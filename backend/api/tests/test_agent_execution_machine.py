import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

from app.application.agent_execution_machine import (
    AgentExecutionContext,
    AgentExecutionMachine,
)
from app.application.agent_summary_service import AgentSummaryResult
from app.application.react_step_executor import StepExecutionRequest
from app.core.exceptions import AppException
from app.domain.agent_core.tools import ToolInvocationStatus
from app.domain.agent_runtime.entities import Reflection, ReflectionAction
from app.domain.agent_runtime.router import AgentStateRouter
from app.domain.context_engineering.entities import MemoryContext
from app.domain.sessions.entities import MessageRole, SessionEvent, SessionEventType


def empty_memory_context() -> MemoryContext:
    return MemoryContext("", [], 0, 0, 0, 0)


def plan_payload(step_count: int = 2) -> dict[str, object]:
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


def make_event(
    session_id: UUID,
    event_type: SessionEventType,
    payload: dict[str, object],
) -> SessionEvent:
    return SessionEvent(uuid4(), session_id, event_type, payload, datetime.now(UTC))


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
        from app.application.react_step_executor import StepExecutionOutcome
        from app.domain.agent_runtime.entities import StepObservation

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


class FakeReplanner:
    def __init__(self, replacement: dict[str, object]) -> None:
        self.replacement = replacement
        self.states = []

    async def replan(self, state):
        self.states.append(state)
        return self.replacement


