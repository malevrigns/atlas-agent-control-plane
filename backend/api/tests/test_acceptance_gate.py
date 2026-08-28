"""验收门禁（Acceptance Gate）测试。

覆盖：
1. domain 门禁的退出码语义（0 通过 / 非 0 不通过 / 超时 / 命令不存在）；
2. plan payload 的 acceptance 配置解析（向后兼容：无该字段返回 None）；
3. 应用服务的审计事件写入（acceptance_gate_started / acceptance_gate_finished）；
4. 状态机接入：gate 通过才 summarize；gate 失败重试；重试额度用完 failed；
   老计划（无 acceptance）不执行门禁。
"""

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

from app.application.acceptance_gate_service import (
    AcceptanceGateService,
    gate_config_from_plan,
)
from app.application.agent_execution_machine import (
    AgentExecutionContext,
    AgentExecutionMachine,
)
from app.application.agent_summary_service import AgentSummaryResult
from app.application.react_step_executor import (
    StepExecutionOutcome,
    StepExecutionRequest,
)
from app.domain.acceptance.gate import (
    OUTPUT_DIGEST_LIMIT,
    AcceptanceGate,
    AcceptanceGateConfig,
    AcceptanceGateResult,
    CommandOutcome,
)
from app.domain.agent_core.tools import ToolInvocationStatus
from app.domain.agent_runtime.entities import (
    Reflection,
    ReflectionAction,
    StepObservation,
)
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


def plan_with_gate(
    step_count: int = 1,
    command: str = "pytest -q",
    allow_retry: bool | None = None,
) -> dict[str, object]:
    """带 acceptance 门禁配置的 plan payload。"""
    plan = plan_payload(step_count)
    acceptance: dict[str, object] = {"command": command, "timeout_seconds": 600}
    if allow_retry is not None:
        acceptance["allow_retry"] = allow_retry
    plan["acceptance"] = acceptance
    return plan


def make_event(
    session_id: UUID,
    event_type: SessionEventType,
    payload: dict[str, object],
) -> SessionEvent:
    return SessionEvent(uuid4(), session_id, event_type, payload, datetime.now(UTC))


def gate_result(
    passed: bool, exit_code: int | None = None, command: str = "pytest -q"
) -> AcceptanceGateResult:
    """构造一个门禁判定结果（测试用）。"""
    return AcceptanceGateResult(
        passed=passed,
        exit_code=exit_code,
        command=command,
        output_digest="digest",
        duration_ms=12,
        reason="验收通过" if passed else f"exit_code={exit_code}",
    )


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


class FakeRunner:
    """假的命令执行器：返回预设 outcome，或抛出预设异常。"""

    def __init__(
        self,
        outcome: CommandOutcome | None = None,
        error: Exception | None = None,
    ) -> None:
        self.outcome = outcome
        self.error = error
        self.calls: list[tuple[str, int, str]] = []

    async def run(self, command: str, timeout_seconds: int, working_dir: str):
        self.calls.append((command, timeout_seconds, working_dir))
        if self.error is not None:
            raise self.error
        assert self.outcome is not None, "FakeRunner 未配置 outcome"
        return self.outcome


class FakeGate:
    """假的门禁：按顺序弹出预设结果（最后一个结果会一直复用）。"""

    def __init__(
        self,
        results: list[AcceptanceGateResult],
        order: list[str] | None = None,
    ) -> None:
        self.results = list(results)
        self.order = order
        self.calls: list[AcceptanceGateConfig] = []

    async def verify(self, config: AcceptanceGateConfig) -> AcceptanceGateResult:
        self.calls.append(config)
        if self.order is not None:
            self.order.append(f"gate:{len(self.calls)}")
        if len(self.results) > 1:
            return self.results.pop(0)
        return self.results[0]


class FakeUow:
    """假的工作单元：只提供 session_events 事件写入器。"""

    def __init__(self, sink: FakeEventSink) -> None:
        self.session_events = sink


# ===================== 1. domain 门禁：退出码语义 =====================


