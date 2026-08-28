"""范围审计（Scope Audit）测试。

覆盖：
- glob 匹配：allowed 内通过、forbidden 命中违规（forbidden 优先）、无 scope 字段跳过；
- numstat 解析：标准输出、二进制文件（-\\t-\\t 行）、重命名行（=> 与花括号两种写法）；
- LLM 复核：返回合法 JSON → 采纳；返回垃圾 → 降级规则层；
- 状态机接线：违规 → retry 语义事件（step_reflected action=retry，reason 含违规文件），
  重试额度（与验收门禁共用）用尽 → failed；
- GitDiffProvider：真实 git 子进程（git 不可用时跳过）、异常工作区返回空 diff。
"""

import json
import os
import shutil
import tempfile
import unittest
from datetime import UTC, datetime
from subprocess import run
from types import SimpleNamespace
from uuid import uuid4

from app.application.agent_execution_machine import (
    AgentExecutionContext,
    AgentExecutionMachine,
)
from app.application.agent_summary_types import AgentSummaryResult
from app.application.react_step_executor import (
    StepExecutionOutcome,
    StepExecutionRequest,
)
from app.application.scope_audit_service import (
    ScopeAuditService,
    build_diff_digest,
    parse_scope_audit_response,
)
from app.domain.acceptance.scope import (
    FileChange,
    ScopeAuditResult,
    ScopePolicy,
    collect_changes,
)
from app.domain.agent_core.tools import ToolInvocationStatus
from app.domain.agent_runtime.entities import (
    Reflection,
    ReflectionAction,
    StepObservation,
)
from app.domain.agent_runtime.router import AgentStateRouter
from app.domain.context_engineering.entities import MemoryContext
from app.domain.sessions.entities import (
    MessageRole,
    SessionEvent,
    SessionEventType,
)
from app.infrastructure.acceptance.diff_provider import GitDiffProvider


# ===================== 公共桩 =====================


def empty_memory_context() -> MemoryContext:
    return MemoryContext("", [], 0, 0, 0, 0)


def make_event(
    session_id,
    event_type: SessionEventType,
    payload: dict[str, object],
) -> SessionEvent:
    return SessionEvent(uuid4(), session_id, event_type, payload, datetime.now(UTC))


def plan_payload(
    step_count: int = 1,
    scope: dict[str, object] | None = None,
) -> dict[str, object]:
    steps = [
        {
            "id": str(uuid4()),
            "title": f"Step {index + 1}",
            "description": f"Execute step {index + 1}",
            "expected_output": f"Evidence {index + 1}",
            "status": "pending",
        }
        for index in range(step_count)
    ]
    plan: dict[str, object] = {"id": str(uuid4()), "goal": "test goal", "steps": steps}
    if scope is not None:
        plan["scope"] = scope
    return plan


class FakeEventSink:
    """记录 add 调用并返回 SessionEvent（与状态机既有测试桩同构）。"""

    def __init__(self, order: list[str] | None = None) -> None:
        self.order: list[str] = order if order is not None else []
        self.events: list[SessionEvent] = []

    async def add(self, *, session_id, event_type, payload) -> SessionEvent:
        self.order.append(f"event:{event_type.value}")
        event = make_event(session_id, event_type, payload)
        self.events.append(event)
        return event


class FakeUow:
    """假 uow：只提供 session_events 写入通道。"""

    def __init__(self) -> None:
        self.session_events = FakeEventSink()


class FakeLLMService:
    """假 LLM：按序返回配置好的回复文本，并记录请求消息。"""

    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.requests: list[list] = []

    async def chat(self, messages, **kwargs):
        self.requests.append(messages)
        content = self.replies.pop(0) if self.replies else ""
        return SimpleNamespace(content=content)


