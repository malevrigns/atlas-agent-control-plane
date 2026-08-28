"""验收链（summarize 前三级门禁）状态机接线测试。

链顺序（DESIGN.md：先便宜后贵、先确定后概率）：
acceptance gate（确定性命令）→ scope audit（规则+LLM）→ coverage review（纯 LLM）。

覆盖：
1. 三级全过 → acceptance_chain_finished 汇总事件 + 正常 summarize（并验证链顺序与 diff 复用）；
2. gate fail → 链短路（scope/coverage 不执行，无汇总事件）；
3. coverage inadequate + enforce_coverage=true → 共用重试额度 → retry 后通过；
4. coverage inadequate + 无 enforce → 只审计不阻断；
5. LLM 不可用（评审器返回 skipped）→ fail-open，链继续；
6. 共用重试额度：gate 失败与 coverage 不足合并计数，额度用尽 → failed；
7. 老计划未接三级 → 无链汇总事件（向后兼容）。
"""
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

from app.application.agent_execution_machine import (
    AgentExecutionContext,
    AgentExecutionMachine,
)
from app.application.agent_summary_service import AgentSummaryResult
from app.application.react_step_executor import StepExecutionOutcome, StepExecutionRequest
from app.domain.acceptance.coverage import CoverageGap, CoverageReviewResult
from app.domain.acceptance.gate import AcceptanceGateConfig, AcceptanceGateResult
from app.domain.acceptance.scope import ScopeAuditResult
from app.domain.agent_core.tools import ToolInvocationStatus
from app.domain.agent_runtime.entities import Reflection, ReflectionAction, StepObservation
from app.domain.agent_runtime.router import AgentStateRouter
from app.domain.context_engineering.entities import MemoryContext
from app.domain.sessions.entities import MessageRole, SessionEvent, SessionEventType


# ===================== 通用 fake / 工具函数（沿用 test_agent_execution_machine 的写法） =====================


def empty_memory_context() -> MemoryContext:
    return MemoryContext("", [], 0, 0, 0, 0)


def plan_payload(step_count: int = 1) -> dict[str, object]:
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
    return {"id": str(uuid4()), "goal": "test goal", "steps": steps}


def chain_plan(
    enforce_coverage: bool | None = None,
    with_gate: bool = True,
    with_scope: bool = True,
) -> dict[str, object]:
    """验收链测试用 plan payload：acceptance（可带 enforce_coverage）+ scope（可选）。"""
    plan = plan_payload(1)
    if with_gate:
        acceptance: dict[str, object] = {"command": "pytest -q", "timeout_seconds": 600}
        if enforce_coverage is not None:
            acceptance["enforce_coverage"] = enforce_coverage
        plan["acceptance"] = acceptance
    if with_scope:
        plan["scope"] = {"allowed": ["backend/api/**"]}
    return plan


# 测试用工作区 diff：一个测试文件 + 一个业务文件（供 changed/test 文件解析）
DIFF_TEXT = "3\t1\tbackend/api/tests/test_feature.py\n2\t0\tbackend/api/app/feature.py\n"


def make_event(
    session_id: UUID,
    event_type: SessionEventType,
    payload: dict[str, object],
) -> SessionEvent:
    return SessionEvent(uuid4(), session_id, event_type, payload, datetime.now(UTC))


def gate_result(passed: bool, exit_code: int | None) -> AcceptanceGateResult:
    """构造一个门禁判定结果（测试用）。"""
    return AcceptanceGateResult(
        passed=passed,
        exit_code=exit_code,
        command="pytest -q",
        output_digest="digest",
        duration_ms=12,
        reason="验收通过" if passed else f"exit_code={exit_code}",
    )


def coverage_result(
    *,
    adequate: bool,
    gaps: tuple[CoverageGap, ...] = (),
    reviewer: str = "llm",
    reason: str = "评审正常",
) -> CoverageReviewResult:
    """构造一个覆盖度评审结果（测试用）。"""
    return CoverageReviewResult(adequate=adequate, gaps=list(gaps), reviewer=reviewer, reason=reason)


def high_gap(area: str = "超时路径", suggestion: str = "补充超时测试") -> CoverageGap:
    return CoverageGap(area=area, severity="high", suggestion=suggestion)


def in_scope_result() -> ScopeAuditResult:
    return ScopeAuditResult(in_scope=True, checked_files=2, reviewer="rules", reason="正常")