class AcceptanceGateDomainTest(unittest.IsolatedAsyncioTestCase):
    """验收门禁 domain 逻辑：退出码语义是硬约束。"""

    def make_gate(self, runner: FakeRunner) -> AcceptanceGate:
        return AcceptanceGate(runner)

    async def test_exit_zero_passes(self) -> None:
        """exit 0 → passed=True，且带非空 reason 与输出摘要。"""
        runner = FakeRunner(CommandOutcome(exit_code=0, output="all green", duration_ms=12))
        gate = self.make_gate(runner)

        result = await gate.verify(AcceptanceGateConfig(command="pytest -q"))

        self.assertTrue(result.passed)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.command, "pytest -q")
        self.assertEqual(result.output_digest, "all green")
        self.assertEqual(result.duration_ms, 12)
        self.assertTrue(result.reason)
        self.assertEqual(runner.calls, [("pytest -q", 600, "")])

    async def test_nonzero_exit_code_fails_with_reason(self) -> None:
        """exit 1 → passed=False，reason 写明退出码。"""
        runner = FakeRunner(
            CommandOutcome(exit_code=1, output="FAIL: 1 test failed", duration_ms=33)
        )

        result = await self.make_gate(runner).verify(
            AcceptanceGateConfig(command="pytest -q")
        )

        self.assertFalse(result.passed)
        self.assertEqual(result.exit_code, 1)
        self.assertIn("exit_code=1", result.reason)
        self.assertEqual(result.output_digest, "FAIL: 1 test failed")

    async def test_timeout_outcome_is_failure(self) -> None:
        """超时（exit_code=None + error）→ passed=False，reason 说明超时。"""
        runner = FakeRunner(
            CommandOutcome(
                exit_code=None,
                output="partial output",
                error="验收命令超时（timeout_seconds=600）",
                duration_ms=600_000,
            )
        )

        result = await self.make_gate(runner).verify(
            AcceptanceGateConfig(command="pytest -q")
        )

        self.assertFalse(result.passed)
        self.assertIsNone(result.exit_code)
        self.assertIn("超时", result.reason)

    async def test_missing_command_is_failure(self) -> None:
        """命令不存在（runner 抛异常）→ passed=False，reason 非空。"""
        runner = FakeRunner(error=FileNotFoundError("pytest: command not found"))

        result = await self.make_gate(runner).verify(
            AcceptanceGateConfig(command="pytest -q")
        )

        self.assertFalse(result.passed)
        self.assertIsNone(result.exit_code)
        self.assertTrue(result.reason)
        self.assertIn("无法执行", result.reason)

    async def test_empty_command_is_failure(self) -> None:
        """验收命令为空 → 直接不通过，不触碰 runner。"""
        runner = FakeRunner()

        result = await self.make_gate(runner).verify(AcceptanceGateConfig(command="   "))

        self.assertFalse(result.passed)
        self.assertIsNone(result.exit_code)
        self.assertTrue(result.reason)
        self.assertEqual(runner.calls, [])

    async def test_output_digest_truncated_within_limit(self) -> None:
        """输出摘要必须 ≤2000 字符（含截断标记）。"""
        runner = FakeRunner(
            CommandOutcome(exit_code=0, output="x" * 5000, duration_ms=1)
        )

        result = await self.make_gate(runner).verify(
            AcceptanceGateConfig(command="pytest -q")
        )

        self.assertTrue(result.passed)
        self.assertLessEqual(len(result.output_digest), OUTPUT_DIGEST_LIMIT)
        self.assertTrue(result.output_digest.startswith("xxx"))
        self.assertTrue(result.output_digest.endswith("(已截断)"))

    async def test_custom_success_exit_codes(self) -> None:
        """success_exit_codes 可配置：exit 2 命中 (0, 2) → passed=True。"""
        runner = FakeRunner(CommandOutcome(exit_code=2, output="no tests"))

        result = await self.make_gate(runner).verify(
            AcceptanceGateConfig(command="pytest -q", success_exit_codes=(0, 2))
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.exit_code, 2)


# ===================== 2. plan 配置解析（向后兼容） =====================