class FakeDiffProvider:
    """假 DiffProvider：返回固定 diff 文本，并记录 workspace_dir 入参。"""

    def __init__(self, text: str = "") -> None:
        self._text = text
        self.calls: list[str] = []

    async def diff(self, workspace_dir: str = "") -> str:
        self.calls.append(workspace_dir)
        return self._text


class FakeAuditor:
    """ScopeAuditorProtocol 协议桩：按序返回配置好的审计结果。"""

    def __init__(self, results: list[ScopeAuditResult]) -> None:
        self._results = list(results)
        self.calls: list[dict[str, object]] = []

    async def audit(self, session_id, run_id, plan, diff_text) -> ScopeAuditResult:
        self.calls.append(
            {"session_id": session_id, "run_id": run_id, "plan": plan, "diff_text": diff_text}
        )
        if self._results:
            return self._results.pop(0)
        return ScopeAuditResult(in_scope=True, reason="默认通过")


class FakeExecutor:
    def __init__(self, statuses, order: list[str]) -> None:
        self.statuses = iter(statuses)
        self.order = order
        self.requests: list[StepExecutionRequest] = []

    async def execute(self, request: StepExecutionRequest):
        self.requests.append(request)
        self.order.append(f"execute:{request.step_index}:{request.attempt}")
        status = next(self.statuses)
        events = (
            make_event(request.session_id, SessionEventType.step_started, {}),
            make_event(request.session_id, SessionEventType.tool_called, {}),
        )
        return StepExecutionOutcome(events, StepObservation(status, status.value))

    def format_step_history(self, **kwargs) -> str:
        return f"attempt {len(self.requests)}"


class FakeCritic:
    def __init__(self, actions, order: list[str]) -> None:
        self.actions = iter(actions)
        self.order = order
        self.calls = []

    async def evaluate(self, step, observation) -> Reflection:
        self.calls.append((step, observation))
        self.order.append(f"critic:{step.title}")
        action = next(self.actions)
        return Reflection(action, f"{action.value} reason")


class FakeSummarizer:
    def __init__(self, order: list[str]) -> None:
        self.order = order

    async def stream(self, request):
        self.order.append("summarize")
        yield ("answer_delta", "final answer")
        message = SimpleNamespace(
            id=uuid4(), role=MessageRole.assistant, content="final answer"
        )
        yield AgentSummaryResult(
            final_answer="final answer",
            reasoning="",
            message_event=make_event(
                request.session_id,
                SessionEventType.message_created,
                {
                    "message_id": str(message.id),
                    "role": MessageRole.assistant.value,
                    "content": message.content,
                },
            ),
            message_id=message.id,
        )


# ===================== glob 匹配 =====================