class FakeEventSink:
    def __init__(self, order: list[str]) -> None:
        self.order = order
        self.events: list[SessionEvent] = []

    async def add(self, *, session_id, event_type, payload) -> SessionEvent:
        self.order.append(f"event:{event_type.value}")
        event = make_event(session_id, event_type, payload)
        self.events.append(event)
        return event


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


class FakeGate:
    """假门禁：按顺序弹出预设结果（最后一个结果一直复用）。"""

    def __init__(self, results: list[AcceptanceGateResult]) -> None:
        self.results = list(results)
        self.calls: list[AcceptanceGateConfig] = []

    async def verify(self, config: AcceptanceGateConfig) -> AcceptanceGateResult:
        self.calls.append(config)
        if len(self.results) > 1:
            return self.results.pop(0)
        return self.results[0]


class FakeAuditor:
    """假范围审计器：按顺序弹出预设结果（最后一个结果一直复用）。"""

    def __init__(self, results: list[ScopeAuditResult]) -> None:
        self.results = list(results)
        self.calls: list[dict[str, object]] = []

    async def audit(self, session_id, run_id, plan, diff_text) -> ScopeAuditResult:
        self.calls.append({"diff_text": diff_text})
        if len(self.results) > 1:
            return self.results.pop(0)
        return self.results[0]


class FakeDiffProvider:
    def __init__(self, text: str = DIFF_TEXT) -> None:
        self._text = text
        self.calls: list[str] = []

    async def diff(self, workspace_dir: str = "") -> str:
        self.calls.append(workspace_dir)
        return self._text


class FakeCoverageReviewer:
    """假覆盖度评审器：按顺序弹出预设结果（最后一个结果一直复用），记录评审输入。"""

    def __init__(self, results: list[CoverageReviewResult]) -> None:
        self.results = list(results)
        self.calls: list[dict[str, object]] = []

    async def review(
        self,
        session_id,
        run_id,
        plan,
        changed_files,
        test_files,
        test_case_names,
    ) -> CoverageReviewResult:
        self.calls.append(
            {
                "changed_files": list(changed_files),
                "test_files": list(test_files),
                "test_case_names": list(test_case_names),
            }
        )
        if len(self.results) > 1:
            return self.results.pop(0)
        return self.results[0]


# ===================== 状态机 + 验收链 =====================


