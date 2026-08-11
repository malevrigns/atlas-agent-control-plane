import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

from app.application.react_agent_service import ReActAgentService
from app.application.react_step_executor import (
    ReActStepExecutor,
    StepExecutionRequest,
)
from app.domain.agent_core.tools import ToolInvocationStatus
from app.domain.context_engineering.entities import MemoryContext
from app.domain.sessions.entities import (
    MessageRole,
    SessionEvent,
    SessionEventType,
    SessionStatus,
)


class FakeSessionEventRepository:
    def __init__(self, events: list[SessionEvent] | None = None) -> None:
        self.events = list(events or ())

    async def add(
        self,
        *,
        session_id: UUID,
        event_type: SessionEventType,
        payload: dict,
    ) -> SessionEvent:
        event = SessionEvent(
            id=uuid4(),
            session_id=session_id,
            type=event_type,
            payload=payload,
            created_at=datetime.now(UTC),
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


class FakeSessionMessageRepository:
    async def add_assistant_message(self, *, session_id: UUID, content: str):
        return SimpleNamespace(id=uuid4(), role=MessageRole.assistant, content=content)


class FakeUnitOfWork:
    def __init__(self, events: list[SessionEvent] | None = None) -> None:
        self.session_events = FakeSessionEventRepository(events)
        self.sessions = FakeSessionRepository()
        self.session_messages = FakeSessionMessageRepository()
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


class StubReActAgentService(ReActAgentService):
    def __init__(
        self,
        status: ToolInvocationStatus,
        uow: FakeUnitOfWork | None = None,
    ) -> None:
        super().__init__(uow or FakeUnitOfWork())
        self.status = status
        self.tool_calls = 0

    async def _call_tool_for_step(self, **kwargs) -> dict:
        self.tool_calls += 1
        return {
            "tool_name": "stub_tool",
            "arguments": {},
            "output": f"tool ended with {self.status.value}",
            "invocation_id": "invocation-1",
            "status": self.status.value,
            "risk_level": "low",
            "artifact_id": None,
            "duration_ms": 1,
            "audit": {},
        }

    async def _sync_session_files_to_sandbox(self, session_id: UUID) -> None:
        return None

    async def _build_final_answer(self, plan: dict, events: list[SessionEvent]) -> str:
        return "final answer"


class FakeContextEngineeringService:
    def __init__(self, uow: FakeUnitOfWork) -> None:
        self.uow = uow

    async def build_snapshot(self, session_id: UUID, task: str):
        return SimpleNamespace(memory_context=empty_memory_context())

    @staticmethod
    def render_for_agent(snapshot: object) -> str:
        return ""


class FakeLLMService:
    async def chat_stream(self, *args, **kwargs):
        yield SimpleNamespace(kind="answer", text="final answer")


def empty_memory_context() -> MemoryContext:
    return MemoryContext(
        query="",
        items=[],
        candidate_count=0,
        omitted_count=0,
        total_chars=0,
        max_chars=0,
    )


def build_plan_event(session_id: UUID) -> SessionEvent:
    return SessionEvent(
        id=uuid4(),
        session_id=session_id,
        type=SessionEventType.plan_created,
        payload={
            "id": "plan-1",
            "goal": "test goal",
            "steps": [
                {"id": "step-1", "title": "first step"},
                {"id": "step-2", "title": "second step"},
            ],
        },
        created_at=datetime.now(UTC),
    )


class StepFailureSemanticsTest(unittest.IsolatedAsyncioTestCase):
    async def execute(self, status: ToolInvocationStatus) -> list[SessionEvent]:
        service = StubReActAgentService(status)
        return await service._execute_step(
            session_id=uuid4(),
            plan={"id": "plan-1", "goal": "test goal"},
            step={"id": "step-1", "title": "test step"},
            index=1,
            memory_context=empty_memory_context(),
            agent_context="",
            step_history=[],
        )

    async def test_final_failure_statuses_emit_step_failed(self) -> None:
        failure_statuses = (
            ToolInvocationStatus.denied,
            ToolInvocationStatus.failed,
            ToolInvocationStatus.timed_out,
        )
        for status in failure_statuses:
            with self.subTest(status=status):
                events = await self.execute(status)
                event_types = [event.type for event in events]

                self.assertEqual(
                    event_types,
                    [
                        SessionEventType.step_started,
                        SessionEventType.tool_called,
                        SessionEventType.step_failed,
                    ],
                )
                self.assertNotIn(SessionEventType.step_completed, event_types)

    async def test_approval_required_emits_step_blocked(self) -> None:
        events = await self.execute(ToolInvocationStatus.approval_required)

        self.assertEqual(
            [event.type for event in events],
            [
                SessionEventType.step_started,
                SessionEventType.tool_called,
                SessionEventType.step_blocked,
            ],
        )

    async def test_deduplicated_emits_step_completed(self) -> None:
        events = await self.execute(ToolInvocationStatus.deduplicated)

        self.assertEqual(
            [event.type for event in events],
            [
                SessionEventType.step_started,
                SessionEventType.tool_called,
                SessionEventType.step_completed,
            ],
        )


class ReActStepExecutorTest(unittest.IsolatedAsyncioTestCase):
    async def test_execute_emits_non_terminal_events_and_observation(self) -> None:
        uow = FakeUnitOfWork()

        async def call_tool(**kwargs) -> dict:
            return {
                "tool_name": "stub_tool",
                "arguments": {},
                "output": "cached output",
                "invocation_id": "invocation-1",
                "status": ToolInvocationStatus.deduplicated.value,
                "risk_level": "low",
                "artifact_id": None,
                "duration_ms": 1,
                "audit": {},
            }

        executor = ReActStepExecutor(uow=uow, tool_caller=call_tool)
        request = StepExecutionRequest(
            session_id=uuid4(),
            plan={"id": "plan-1", "goal": "test goal"},
            step={"id": "step-1", "title": "test step"},
            step_index=0,
            memory_context=empty_memory_context(),
            agent_context="",
            step_history=(),
        )

        outcome = await executor.execute(request)

        self.assertEqual(
            [event.type for event in outcome.events],
            [SessionEventType.step_started, SessionEventType.tool_called],
        )
        self.assertEqual(outcome.observation.status, ToolInvocationStatus.deduplicated)
        self.assertEqual(outcome.observation.output, "cached output")
        history = executor.format_step_history(
            step_index=request.step_index,
            step=request.step,
            events=outcome.events,
        )
        self.assertNotIn("失败", history)


if __name__ == "__main__":
    unittest.main()