class ScopePolicyGlobTest(unittest.TestCase):
    """glob 匹配：allowed 内通过、forbidden 命中违规、无 scope 字段跳过。"""

    def test_files_inside_allowed_pass(self) -> None:
        policy = ScopePolicy(["backend/api/**", "docs/**"])
        changes = [
            FileChange("backend/api/app/main.py", "modified", 10, 2),
            FileChange("docs/guide.md", "added", 5, 0),
        ]
        self.assertEqual(policy.check(changes), [])

    def test_forbidden_beats_allowed(self) -> None:
        policy = ScopePolicy(["backend/api/**", "docker-compose.yml"], ["**/.env*"])
        changes = [
            FileChange("backend/api/.env.local", "modified", 1, 1),
            FileChange("backend/api/app/ok.py", "modified", 1, 0),
        ]
        violations = policy.check(changes)
        # backend/api/.env.local 同时在 allowed 与 forbidden 内：forbidden 优先 → 违规
        self.assertEqual([v.path for v in violations], ["backend/api/.env.local"])

    def test_exact_forbidden_path_violates(self) -> None:
        policy = ScopePolicy(["backend/api/**", "docs/**"], ["docker-compose.yml"])
        violations = policy.check(
            [
                FileChange("docker-compose.yml", "modified", 3, 1),
                FileChange("docs/a.md", "added", 2, 0),
            ]
        )
        self.assertEqual([v.path for v in violations], ["docker-compose.yml"])

    def test_outside_allowed_is_violation(self) -> None:
        policy = ScopePolicy(["backend/api/**"])
        violations = policy.check(
            [
                FileChange("frontend/src/app.ts", "modified", 4, 0),
                FileChange("backend/api/app/ok.py", "modified", 1, 0),
            ]
        )
        self.assertEqual([v.path for v in violations], ["frontend/src/app.ts"])

    def test_from_plan_without_scope_returns_none(self) -> None:
        # 无 scope 字段（老计划）→ None，审计跳过，向后兼容
        self.assertIsNone(ScopePolicy.from_plan(plan_payload()))
        self.assertIsNone(ScopePolicy.from_plan({"scope": {}}))
        self.assertIsNone(ScopePolicy.from_plan({"scope": {"allowed": []}}))

    def test_from_plan_reads_allowed_and_forbidden(self) -> None:
        plan = plan_payload(
            scope={
                "allowed": ["backend/api/**", "docs/**"],
                "forbidden": ["**/.env*", "docker-compose.yml"],
                "llm_review": True,
            }
        )
        policy = ScopePolicy.from_plan(plan)
        self.assertIsNotNone(policy)
        assert policy is not None
        self.assertEqual(policy.allowed_globs, ["backend/api/**", "docs/**"])
        self.assertEqual(policy.forbidden_globs, ["**/.env*", "docker-compose.yml"])


# ===================== numstat 解析 =====================


class CollectChangesTest(unittest.TestCase):
    """numstat 解析：标准输出、二进制行、重命名行。"""

    def test_standard_numstat(self) -> None:
        diff_text = (
            "12\t3\tbackend/api/app/a.py\n"
            "0\t5\tbackend/api/app/b.py\n"
            "7\t0\tbackend/api/app/new.py\n"
        )
        changes = collect_changes(diff_text)
        self.assertEqual(len(changes), 3)
        self.assertEqual(
            (changes[0].path, changes[0].change_type, changes[0].additions, changes[0].deletions),
            ("backend/api/app/a.py", "modified", 12, 3),
        )
        self.assertEqual(changes[1].change_type, "deleted")
        self.assertEqual((changes[1].additions, changes[1].deletions), (0, 5))
        self.assertEqual(changes[2].change_type, "added")
        self.assertEqual((changes[2].additions, changes[2].deletions), (7, 0))

    def test_binary_file_dash_line(self) -> None:
        diff_text = "3\t3\tbackend/api/app/a.py\n-\t-\tassets/logo.png\n"
        changes = collect_changes(diff_text)
        self.assertEqual(len(changes), 2)
        self.assertEqual(changes[1].path, "assets/logo.png")
        # 二进制文件：两列均为 '-'，记为 modified（0/0）
        self.assertEqual(changes[1].change_type, "modified")
        self.assertEqual((changes[1].additions, changes[1].deletions), (0, 0))

    def test_rename_arrow_form(self) -> None:
        diff_text = "12\t3\told/path.py => new/path.py\n"
        changes = collect_changes(diff_text)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].path, "new/path.py")
        self.assertEqual(changes[0].change_type, "modified")

    def test_rename_brace_form(self) -> None:
        diff_text = "1\t1\tsrc/{old.py => new.py}\n"
        changes = collect_changes(diff_text)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].path, "src/new.py")

    def test_full_diff_section_is_ignored(self) -> None:
        # numstat 段后拼接全量 diff：解析在 diff --git 标记处停止
        diff_text = (
            "1\t1\tbackend/api/app/a.py\n"
            "diff --git a/backend/api/app/a.py b/backend/api/app/a.py\n"
            "--- a/backend/api/app/a.py\n"
            "+++ b/backend/api/app/a.py\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
        )
        changes = collect_changes(diff_text)
        self.assertEqual([c.path for c in changes], ["backend/api/app/a.py"])

    def test_empty_text(self) -> None:
        self.assertEqual(collect_changes(""), [])

    def test_diff_digest_keeps_head_per_file(self) -> None:
        # 每文件保留前 lines_per_file 行（含 diff --git 头）：40 = 头 1 行 + 39 内容行
        lines = ["diff --git a/x b/x"] + [f"line{i}" for i in range(60)]
        digest = build_diff_digest("\n".join(lines), lines_per_file=40)
        self.assertIn("line0", digest)
        self.assertIn("line38", digest)
        self.assertNotIn("line39", digest)
        self.assertNotIn("line59", digest)
        self.assertIn("省略", digest)