class GateConfigFromPlanTest(unittest.TestCase):
    """gate_config_from_plan：从 plan payload 读取 acceptance 配置。"""

    def test_plan_without_acceptance_returns_none(self) -> None:
        """老计划没有 acceptance 字段 → 返回 None（不执行门禁，向后兼容）。"""
        self.assertIsNone(gate_config_from_plan(plan_payload(1)))

    def test_acceptance_without_command_returns_none(self) -> None:
        """acceptance 缺少 command（或 command 为空）→ 返回 None。"""
        plan = plan_payload(1)
        plan["acceptance"] = {"timeout_seconds": 30}
        self.assertIsNone(gate_config_from_plan(plan))

        plan["acceptance"] = {"command": "   "}
        self.assertIsNone(gate_config_from_plan(plan))

    def test_parses_command_timeout_and_working_dir(self) -> None:
        """command/timeout_seconds/working_dir 解析正确，command 去除首尾空白。"""
        plan = plan_payload(1)
        plan["acceptance"] = {
            "command": " pytest -q ",
            "timeout_seconds": 30,
            "working_dir": "/workspace",
        }

        config = gate_config_from_plan(plan)

        self.assertIsNotNone(config)
        self.assertEqual(config.command, "pytest -q")
        self.assertEqual(config.timeout_seconds, 30)
        self.assertEqual(config.working_dir, "/workspace")
        self.assertEqual(config.success_exit_codes, (0,))

    def test_invalid_timeout_falls_back_to_default(self) -> None:
        """timeout_seconds 非法（负数/布尔）→ 回落到默认 600。"""
        plan = plan_payload(1)
        plan["acceptance"] = {"command": "pytest -q", "timeout_seconds": -1}
        self.assertEqual(gate_config_from_plan(plan).timeout_seconds, 600)

        plan["acceptance"] = {"command": "pytest -q", "timeout_seconds": True}
        self.assertEqual(gate_config_from_plan(plan).timeout_seconds, 600)

    def test_success_exit_codes_parsed(self) -> None:
        """success_exit_codes 列表解析为元组，非法项被过滤。"""
        plan = plan_payload(1)
        plan["acceptance"] = {"command": "pytest -q", "success_exit_codes": [0, 2, "bad", True]}

        config = gate_config_from_plan(plan)

        self.assertEqual(config.success_exit_codes, (0, 2))


# ===================== 3. 应用服务：审计事件写入 =====================


class AcceptanceGateServiceTest(unittest.IsolatedAsyncioTestCase):
    """AcceptanceGateService：执行门禁并写审计事件。"""

    async def test_run_gate_writes_started_and_finished_events(self) -> None:
        """执行门禁 → 写 started/finished 两个审计事件，payload 含结果字段。"""
        order: list[str] = []
        sink = FakeEventSink(order)
        service = AcceptanceGateService(FakeUow(sink), FakeGate([gate_result(False, 1)]))

        result = await service.run_gate(uuid4(), uuid4(), plan_with_gate())

        self.assertEqual(
            order,
            [
                "event:acceptance_gate_started",
                "event:acceptance_gate_finished",
            ],
        )
        self.assertFalse(result.passed)
        started, finished = sink.events
        self.assertEqual(started.type, SessionEventType.acceptance_gate_started)
        self.assertEqual(finished.type, SessionEventType.acceptance_gate_finished)
        self.assertEqual(started.payload["command"], "pytest -q")
        for key in ("command", "exit_code", "passed", "output_digest", "duration_ms"):
            self.assertIn(key, finished.payload)
        self.assertEqual(finished.payload["exit_code"], 1)
        self.assertIs(finished.payload["passed"], False)

    async def test_run_gate_skips_when_plan_has_no_acceptance(self) -> None:
        """plan 无 acceptance 字段 → 不执行门禁、不写事件，返回通过（向后兼容）。"""

        def exploding_verify(config):  # 门禁一旦被调用即失败
            raise AssertionError("老计划不应执行门禁")

        order: list[str] = []
        sink = FakeEventSink(order)
        gate = SimpleNamespace(verify=exploding_verify)
        service = AcceptanceGateService(FakeUow(sink), gate)

        result = await service.run_gate(uuid4(), uuid4(), plan_payload(1))

        self.assertTrue(result.passed)
        self.assertIsNone(result.exit_code)
        self.assertEqual(order, [])

    async def test_run_gate_uses_explicit_config_and_custom_event_writer(self) -> None:
        """显式 config 优先于 plan；自定义 event_writer 生效。"""
        order: list[str] = []
        custom_sink = FakeEventSink(order)
        service = AcceptanceGateService(
            FakeUow(FakeEventSink([])),
            FakeGate([gate_result(True, 0)]),
            event_writer=custom_sink,
        )
        config = AcceptanceGateConfig(command="uv run pytest -q", timeout_seconds=30)

        result = await service.run_gate(uuid4(), uuid4(), plan_payload(1), config)

        self.assertTrue(result.passed)
        self.assertEqual(
            order,
            [
                "event:acceptance_gate_started",
                "event:acceptance_gate_finished",
            ],
        )
        self.assertEqual(custom_sink.events[1].payload["command"], "uv run pytest -q")


