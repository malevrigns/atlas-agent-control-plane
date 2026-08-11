import unittest
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.application.react_agent_service import ReActAgentService
from app.application.react_step_executor import (
    ReActStepExecutor,
    StepExecutionRequest,
)
from app.domain.agent_core.tools import ToolInvocationStatus
from app.domain.context_engineering.entities import MemoryContext
from app.domain.sessions.entities import SessionEvent, SessionEventType


class FakeSessionEventRepository:
    def __init__(self) -> None:
        self.events: list[SessionEvent] = []

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


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.session_events = FakeSessionEventRepository()


class StubReActAgentService(ReActAgentService):
    def __init__(self, status: ToolInvocationStatus) -> None:
        super().__init__(FakeUnitOfWork())
        self.status = status

    async def _call_tool_for_step(self, **kwargs) -> dict:
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


def empty_memory_context() -> MemoryContext:
    return MemoryContext(
        query="",
        items=[],
        candidate_count=0,
        omitted_count=0,
        total_chars=0,
        max_chars=0,
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