# ===================== LLM 复核 =====================


class ParseScopeAuditResponseTest(unittest.TestCase):
    def test_valid_json_adopted(self) -> None:
        text = (
            '```json\n'
            '{"in_scope": false, "violations": [{"path": "a.py", "reason": "越界"}], '
            '"reason": "存在越界改动"}\n'
            "```"
        )
        parsed = parse_scope_audit_response(text)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertIs(parsed["in_scope"], False)
        self.assertEqual(parsed["violations"], [{"path": "a.py", "reason": "越界"}])
        self.assertEqual(parsed["reason"], "存在越界改动")

    def test_garbage_returns_none(self) -> None:
        self.assertIsNone(parse_scope_audit_response("我觉得这次改动应该没问题。"))
        self.assertIsNone(parse_scope_audit_response("{这不是 JSON"))
        # in_scope 非布尔 → 结构不合法
        self.assertIsNone(
            parse_scope_audit_response('{"in_scope": "yes", "violations": []}')
        )


class ScopeAuditServiceTest(unittest.IsolatedAsyncioTestCase):
    """两级审计服务：规则层 / LLM 复核 / 降级 / 审计事件。"""

    def _service(
        self, uow: FakeUow, llm: FakeLLMService, **kwargs
    ) -> ScopeAuditService:
        return ScopeAuditService(
            uow, llm, llm_review_threshold=500, **kwargs
        )

    async def test_no_scope_field_skips_audit(self) -> None:
        uow, llm = FakeUow(), FakeLLMService([])
        service = self._service(uow, llm)
        result = await service.audit(uuid4(), uuid4(), plan_payload(), "1\t1\tx.py")

        self.assertTrue(result.in_scope)
        self.assertEqual(result.violations, [])
        self.assertEqual(result.reviewer, "rules")
        self.assertIn("跳过", result.reason)
        self.assertEqual(llm.requests, [])  # 未触发 LLM
        # 审计事件仍然落库（跳过也是审计留痕）
        self.assertEqual(len(uow.session_events.events), 1)
        event = uow.session_events.events[0]
        self.assertIs(event.type, SessionEventType.scope_audit_finished)
        self.assertIs(event.payload["in_scope"], True)

    async def test_rules_layer_violation(self) -> None:
        uow, llm = FakeUow(), FakeLLMService([])
        service = self._service(uow, llm)
        plan = plan_payload(scope={"allowed": ["backend/api/**"]})
        diff_text = "1\t1\tbackend/api/app/ok.py\n4\t0\tfrontend/out.ts\n"
        result = await service.audit(uuid4(), uuid4(), plan, diff_text)

        self.assertFalse(result.in_scope)
        self.assertEqual([v.path for v in result.violations], ["frontend/out.ts"])
        self.assertEqual(result.reviewer, "rules")
        self.assertEqual(result.checked_files, 2)
        self.assertIn("frontend/out.ts", result.reason)
        self.assertEqual(llm.requests, [])  # 小体积 allowed 变更不触发 LLM

    async def test_llm_review_adopted_when_enabled(self) -> None:
        uow = FakeUow()
        llm = FakeLLMService(
            [
                json.dumps(
                    {
                        "in_scope": False,
                        "violations": [
                            {"path": "backend/api/app/hack.py", "reason": "与计划无关"}
                        ],
                        "reason": "发现计划外改动",
                    },
                    ensure_ascii=False,
                )
            ]
        )
        service = self._service(uow, llm)
        plan = plan_payload(scope={"allowed": ["backend/api/**"], "llm_review": True})
        diff_text = "10\t2\tbackend/api/app/ok.py\n"
        result = await service.audit(uuid4(), uuid4(), plan, diff_text)

        self.assertFalse(result.in_scope)
        self.assertEqual(
            [v.path for v in result.violations], ["backend/api/app/hack.py"]
        )
        self.assertEqual(result.reviewer, "rules+llm")
        self.assertIn("发现计划外改动", result.reason)
        # LLM 请求应包含 diff 摘要与 scope 声明
        user_prompt = llm.requests[0][1].content
        self.assertIn("diff 摘要", user_prompt)
        self.assertIn("backend/api/**", user_prompt)

    async def test_llm_garbage_falls_back_to_rules(self) -> None:
        uow = FakeUow()
        llm = FakeLLMService(["我认为这些改动看起来都还可以，继续保持。"])
        service = self._service(uow, llm)
        plan = plan_payload(scope={"allowed": ["backend/api/**"], "llm_review": True})
        diff_text = "10\t2\tbackend/api/app/ok.py\n"
        result = await service.audit(uuid4(), uuid4(), plan, diff_text)

        # 全部变更都在 allowed 内：规则层通过；LLM 垃圾回复 → 降级只信规则层
        self.assertTrue(result.in_scope)
        self.assertEqual(result.violations, [])
        self.assertEqual(result.reviewer, "rules")
        self.assertIn("降级", result.reason)

    async def test_llm_review_triggered_by_large_allowed_file(self) -> None:
        uow = FakeUow()
        llm = FakeLLMService(
            [json.dumps({"in_scope": True, "violations": [], "reason": "正常大改"})]
        )
        service = self._service(uow, llm)
        plan = plan_payload(scope={"allowed": ["backend/api/**"]})
        # 单文件 600 行变更 > 阈值 500：体积异常触发 LLM 复核
        diff_text = "600\t0\tbackend/api/app/big.py\n"
        result = await service.audit(uuid4(), uuid4(), plan, diff_text)

        self.assertEqual(len(llm.requests), 1)
        self.assertTrue(result.in_scope)
        self.assertEqual(result.reviewer, "rules+llm")

    async def test_write_audit_event_flag_off(self) -> None:
        # 被状态机驱动时关闭事件写入（事件由状态机统一写入，避免重复）
        uow = FakeUow()
        llm = FakeLLMService([])
        service = self._service(uow, llm, write_audit_event=False)
        plan = plan_payload(scope={"allowed": ["backend/api/**"]})
        await service.audit(uuid4(), uuid4(), plan, "1\t1\tbackend/api/app/a.py")
        self.assertEqual(uow.session_events.events, [])


