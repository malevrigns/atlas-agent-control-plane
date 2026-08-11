import unittest
from copy import deepcopy
from uuid import UUID, uuid4

from app.application.agent_execution_machine import (
    AgentExecutionContext,
    AgentExecutionMachine,
)
from app.application.react_step_executor import ReActStepExecutor, StepExecutionRequest
from app.application.tool_runtime import ToolRuntime
from app.domain.agent_core.tools import (
    ToolInvocationStatus,
    ToolRegistry,
    agent_tool,
)
from app.domain.agent_runtime.entities import ReflectionAction
from app.domain.agent_runtime.router import AgentStateRouter
from app.domain.context_engineering.entities import MemoryContext
from app.domain.sessions.entities import SessionEventType
from tests.test_agent_execution_machine import (
    FakeCritic,
    FakeEventSink,
    FakeExecutor,
    FakeReplanner,
    FakeSummarizer,
    empty_memory_context,
    plan_payload,
)


def build_request(
    run_id: UUID,
    plan_revision: int,
) -> StepExecutionRequest:
    step_id = str(uuid4())
    return StepExecutionRequest(
        session_id=uuid4(),
        run_id=run_id,
        plan_revision=plan_revision,
        plan={"id": "plan-1"},
        step={"id": step_id, "title": "step"},
        step_index=0,
        attempt=1,
        memory_context=MemoryContext("", [], 0, 0, 0, 0),
        agent_context="",
        step_history=(),
    )


def build_runtime() -> tuple[ToolRuntime, list[str]]:
    calls: list[str] = []

    @agent_tool(
        name="revision_echo",
        description="record text",
        parameter_descriptions={"text": "text"},
    )
    def revision_echo(text: str) -> str:
        calls.append(text)
        return text

    registry = ToolRegistry()
    registry.register(revision_echo)
    return ToolRuntime(registry), calls


async def execute_pair(
    first: StepExecutionRequest,
    second: StepExecutionRequest,
    outputs: tuple[str, str],
) -> tuple[list[ToolInvocationStatus], list[str]]:
    runtime, calls = build_runtime()
    statuses = []
    for request, output in zip((first, second), outputs, strict=True):
        context = ReActStepExecutor._tool_execution_context(request)
        result = await runtime.execute("revision_echo", {"text": output}, context)
        statuses.append(result.status)
    return statuses, calls


class ReplanRevisionTest(unittest.IsolatedAsyncioTestCase):
    async def test_machine_creates_a_new_run_id_for_each_stream(self) -> None:
        order: list[str] = []
        executor = FakeExecutor(
            [ToolInvocationStatus.succeeded, ToolInvocationStatus.succeeded],
            order,
        )
        machine = AgentExecutionMachine(
            executor=executor,
            critic=FakeCritic(
                [ReflectionAction.accept, ReflectionAction.accept], order
            ),
            summarizer=FakeSummarizer(order),
            event_sink=FakeEventSink(order),
            router=AgentStateRouter(),
        )
        session_id = uuid4()
        plan = plan_payload(1)
        context = AgentExecutionContext(empty_memory_context(), "")

        _ = [item async for item in machine.stream(session_id, plan, context)]
        _ = [item async for item in machine.stream(session_id, plan, context)]

        self.assertNotEqual(executor.requests[0].run_id, executor.requests[1].run_id)
        self.assertEqual([request.plan_revision for request in executor.requests], [0, 0])

    async def test_new_run_does_not_reuse_previous_invocation(self) -> None:
        first = build_request(uuid4(), 0)
        second = build_request(uuid4(), 0)
        shared_step = first.step
        second = StepExecutionRequest(
            session_id=first.session_id,
            run_id=second.run_id,
            plan_revision=0,
            plan=first.plan,
            step=shared_step,
            step_index=0,
            attempt=1,
            memory_context=first.memory_context,
            agent_context="",
            step_history=(),
        )

        statuses, calls = await execute_pair(first, second, ("same", "same"))

        self.assertEqual(statuses, [ToolInvocationStatus.succeeded] * 2)
        self.assertEqual(calls, ["same", "same"])

    async def test_replan_revision_separates_same_and_changed_arguments(self) -> None:
        run_id = uuid4()
        for outputs in (("same", "same"), ("first", "second")):
            with self.subTest(outputs=outputs):
                first = build_request(run_id, 0)
                second = StepExecutionRequest(
                    session_id=first.session_id,
                    run_id=run_id,
                    plan_revision=1,
                    plan=first.plan,
                    step=first.step,
                    step_index=0,
                    attempt=1,
                    memory_context=first.memory_context,
                    agent_context="",
                    step_history=(),
                )

                statuses, calls = await execute_pair(first, second, outputs)

                self.assertEqual(statuses, [ToolInvocationStatus.succeeded] * 2)
                self.assertEqual(calls, list(outputs))

    async def test_machine_persists_revision_and_preserves_run_id(self) -> None:
        order: list[str] = []
        initial = plan_payload(1)
        replacement = deepcopy(initial)
        executor = FakeExecutor(
            [ToolInvocationStatus.succeeded, ToolInvocationStatus.succeeded],
            order,
        )
        sink = FakeEventSink(order)
        machine = AgentExecutionMachine(
            executor=executor,
            critic=FakeCritic(
                [ReflectionAction.replan, ReflectionAction.accept], order
            ),
            summarizer=FakeSummarizer(order),
            event_sink=sink,
            replanner=FakeReplanner(replacement),
            router=AgentStateRouter(),
        )
        context = AgentExecutionContext(empty_memory_context(), "")

        _ = [item async for item in machine.stream(uuid4(), initial, context)]

        self.assertEqual([request.plan_revision for request in executor.requests], [0, 1])
        self.assertEqual(len({request.run_id for request in executor.requests}), 1)
        plan_event = next(
            event for event in sink.events if event.type is SessionEventType.plan_created
        )
        self.assertEqual(plan_event.payload["plan_revision"], 1)
        self.assertEqual(
            plan_event.payload["run_id"],
            str(executor.requests[0].run_id),
        )
        step_events = [
            event
            for event in sink.events
            if event.type
            in {SessionEventType.step_reflected, SessionEventType.step_completed}
        ]
        self.assertEqual(
            {event.payload["run_id"] for event in step_events},
            {str(executor.requests[0].run_id)},
        )
        self.assertEqual(
            {event.payload["plan_revision"] for event in step_events},
            {0, 1},
        )


if __name__ == "__main__":
    unittest.main()
