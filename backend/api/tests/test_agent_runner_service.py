import unittest
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.application.agent_runner_service import AgentRunnerService
from app.domain.agent_core.planner import create_agent_plan, create_plan_step
from app.domain.sessions.entities import (
    MessageRole,
    Session,
    SessionEvent,
    SessionEventType,
    SessionMessage,
    SessionStatus,
)


def build_session(status: SessionStatus = SessionStatus.idle) -> Session:
    now = datetime.now(UTC)
    return Session(
        id=uuid4(),
        title="第 42 章测试会话",
        status=status,
        unread_count=0,
        created_at=now,
        updated_at=now,
    )


def build_message(session_id: UUID, content: str) -> SessionMessage:
    return SessionMessage(
        id=uuid4(),
        session_id=session_id,
        role=MessageRole.user,
        content=content,
        created_at=datetime.now(UTC),
    )


def build_event(
    session_id: UUID,
    event_type: SessionEventType,
    payload: dict,
) -> SessionEvent:
    return SessionEvent(
        id=uuid4(),
        session_id=session_id,
        type=event_type,
        payload=payload,
        created_at=datetime.now(UTC),
    )


@dataclass(slots=True)
class FakeSessionService:
    session: Session

    async def mark_running(self, session_id: UUID) -> Session:
        self.session.status = SessionStatus.running
        return self.session

    async def create_user_message(
        self,
        session_id: UUID,
        content: str,
    ) -> tuple[SessionMessage, SessionEvent]:
        message = build_message(session_id, content)
        event = build_event(
            session_id,
            SessionEventType.message_created,
            {"message_id": str(message.id), "content": content},
        )
        return message, event

    async def get_session(self, session_id: UUID) -> Session:
        self.session.status = SessionStatus.idle
        return self.session


class FakePlannerService:
    def _build(self, session_id: UUID, task: str):
        plan = create_agent_plan(
            title="测试计划",
            goal=task,
            source="test",
            steps=[
                create_plan_step(
                    title="执行任务",
                    description="执行测试任务",
                    expected_output="返回结果",
                )
            ],
        )
        event = build_event(
            session_id,
            SessionEventType.plan_created,
            {"id": str(plan.id), "goal": task},
        )
        return plan, event

    async def create_plan(self, session_id: UUID, task: str):
        return self._build(session_id, task)

    async def stream_plan(self, session_id: UUID, task: str):
        yield ("result", self._build(session_id, task))


class FakeReactService:
    async def stream_latest_plan(self, session_id: UUID):
        yield build_event(
            session_id,
            SessionEventType.step_started,
            {"title": "执行任务"},
        )
        yield build_event(
            session_id,
            SessionEventType.task_done,
            {"message": "完成"},
        )


class AgentRunnerServiceTest(unittest.IsolatedAsyncioTestCase):
    # ===================== 第1步：验证对话执行流由统一 Runner 串起来 =====================
    async def test_stream_user_message_yields_unified_runner_events(self) -> None:
        session = build_session()
        service = AgentRunnerService(
            session_service=FakeSessionService(session),
            planner_service=FakePlannerService(),
            react_service=FakeReactService(),
        )

        items = [
            item
            async for item in service.stream_user_message(
                session_id=session.id,
                content="请执行一个测试任务",
            )
        ]

        self.assertEqual(
            [item.name for item in items],
            [
                "session_status",
                "message_created",
                "plan_created",
                "step_started",
                "task_done",
                "session_status",
                "stream_done",
            ],
        )
        self.assertEqual(items[-1].payload["session_id"], str(session.id))
        self.assertIn("message", items[-1].payload)


if __name__ == "__main__":
    unittest.main()
