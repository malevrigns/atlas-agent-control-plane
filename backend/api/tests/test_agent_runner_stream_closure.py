import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

from app.application.agent_runner_service import AgentRunnerService
from app.domain.agent_core.tools import ToolInvocationStatus
from app.domain.agent_runtime.entities import ReflectionAction
from app.domain.sessions.entities import (
    MessageRole,
    SessionEvent,
    SessionEventType,
    SessionStatus,
)
from tests.test_react_entrypoint_terminal_semantics import build_terminal_service


class RunnerSessionRepository:
    def __init__(self, session_id: UUID) -> None:
        self.status = SessionStatus.idle
        self.session = SimpleNamespace(id=session_id, status=self.status)

    async def get(self, session_id: UUID):
        self.session.status = self.status
        return self.session

    async def update_status(self, session_id: UUID, status: str):
        self.status = SessionStatus(status)
        self.session.status = self.status
        return self.session

    async def touch(self, session_id: UUID) -> None:
        return None


class RunnerSessionService:
    def __init__(self, uow) -> None:
        self.uow = uow

    async def mark_running(self, session_id: UUID):
        session = await self.uow.sessions.update_status(
            session_id, SessionStatus.running.value
        )
        await self.uow.commit()
        return session

    async def create_user_message(self, session_id: UUID, content: str):
        message = SimpleNamespace(
            id=uuid4(),
            session_id=session_id,
            role=MessageRole.user,
            content=content,
            created_at=datetime.now(UTC),
        )
        event = await self.uow.session_events.add(
            session_id=session_id,
            event_type=SessionEventType.message_created,
            payload={"message_id": str(message.id), "role": message.role.value},
        )
        await self.uow.commit()
        return message, event

    async def get_session(self, session_id: UUID):
        return await self.uow.sessions.get(session_id)


class ExistingPlanPlanner:
    def __init__(self, plan_event: SessionEvent) -> None:
        self.plan_event = plan_event

    async def stream_plan(self, session_id: UUID, task: str):
        yield "result", (object(), self.plan_event)


class PipelineOnlyDirectChat:
    model = object()
    context_service = object()

    async def stream(self, *, session_id: UUID, content: str):
        raise AssertionError("pipeline request entered direct chat")
        yield


class AgentRunnerStreamClosureTest(unittest.IsolatedAsyncioTestCase):
    def build_runner(self, status, action):
        session_id, react_service, uow, _, _ = build_terminal_service(status, action)
        uow.sessions = RunnerSessionRepository(session_id)
        runner = AgentRunnerService(
            session_service=RunnerSessionService(uow),
            planner_service=ExistingPlanPlanner(uow.session_events.events[0]),
            react_service=react_service,
            direct_chat_service=PipelineOnlyDirectChat(),
        )
        return session_id, runner, uow

    async def test_close_after_summary_message_keeps_completed_state(self) -> None:
        session_id, runner, uow = self.build_runner(
            ToolInvocationStatus.succeeded, ReflectionAction.accept
        )
        stream = runner.stream_user_message(
            session_id=session_id,
            content="https://sandbox.invalid/task",
        )
        message_count = 0

        async for item in stream:
            if item.name != SessionEventType.message_created.value:
                continue
            message_count += 1
            if message_count == 2:
                break
        await stream.aclose()

        event_types = [event.type for event in uow.session_events.events]
        self.assertEqual(event_types[-1], SessionEventType.task_done)
        self.assertEqual(uow.sessions.status, SessionStatus.idle)

    async def test_close_after_failed_reflection_keeps_failure_state(self) -> None:
        session_id, runner, uow = self.build_runner(
            ToolInvocationStatus.failed, ReflectionAction.fail
        )
        stream = runner.stream_user_message(
            session_id=session_id,
            content="https://sandbox.invalid/task",
        )

        async for item in stream:
            if item.name == SessionEventType.step_reflected.value:
                break
        await stream.aclose()

        event_types = [event.type for event in uow.session_events.events]
        self.assertEqual(
            event_types[-3:],
            [
                SessionEventType.step_reflected,
                SessionEventType.step_failed,
                SessionEventType.task_error,
            ],
        )
        self.assertEqual(uow.sessions.status, SessionStatus.failed)


if __name__ == "__main__":
    unittest.main()
