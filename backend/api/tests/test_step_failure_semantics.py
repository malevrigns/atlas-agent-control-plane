import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

from app.application.react_step_executor import ReActStepExecutor, StepExecutionRequest
from app.domain.agent_core.tools import ToolInvocationStatus
from app.domain.context_engineering.entities import MemoryContext
from app.domain.sessions.entities import SessionEvent, SessionEventType, SessionStatus


class FakeSessionEventRepository:
    def __init__(self, events: list[SessionEvent] | None = None) -> None:
        self.events = list(events or ())

    async def add(self, *, session_id, event_type, payload) -> SessionEvent:
        event = SessionEvent(
            uuid4(), session_id, event_type, payload, datetime.now(UTC)
        )
        self.events.append(event)
        return event

    async def list_by_session(self, session_id: UUID) -> list[SessionEvent]:
        return [event for event in self.events if event.session_id == session_id]


class FakeSessionRepository:
    def __init__(self) -> None:
        self.status = SessionStatus.idle

    async def get(self, session_id: UUID) -> object:
        return object()

    async def update_status(self, session_id: UUID, status: str) -> None:
        self.status = SessionStatus(status)

    async def touch(self, session_id: UUID) -> None:
        return None


class FakeUnitOfWork:
    def __init__(self, events: list[SessionEvent] | None = None) -> None:
        self.session_events = FakeSessionEventRepository(events)
        self.sessions = FakeSessionRepository()
        self.session_messages = SimpleNamespace()
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


def empty_memory_context() -> MemoryContext:
    return MemoryContext("", [], 0, 0, 0, 0)


def build_plan_event(session_id: UUID) -> SessionEvent:
    steps = [
        {
            "id": str(uuid4()),
            "title": f"Step {index + 1}",
            "description": "Execute the test step.",
            "expected_output": "A test result.",
            "status": "pending",
        }
        for index in range(2)
    ]
    return SessionEvent(
        uuid4(),
        session_id,
        SessionEventType.plan_created,
        {"id": str(uuid4()), "goal": "test goal", "steps": steps},
        datetime.now(UTC),
    )


class ReActStepExecutorTest(unittest.IsolatedAsyncioTestCase):
    async def execute(self, status: ToolInvocationStatus):
        async def call_tool(**kwargs) -> dict:
            return {
                "tool_name": "stub_tool",
                "arguments": {},
                "output": f"tool ended with {status.value}",
                "status": status.value,
            }

        uow = FakeUnitOfWork()
        executor = ReActStepExecutor(uow=uow, tool_caller=call_tool)
        request = StepExecutionRequest(
            session_id=uuid4(),
            plan={"id": "plan-1", "goal": "test goal"},
            step={"id": "step-1", "title": "test step"},
            step_index=0,
            attempt=1,
            memory_context=empty_memory_context(),
            agent_context="",
            step_history=(),
        )
        return executor, request, await executor.execute(request)

    async def test_final_failures_remain_observations_without_terminal_event(self) -> None:
        for status in (
            ToolInvocationStatus.denied,
            ToolInvocationStatus.failed,
            ToolInvocationStatus.timed_out,
        ):
            with self.subTest(status=status):
                _, _, outcome = await self.execute(status)
                self.assertEqual(outcome.observation.status, status)
                self.assertEqual(
                    [event.type for event in outcome.events],
                    [SessionEventType.step_started, SessionEventType.tool_called],
                )

    async def test_approval_required_remains_a_blocking_observation(self) -> None:
        _, _, outcome = await self.execute(ToolInvocationStatus.approval_required)
        self.assertEqual(
            outcome.observation.status, ToolInvocationStatus.approval_required
        )

    async def test_deduplicated_history_is_successful(self) -> None:
        executor, request, outcome = await self.execute(ToolInvocationStatus.deduplicated)
        history = executor.format_step_history(
            step_index=request.step_index,
            step=request.step,
            events=outcome.events,
        )
        self.assertNotIn("失败", history)


if __name__ == "__main__":
    unittest.main()