class AgentExecutionMachineTest(unittest.IsolatedAsyncioTestCase):
    async def collect(self, machine, plan):
        session_id = uuid4()
        context = AgentExecutionContext(empty_memory_context(), "agent context")
        return [item async for item in machine.stream(session_id, plan, context)]

    async def test_success_executes_reflects_and_completes_in_order(self) -> None:
        order: list[str] = []
        sink = FakeEventSink(order)
        machine = AgentExecutionMachine(
            executor=FakeExecutor(
                [ToolInvocationStatus.succeeded, ToolInvocationStatus.deduplicated],
                order,
            ),
            critic=FakeCritic(
                [ReflectionAction.accept, ReflectionAction.accept], order
            ),
            summarizer=FakeSummarizer(order),
            event_sink=sink,
            router=AgentStateRouter(),
        )

        plan = plan_payload()
        items = await self.collect(machine, plan)

        event_types = [item.type for item in items if isinstance(item, SessionEvent)]
        self.assertEqual(
            order,
            [
                "execute:0:1",
                "critic:Step 1",
                "event:step_reflected",
                "event:step_completed",
                "execute:1:1",
                "critic:Step 2",
                "event:step_reflected",
                "event:step_completed",
                "summarize",
                "event:task_done",
            ],
        )
        self.assertLess(
            event_types.index(SessionEventType.step_reflected),
            event_types.index(SessionEventType.step_completed),
        )
        self.assertEqual(event_types[-1], SessionEventType.task_done)
        reflected = [item for item in items if getattr(item, "type", None) is SessionEventType.step_reflected]
        completed = [item for item in items if getattr(item, "type", None) is SessionEventType.step_completed]
        self.assertEqual([event.payload["step_id"] for event in completed], [step["id"] for step in plan["steps"]])
        self.assertTrue(all(event.payload["plan_id"] == plan["id"] for event in reflected + completed))
        self.assertEqual(reflected[0].payload["status"], "succeeded")
        self.assertEqual(items[-1].payload["plan_id"], plan["id"])

    async def test_failed_observation_is_criticized_before_failed_terminal_events(self) -> None:
        order: list[str] = []
        sink = FakeEventSink(order)
        critic = FakeCritic([ReflectionAction.fail], order)
        machine = AgentExecutionMachine(
            executor=FakeExecutor([ToolInvocationStatus.denied], order),
            critic=critic,
            summarizer=FakeSummarizer(order),
            event_sink=sink,
            router=AgentStateRouter(),
        )

        items = await self.collect(machine, plan_payload(1))

        event_types = [item.type for item in items if isinstance(item, SessionEvent)]
        self.assertEqual(critic.calls[0][1].status, ToolInvocationStatus.denied)
        self.assertEqual(
            event_types[-3:],
            [
                SessionEventType.step_reflected,
                SessionEventType.step_failed,
                SessionEventType.task_error,
            ],
        )
        self.assertEqual(items[-1].payload["phase"], "failed")
        self.assertNotIn(SessionEventType.step_completed, event_types)
        self.assertNotIn(SessionEventType.task_done, event_types)
        self.assertNotIn("summarize", order)

    async def test_approval_required_blocks_without_calling_critic(self) -> None:
        order: list[str] = []
        critic = FakeCritic([], order)
        machine = AgentExecutionMachine(
            executor=FakeExecutor([ToolInvocationStatus.approval_required], order),
            critic=critic,
            summarizer=FakeSummarizer(order),
            event_sink=FakeEventSink(order),
            router=AgentStateRouter(),
        )

        items = await self.collect(machine, plan_payload(1))

        event_types = [item.type for item in items if isinstance(item, SessionEvent)]
        self.assertEqual(critic.calls, [])
        self.assertEqual(event_types[-1], SessionEventType.step_blocked)
        self.assertNotIn(SessionEventType.step_reflected, event_types)

    async def test_retry_reexecutes_same_step_with_incremented_attempt(self) -> None:
        order: list[str] = []
        executor = FakeExecutor(
            [ToolInvocationStatus.failed, ToolInvocationStatus.succeeded], order
        )
        machine = AgentExecutionMachine(
            executor=executor,
            critic=FakeCritic(
                [ReflectionAction.retry, ReflectionAction.accept], order
            ),
            summarizer=FakeSummarizer(order),
            event_sink=FakeEventSink(order),
            router=AgentStateRouter(),
        )

        await self.collect(machine, plan_payload(1))

        self.assertEqual(
            [(request.step_index, request.attempt) for request in executor.requests],
            [(0, 1), (0, 2)],
        )

    async def test_replan_invokes_injected_replanner_from_replanning_phase(self) -> None:
        order: list[str] = []
        replacement = plan_payload(1)
        replanner = FakeReplanner(replacement)
        sink = FakeEventSink(order)
        machine = AgentExecutionMachine(
            executor=FakeExecutor(
                [ToolInvocationStatus.succeeded, ToolInvocationStatus.succeeded], order
            ),
            critic=FakeCritic(
                [ReflectionAction.replan, ReflectionAction.accept], order
            ),
            summarizer=FakeSummarizer(order),
            event_sink=sink,
            replanner=replanner,
            router=AgentStateRouter(),
        )

        items = await self.collect(machine, plan_payload(1))

        self.assertEqual(len(replanner.states), 1)
        self.assertEqual(replanner.states[0].phase.value, "replanning")
        replanned = [
            item
            for item in items
            if isinstance(item, SessionEvent)
            and item.type is SessionEventType.plan_created
        ]
        self.assertEqual(len(replanned), 1)
        self.assertEqual((replanned[0].payload["plan_revision"], replanned[0].payload["run_id"]), (1, str(replanner.states[0].run_id)))
        self.assertEqual(replanned[0].payload["id"], replacement["id"])
        self.assertIn(replanned[0], sink.events)

    async def test_replan_without_replanner_raises_configuration_error(self) -> None:
        order: list[str] = []
        machine = AgentExecutionMachine(
            executor=FakeExecutor([ToolInvocationStatus.succeeded], order),
            critic=FakeCritic([ReflectionAction.replan], order),
            summarizer=FakeSummarizer(order),
            event_sink=FakeEventSink(order),
            router=AgentStateRouter(),
        )

        with self.assertRaisesRegex(AppException, "replanner is not configured"):
            await self.collect(machine, plan_payload(1))


if __name__ == "__main__":
    unittest.main()