# ===================== 状态机接线 =====================


class MachineScopeAuditTest(unittest.IsolatedAsyncioTestCase):
    """状态机 summarize 前范围审计：违规 → retry 语义事件；额度用尽 → failed。"""

    def _machine(
        self,
        order: list[str],
        auditor: FakeAuditor,
        provider: FakeDiffProvider,
        *,
        executor_statuses,
        critic_actions,
        acceptance_gate_max_retries: int = 2,
    ) -> AgentExecutionMachine:
        sink = FakeEventSink(order)
        return AgentExecutionMachine(
            executor=FakeExecutor(executor_statuses, order),
            critic=FakeCritic(critic_actions, order),
            summarizer=FakeSummarizer(order),
            event_sink=sink,
            router=AgentStateRouter(),
            scope_auditor=auditor,
            scope_diff_provider=provider,
            acceptance_gate_max_retries=acceptance_gate_max_retries,
        )

    async def collect(self, machine: AgentExecutionMachine, plan) -> list:
        session_id = uuid4()
        context = AgentExecutionContext(
            empty_memory_context(), "agent context", workspace_dir="/ws"
        )
        return [item async for item in machine.stream(session_id, plan, context)]

    def _violation_result(self) -> ScopeAuditResult:
        return ScopeAuditResult(
            in_scope=False,
            violations=[
                FileChange(path="frontend/out.ts", change_type="modified", additions=4, deletions=0)
            ],
            checked_files=2,
            reviewer="rules",
            reason="越界文件变更: frontend/out.ts",
        )

    async def test_violation_triggers_retry_then_passes(self) -> None:
        order: list[str] = []
        auditor = FakeAuditor([self._violation_result(), ScopeAuditResult(in_scope=True)])
        provider = FakeDiffProvider("1\t1\tbackend/api/app/ok.py\n4\t0\tfrontend/out.ts\n")
        machine = self._machine(
            order,
            auditor,
            provider,
            executor_statuses=[
                ToolInvocationStatus.succeeded,
                ToolInvocationStatus.succeeded,
            ],
            critic_actions=[ReflectionAction.accept, ReflectionAction.accept],
        )
        plan = plan_payload(scope={"allowed": ["backend/api/**"]})

        items = await self.collect(machine, plan)

        # 第一次审计违规 → retry 语义事件 → 重跑步骤 → 第二次审计通过 → summarize
        self.assertEqual(
            order,
            [
                "execute:0:1",
                "critic:Step 1",
                "event:step_reflected",
                "event:step_completed",
                "event:scope_audit_finished",
                "event:step_reflected",  # 审计违规产生的 retry 语义事件
                "execute:0:2",
                "critic:Step 1",
                "event:step_reflected",
                "event:step_completed",
                "event:scope_audit_finished",
                "summarize",
                "event:task_done",
            ],
        )
        # retry 语义事件：action=retry，reason 写明违规文件
        reflected = [
            item
            for item in items
            if isinstance(item, SessionEvent)
            and item.type is SessionEventType.step_reflected
        ]
        retry_event = reflected[1]
        self.assertEqual(retry_event.payload["action"], "retry")
        self.assertIn("frontend/out.ts", str(retry_event.payload["reason"]))
        # 审计事件进入事件流（供重试额度计数）
        audit_events = [
            item
            for item in items
            if isinstance(item, SessionEvent)
            and item.type is SessionEventType.scope_audit_finished
        ]
        self.assertEqual([e.payload["in_scope"] for e in audit_events], [False, True])
        # 审计器被调用两次，且拿到 diff provider 的 diff 文本
        self.assertEqual(len(auditor.calls), 2)
        self.assertEqual(auditor.calls[0]["diff_text"], provider._text)
        self.assertEqual(provider.calls, ["/ws", "/ws"])

    async def test_violation_exhausts_shared_retry_quota_then_fails(self) -> None:
        order: list[str] = []
        # 额度 1：第一次违规重试一次，第二次违规额度用尽 → failed
        auditor = FakeAuditor(
            [self._violation_result(), self._violation_result(), self._violation_result()]
        )
        provider = FakeDiffProvider("4\t0\tfrontend/out.ts\n")
        machine = self._machine(
            order,
            auditor,
            provider,
            executor_statuses=[
                ToolInvocationStatus.succeeded,
                ToolInvocationStatus.succeeded,
            ],
            critic_actions=[ReflectionAction.accept, ReflectionAction.accept],
            acceptance_gate_max_retries=1,
        )
        plan = plan_payload(scope={"allowed": ["backend/api/**"]})

        items = await self.collect(machine, plan)

        self.assertNotIn("summarize", order)
        self.assertNotIn("event:task_done", order)
        self.assertIn("event:task_error", order)
        event_types = [
            item.type for item in items if isinstance(item, SessionEvent)
        ]
        self.assertIn(SessionEventType.step_failed, event_types)
        # 终态 task_error：phase=failed
        task_error = items[-1]
        self.assertIsInstance(task_error, SessionEvent)
        self.assertIs(task_error.type, SessionEventType.task_error)
        self.assertEqual(task_error.payload["phase"], "failed")
        # 两次审计都违规
        self.assertEqual(len(auditor.calls), 2)

    async def test_allow_retry_false_fails_immediately(self) -> None:
        order: list[str] = []
        auditor = FakeAuditor([self._violation_result()])
        provider = FakeDiffProvider("4\t0\tfrontend/out.ts\n")
        machine = self._machine(
            order,
            auditor,
            provider,
            executor_statuses=[ToolInvocationStatus.succeeded],
            critic_actions=[ReflectionAction.accept],
        )
        plan = plan_payload(
            scope={"allowed": ["backend/api/**"], "allow_retry": False}
        )

        items = await self.collect(machine, plan)

        self.assertNotIn("summarize", order)
        event_types = [
            item.type for item in items if isinstance(item, SessionEvent)
        ]
        self.assertIn(SessionEventType.step_failed, event_types)
        # 不允许重试：只执行一次
        self.assertEqual(len(auditor.calls), 1)

    async def test_no_scope_field_skips_auditor(self) -> None:
        order: list[str] = []
        auditor = FakeAuditor([self._violation_result()])
        provider = FakeDiffProvider("4\t0\tfrontend/out.ts\n")
        machine = self._machine(
            order,
            auditor,
            provider,
            executor_statuses=[ToolInvocationStatus.succeeded],
            critic_actions=[ReflectionAction.accept],
        )
        plan = plan_payload()  # 无 scope 字段

        await self.collect(machine, plan)

        self.assertEqual(auditor.calls, [])
        self.assertNotIn("event:scope_audit_finished", order)
        self.assertIn("summarize", order)