class AcceptanceChainMachineTest(unittest.IsolatedAsyncioTestCase):
    """AgentExecutionMachine + 三级验收链：gate → scope → coverage。"""

    async def collect(self, machine, plan) -> list:
        session_id = uuid4()
        context = AgentExecutionContext(
            empty_memory_context(), "agent context", workspace_dir="/ws"
        )
        return [item async for item in machine.stream(session_id, plan, context)]

    def build_machine(
        self,
        order,
        gate,
        auditor,
        provider,
        reviewer,
        statuses,
        actions,
        max_retries: int = 2,
    ) -> AgentExecutionMachine:
        return AgentExecutionMachine(
            executor=FakeExecutor(statuses, order),
            critic=FakeCritic(actions, order),
            summarizer=FakeSummarizer(order),
            event_sink=FakeEventSink(order),
            router=AgentStateRouter(),
            acceptance_gate=gate,
            acceptance_gate_max_retries=max_retries,
            scope_auditor=auditor,
            scope_diff_provider=provider,
            coverage_reviewer=reviewer,
        )

    def event_types(self, items) -> list[SessionEventType]:
        return [item.type for item in items if isinstance(item, SessionEvent)]

    def find_events(self, items, event_type: SessionEventType) -> list[SessionEvent]:
        return [
            item
            for item in items
            if isinstance(item, SessionEvent) and item.type is event_type
        ]

    async def test_all_three_stages_pass_writes_chain_event_and_summarizes(self) -> None:
        """三级全过 → 汇总事件列出各 stage 结论，再正常 summarize；验证链顺序与 diff 复用。"""
        order: list[str] = []
        gate = FakeGate([gate_result(True, 0)])
        auditor = FakeAuditor([in_scope_result()])
        provider = FakeDiffProvider()
        reviewer = FakeCoverageReviewer([coverage_result(adequate=True)])
        machine = self.build_machine(
            order,
            gate,
            auditor,
            provider,
            reviewer,
            [ToolInvocationStatus.succeeded],
            [ReflectionAction.accept],
        )

        plan = chain_plan()
        items = await self.collect(machine, plan)

        # 链顺序：gate → scope → coverage → 链汇总 → summarize → done
        self.assertEqual(
            order,
            [
                "execute:0:1",
                "critic:Step 1",
                "event:step_reflected",
                "event:step_completed",
                "event:acceptance_gate_started",
                "event:acceptance_gate_finished",
                "event:scope_audit_finished",
                "event:coverage_review_finished",
                "event:acceptance_chain_finished",
                "summarize",
                "event:task_done",
            ],
        )
        # diff 每个 cycle 只取一次（范围审计与覆盖度评审共用，避免重复 git 调用）
        self.assertEqual(provider.calls, ["/ws"])
        # 覆盖度评审输入：改动文件清单 / 测试文件清单（从 diff 解析）
        self.assertEqual(
            reviewer.calls[0]["changed_files"],
            ["backend/api/tests/test_feature.py", "backend/api/app/feature.py"],
        )
        self.assertEqual(
            reviewer.calls[0]["test_files"], ["backend/api/tests/test_feature.py"]
        )
        # 汇总事件 payload：各 stage 的 passed/skipped + detail
        chain_events = self.find_events(items, SessionEventType.acceptance_chain_finished)
        self.assertEqual(len(chain_events), 1)
        stages = chain_events[0].payload["stages"]
        self.assertEqual(
            list(stages), ["acceptance_gate", "scope_audit", "coverage_review"]
        )
        self.assertEqual(stages["acceptance_gate"]["status"], "passed")
        self.assertIn("exit_code=0", stages["acceptance_gate"]["detail"])
        self.assertEqual(stages["scope_audit"]["status"], "passed")
        self.assertEqual(stages["coverage_review"]["status"], "passed")
        self.assertIn("adequate=True", stages["coverage_review"]["detail"])
        # 身份字段与门禁/审计事件同构
        self.assertEqual(chain_events[0].payload["plan_id"], plan["id"])
        self.assertEqual(chain_events[0].payload["plan_revision"], 0)
        self.assertTrue(chain_events[0].payload["run_id"])
        # 终态正常
        self.assertEqual(self.event_types(items)[-1], SessionEventType.task_done)

    async def test_gate_fail_short_circuits_chain(self) -> None:
        """gate fail → 链短路：范围审计与覆盖度评审均不执行，无链汇总事件。"""
        order: list[str] = []
        gate = FakeGate([gate_result(False, 1)])
        auditor = FakeAuditor([in_scope_result()])
        provider = FakeDiffProvider()
        reviewer = FakeCoverageReviewer([coverage_result(adequate=True)])
        machine = self.build_machine(
            order,
            gate,
            auditor,
            provider,
            reviewer,
            [ToolInvocationStatus.succeeded],
            [ReflectionAction.accept],
            max_retries=0,
        )

        items = await self.collect(machine, chain_plan())

        # 只有 gate 跑了；scope/coverage 未被触碰
        self.assertEqual(len(gate.calls), 1)
        self.assertEqual(auditor.calls, [])
        self.assertEqual(reviewer.calls, [])
        event_types = self.event_types(items)
        self.assertNotIn(SessionEventType.scope_audit_finished, event_types)
        self.assertNotIn(SessionEventType.coverage_review_finished, event_types)
        self.assertNotIn(SessionEventType.acceptance_chain_finished, event_types)
        self.assertNotIn("summarize", order)
        # 额度 0 → 直接 failed
        self.assertEqual(
            event_types[-3:],
            [
                SessionEventType.step_reflected,
                SessionEventType.step_failed,
                SessionEventType.task_error,
            ],
        )
        self.assertEqual(items[-1].payload["phase"], "failed")

    async def test_coverage_inadequate_with_enforce_retries(self) -> None:
        """coverage inadequate + enforce_coverage=true → 共用重试额度 → retry 后通过 → summarize。"""
        order: list[str] = []
        gate = FakeGate([gate_result(True, 0)])
        auditor = FakeAuditor([in_scope_result(), in_scope_result()])
        provider = FakeDiffProvider()
        reviewer = FakeCoverageReviewer(
            [
                coverage_result(adequate=False, gaps=(high_gap(),), reason="存在高风险缺口"),
                coverage_result(adequate=True),
            ]
        )
        machine = self.build_machine(
            order,
            gate,
            auditor,
            provider,
            reviewer,
            [ToolInvocationStatus.succeeded, ToolInvocationStatus.succeeded],
            [ReflectionAction.accept, ReflectionAction.accept],
        )

        plan = chain_plan(enforce_coverage=True)
        items = await self.collect(machine, plan)

        # 第一次不足 → 重试当前步骤；第二次通过 → summarize
        self.assertEqual(len(gate.calls), 2)
        self.assertEqual(len(auditor.calls), 2)
        self.assertEqual(len(reviewer.calls), 2)
        self.assertEqual(
            order,
            [
                "execute:0:1",
                "critic:Step 1",
                "event:step_reflected",
                "event:step_completed",
                "event:acceptance_gate_started",
                "event:acceptance_gate_finished",
                "event:scope_audit_finished",
                "event:coverage_review_finished",
                "event:step_reflected",  # 覆盖度不足产生的 retry 语义事件
                "execute:0:2",
                "critic:Step 1",
                "event:step_reflected",
                "event:step_completed",
                "event:acceptance_gate_started",
                "event:acceptance_gate_finished",
                "event:scope_audit_finished",
                "event:coverage_review_finished",
                "event:acceptance_chain_finished",
                "summarize",
                "event:task_done",
            ],
        )
        # 第一次评审事件：enforce 开启、不足、gap 已落审计
        finished = self.find_events(items, SessionEventType.coverage_review_finished)
        self.assertEqual(len(finished), 2)
        self.assertIs(finished[0].payload["enforce_coverage"], True)
        self.assertIs(finished[0].payload["adequate"], False)
        self.assertEqual(finished[0].payload["gap_count"], 1)
        self.assertEqual(finished[0].payload["gaps"][0]["area"], "超时路径")
        # retry 语义事件的 reason 列出 high gap
        reflected = self.find_events(items, SessionEventType.step_reflected)
        retry_events = [e for e in reflected if e.payload.get("action") == "retry"]
        self.assertEqual(len(retry_events), 1)
        self.assertIn("覆盖度评审不足", retry_events[0].payload["reason"])
        self.assertIn("超时路径", retry_events[0].payload["reason"])
        # 终态正常
        self.assertEqual(self.event_types(items)[-1], SessionEventType.task_done)

    async def test_coverage_inadequate_without_enforce_only_audits(self) -> None:
        """coverage inadequate + 无 enforce → 只审计不阻断：无 retry，正常 summarize。"""
        order: list[str] = []
        gate = FakeGate([gate_result(True, 0)])
        auditor = FakeAuditor([in_scope_result()])
        provider = FakeDiffProvider()
        reviewer = FakeCoverageReviewer(
            [coverage_result(adequate=False, gaps=(high_gap(),), reason="存在高风险缺口")]
        )
        machine = self.build_machine(
            order,
            gate,
            auditor,
            provider,
            reviewer,
            [ToolInvocationStatus.succeeded],
            [ReflectionAction.accept],
        )

        plan = chain_plan()  # 无 enforce_coverage 字段
        items = await self.collect(machine, plan)

        # 不重试：各 stage 只跑一次，终态正常
        self.assertEqual(len(gate.calls), 1)
        self.assertEqual(len(reviewer.calls), 1)
        reflected = self.find_events(items, SessionEventType.step_reflected)
        self.assertEqual([e for e in reflected if e.payload.get("action") == "retry"], [])
        self.assertEqual(
            order,
            [
                "execute:0:1",
                "critic:Step 1",
                "event:step_reflected",
                "event:step_completed",
                "event:acceptance_gate_started",
                "event:acceptance_gate_finished",
                "event:scope_audit_finished",
                "event:coverage_review_finished",
                "event:acceptance_chain_finished",
                "summarize",
                "event:task_done",
            ],
        )
        # 审计事件：inadequate + enforce 关闭（失败开放）
        finished = self.find_events(items, SessionEventType.coverage_review_finished)
        self.assertIs(finished[0].payload["adequate"], False)
        self.assertIs(finished[0].payload["enforce_coverage"], False)
        # 链汇总事件：coverage stage 显式标注"仅建议"
        stages = self.find_events(items, SessionEventType.acceptance_chain_finished)[
            0
        ].payload["stages"]
        self.assertEqual(stages["coverage_review"]["status"], "passed")
        self.assertIn("仅建议", stages["coverage_review"]["detail"])
        self.assertEqual(self.event_types(items)[-1], SessionEventType.task_done)

    async def test_coverage_llm_unavailable_skips_and_chain_continues(self) -> None:
        """LLM 不可用（评审器返回 skipped）→ fail-open：即使 enforce 开启也不阻断，链继续。"""
        order: list[str] = []
        gate = FakeGate([gate_result(True, 0)])
        auditor = FakeAuditor([in_scope_result()])
        provider = FakeDiffProvider()
        reviewer = FakeCoverageReviewer(
            [coverage_result(adequate=True, reviewer="skipped", reason="llm unavailable")]
        )
        machine = self.build_machine(
            order,
            gate,
            auditor,
            provider,
            reviewer,
            [ToolInvocationStatus.succeeded],
            [ReflectionAction.accept],
        )

        items = await self.collect(machine, chain_plan(enforce_coverage=True))

        reflected = self.find_events(items, SessionEventType.step_reflected)
        self.assertEqual([e for e in reflected if e.payload.get("action") == "retry"], [])
        finished = self.find_events(items, SessionEventType.coverage_review_finished)
        self.assertEqual(finished[0].payload["reviewer"], "skipped")
        self.assertIs(finished[0].payload["adequate"], True)
        stages = self.find_events(items, SessionEventType.acceptance_chain_finished)[
            0
        ].payload["stages"]
        self.assertIn("reviewer=skipped", stages["coverage_review"]["detail"])
        self.assertIn("summarize", order)
        self.assertEqual(self.event_types(items)[-1], SessionEventType.task_done)

    async def test_shared_retry_quota_across_gate_and_coverage(self) -> None:
        """共用重试额度：gate 失败（消耗 1 次）+ coverage 不足 → 额度用尽 → failed。

        若额度不共用，coverage 失败（自身计数 0 < 1）本应还能重试——本用例证明合并计数生效。
        """
        order: list[str] = []
        gate = FakeGate([gate_result(False, 1), gate_result(True, 0)])
        auditor = FakeAuditor([in_scope_result()])
        provider = FakeDiffProvider()
        reviewer = FakeCoverageReviewer(
            [coverage_result(adequate=False, gaps=(high_gap(),))]
        )
        executor = FakeExecutor(
            [ToolInvocationStatus.succeeded, ToolInvocationStatus.succeeded], order
        )
        machine = AgentExecutionMachine(
            executor=executor,
            critic=FakeCritic(
                [ReflectionAction.accept, ReflectionAction.accept], order
            ),
            summarizer=FakeSummarizer(order),
            event_sink=FakeEventSink(order),
            router=AgentStateRouter(),
            acceptance_gate=gate,
            acceptance_gate_max_retries=1,
            scope_auditor=auditor,
            scope_diff_provider=provider,
            coverage_reviewer=reviewer,
        )

        plan = chain_plan(enforce_coverage=True, with_scope=False)
        items = await self.collect(machine, plan)

        # 第 1 次：gate 失败消耗额度 → retry；第 2 次：gate 通过、coverage 不足，
        # 共用计数 = 1（额度已用尽）→ 直接 failed
        self.assertEqual(len(gate.calls), 2)
        self.assertEqual(len(reviewer.calls), 1)
        self.assertEqual(
            [(request.step_index, request.attempt) for request in executor.requests],
            [(0, 1), (0, 2)],
        )
        self.assertNotIn("summarize", order)
        reflected = self.find_events(items, SessionEventType.step_reflected)
        last = reflected[-1]
        self.assertEqual(last.payload["action"], "fail")
        self.assertIn("覆盖度评审不足", last.payload["reason"])
        self.assertEqual(items[-1].payload["phase"], "failed")
        self.assertNotIn(
            SessionEventType.acceptance_chain_finished, self.event_types(items)
        )

    async def test_plain_machine_writes_no_chain_event(self) -> None:
        """老计划未接三级（无 gate/scope/coverage）→ 无链汇总事件（向后兼容）。"""
        order: list[str] = []
        machine = AgentExecutionMachine(
            executor=FakeExecutor([ToolInvocationStatus.succeeded], order),
            critic=FakeCritic([ReflectionAction.accept], order),
            summarizer=FakeSummarizer(order),
            event_sink=FakeEventSink(order),
            router=AgentStateRouter(),
        )

        items = await self.collect(machine, plan_payload(1))

        self.assertEqual(
            order,
            [
                "execute:0:1",
                "critic:Step 1",
                "event:step_reflected",
                "event:step_completed",
                "summarize",
                "event:task_done",
            ],
        )
        event_types = self.event_types(items)
        self.assertNotIn(SessionEventType.acceptance_chain_finished, event_types)
        self.assertNotIn(SessionEventType.acceptance_gate_finished, event_types)
        self.assertNotIn(SessionEventType.scope_audit_finished, event_types)
        self.assertNotIn(SessionEventType.coverage_review_finished, event_types)


if __name__ == "__main__":
    unittest.main()