# ===================== 4. 状态机接入 =====================


class MachineAcceptanceGateTest(unittest.IsolatedAsyncioTestCase):
    """AgentExecutionMachine + 验收门禁：gate 通过才 summarize，失败走重试。"""

    async def collect(self, machine, plan):
        session_id = uuid4()
        context = AgentExecutionContext(empty_memory_context(), "agent context")
        return [item async for item in machine.stream(session_id, plan, context)]

    def build_machine(self, order, gate, statuses, actions, max_retries=2):
        return AgentExecutionMachine(
            executor=FakeExecutor(statuses, order),
            critic=FakeCritic(actions, order),
            summarizer=FakeSummarizer(order),
            event_sink=FakeEventSink(order),
            router=AgentStateRouter(),
            acceptance_gate=gate,
            acceptance_gate_max_retries=max_retries,
        )

    async def test_gate_pass_allows_summarize(self) -> None:
        """gate 通过 → 正常进入 summarize，且 gate 事件在 summarize 之前。"""
        order: list[str] = []
        gate = FakeGate([gate_result(True, 0)], order)
        machine = self.build_machine(
            order,
            gate,
            [ToolInvocationStatus.succeeded],
            [ReflectionAction.accept],
        )

        items = await self.collect(machine, plan_with_gate())

        self.assertEqual(len(gate.calls), 1)
        self.assertEqual(gate.calls[0].command, "pytest -q")
        self.assertEqual(gate.calls[0].timeout_seconds, 600)
        event_types = [item.type for item in items if isinstance(item, SessionEvent)]
        self.assertIn(SessionEventType.acceptance_gate_started, event_types)
        self.assertIn(SessionEventType.acceptance_gate_finished, event_types)
        self.assertLess(
            event_types.index(SessionEventType.acceptance_gate_finished),
            event_types.index(SessionEventType.task_done),
        )
        self.assertEqual(event_types[-1], SessionEventType.task_done)
        self.assertIn("summarize", order)
        finished = [
            event
            for event in items
            if isinstance(event, SessionEvent)
            and event.type is SessionEventType.acceptance_gate_finished
        ][0]
        self.assertIs(finished.payload["passed"], True)
        self.assertEqual(finished.payload["command"], "pytest -q")
        self.assertEqual(finished.payload["exit_code"], 0)
        self.assertEqual(finished.payload["duration_ms"], 12)
        self.assertIn("output_digest", finished.payload)

    async def test_gate_fail_retries_step_then_passes(self) -> None:
        """gate 连续失败 2 次（额度内）→ 每次重试当前步骤；第 3 次通过 → summarize。"""
        order: list[str] = []
        gate = FakeGate(
            [gate_result(False, 1), gate_result(False, 1), gate_result(True, 0)],
            order,
        )
        executor_statuses = [ToolInvocationStatus.succeeded] * 3
        machine = self.build_machine(
            order,
            gate,
            executor_statuses,
            [ReflectionAction.accept] * 3,
            max_retries=2,
        )

        items = await self.collect(machine, plan_with_gate())

        self.assertEqual(len(gate.calls), 3)
        event_types = [item.type for item in items if isinstance(item, SessionEvent)]
        self.assertEqual(event_types[-1], SessionEventType.task_done)
        self.assertIn("summarize", order)
        reflected = [
            event
            for event in items
            if isinstance(event, SessionEvent)
            and event.type is SessionEventType.step_reflected
        ]
        # 两次门禁失败产生的 retry 反射，reason 写明 exit_code
        gate_retries = [
            event for event in reflected if event.payload.get("reason") == "acceptance gate failed: exit_code=1"
        ]
        self.assertEqual(len(gate_retries), 2)
        self.assertTrue(
            all(event.payload["action"] == "retry" for event in gate_retries)
        )

    async def test_gate_fail_exhausts_retries_then_fails(self) -> None:
        """gate 一直失败 → 最多重试 2 次后 failed，不进 summarize。"""
        order: list[str] = []
        gate = FakeGate([gate_result(False, 1)], order)
        executor = FakeExecutor([ToolInvocationStatus.succeeded] * 3, order)
        machine = AgentExecutionMachine(
            executor=executor,
            critic=FakeCritic([ReflectionAction.accept] * 3, order),
            summarizer=FakeSummarizer(order),
            event_sink=FakeEventSink(order),
            router=AgentStateRouter(),
            acceptance_gate=gate,
            acceptance_gate_max_retries=2,
        )

        items = await self.collect(machine, plan_with_gate())

        # 1 次初始 + 2 次重试 = 3 次门禁执行，步骤按 attempt 1/2/3 重跑
        self.assertEqual(len(gate.calls), 3)
        self.assertEqual(
            [(request.step_index, request.attempt) for request in executor.requests],
            [(0, 1), (0, 2), (0, 3)],
        )
        event_types = [item.type for item in items if isinstance(item, SessionEvent)]
        self.assertNotIn("summarize", order)
        self.assertNotIn(SessionEventType.task_done, event_types)
        self.assertEqual(
            event_types[-3:],
            [
                SessionEventType.step_reflected,
                SessionEventType.step_failed,
                SessionEventType.task_error,
            ],
        )
        self.assertEqual(items[-1].payload["phase"], "failed")
        # 三次 finished 事件全部 passed=False
        finished = [
            event
            for event in items
            if isinstance(event, SessionEvent)
            and event.type is SessionEventType.acceptance_gate_finished
        ]
        self.assertEqual(len(finished), 3)
        self.assertTrue(all(event.payload["passed"] is False for event in finished))
        # 最后一次反射是 fail，且 reason 写明 exit_code
        self.assertEqual(finished[-1].payload["reason"].count("exit_code"), 1)
        last_reflected = [
            event
            for event in items
            if isinstance(event, SessionEvent)
            and event.type is SessionEventType.step_reflected
        ][-1]
        self.assertEqual(last_reflected.payload["action"], "fail")
        self.assertEqual(
            last_reflected.payload["reason"], "acceptance gate failed: exit_code=1"
        )

    async def test_plan_without_acceptance_never_runs_gate(self) -> None:
        """plan 无 acceptance 字段 → 门禁根本不执行（向后兼容），直接 summarize。"""
        order: list[str] = []
        gate = FakeGate([gate_result(False, 1)], order)
        machine = self.build_machine(
            order,
            gate,
            [ToolInvocationStatus.succeeded],
            [ReflectionAction.accept],
        )

        items = await self.collect(machine, plan_payload(1))

        self.assertEqual(gate.calls, [])
        event_types = [item.type for item in items if isinstance(item, SessionEvent)]
        self.assertNotIn(SessionEventType.acceptance_gate_started, event_types)
        self.assertNotIn(SessionEventType.acceptance_gate_finished, event_types)
        self.assertEqual(event_types[-1], SessionEventType.task_done)
        self.assertIn("summarize", order)

    async def test_machine_without_gate_skips_gate(self) -> None:
        """未注入 gate（默认 None）→ 即使 plan 带 acceptance 也不执行门禁。"""
        order: list[str] = []
        machine = AgentExecutionMachine(
            executor=FakeExecutor([ToolInvocationStatus.succeeded], order),
            critic=FakeCritic([ReflectionAction.accept], order),
            summarizer=FakeSummarizer(order),
            event_sink=FakeEventSink(order),
            router=AgentStateRouter(),
        )

        items = await self.collect(machine, plan_with_gate())

        event_types = [item.type for item in items if isinstance(item, SessionEvent)]
        self.assertNotIn(SessionEventType.acceptance_gate_started, event_types)
        self.assertEqual(event_types[-1], SessionEventType.task_done)
        self.assertIn("summarize", order)

    async def test_allow_retry_false_fails_immediately(self) -> None:
        """plan 声明 allow_retry=False → 门禁首次失败即 failed，不重试。"""
        order: list[str] = []
        gate = FakeGate([gate_result(False, 1)], order)
        machine = self.build_machine(
            order,
            gate,
            [ToolInvocationStatus.succeeded],
            [ReflectionAction.accept],
            max_retries=2,
        )

        items = await self.collect(machine, plan_with_gate(allow_retry=False))

        self.assertEqual(len(gate.calls), 1)
        self.assertNotIn("summarize", order)
        event_types = [item.type for item in items if isinstance(item, SessionEvent)]
        self.assertEqual(event_types[-1], SessionEventType.task_error)
        self.assertEqual(items[-1].payload["phase"], "failed")


if __name__ == "__main__":
    unittest.main()