# ===================== GitDiffProvider =====================


@unittest.skipUnless(shutil.which("git") is not None, "git 不可用")
class GitDiffProviderTest(unittest.IsolatedAsyncioTestCase):
    async def test_diff_in_temp_repo(self) -> None:
        provider = GitDiffProvider()
        with tempfile.TemporaryDirectory() as tmp:
            def git(*args: str) -> None:
                run(["git", *args], cwd=tmp, check=True, capture_output=True)

            git("init")
            with open(f"{tmp}/a.py", "w", encoding="utf-8") as f:
                f.write("print('a')\n")
            with open(f"{tmp}/c.py", "w", encoding="utf-8") as f:
                f.write("print('c')\n")
            git("add", "-A")
            git(
                "-c", "user.email=t@t.local", "-c", "user.name=t",
                "commit", "-m", "init",
            )
            # 修改 a、新增 b、删除 c
            with open(f"{tmp}/a.py", "w", encoding="utf-8") as f:
                f.write("print('a')\nprint('a2')\n")
            with open(f"{tmp}/b.py", "w", encoding="utf-8") as f:
                f.write("print('b')\n")
            # 新增文件需暂存才会出现在 git diff HEAD 中
            git("add", "b.py")
            os.remove(f"{tmp}/c.py")

            diff_text = await provider.diff(tmp)

        self.assertIn("diff --git", diff_text)
        changes = collect_changes(diff_text)
        paths = {c.path for c in changes}
        self.assertIn("a.py", paths)
        self.assertIn("b.py", paths)
        self.assertIn("c.py", paths)
        by_path = {c.path: c for c in changes}
        self.assertEqual(by_path["b.py"].change_type, "added")
        self.assertEqual(by_path["c.py"].change_type, "deleted")

    async def test_missing_workspace_returns_empty(self) -> None:
        provider = GitDiffProvider()
        self.assertEqual(await provider.diff(), "")
        self.assertEqual(await provider.diff("/nonexistent/workspace/xyz"), "")


if __name__ == "__main__":
    unittest.main()
