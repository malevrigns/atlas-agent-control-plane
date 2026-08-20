import unittest
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
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


class FakeDirectChatService:
    model = object()
    context_service = object()

    async def stream(self, *, session_id: UUID, content: str):
        raise AssertionError("tool task must not enter direct chat")
        yield


class AgentRunnerServiceTest(unittest.IsolatedAsyncioTestCase):
    def test_runner_requires_composed_direct_chat_service(self) -> None:
        with self.assertRaises(TypeError):
            AgentRunnerService(
                session_service=SimpleNamespace(uow=SimpleNamespace()),
                planner_service=object(),
                react_service=object(),
            )

    def assert_shared_model(self, service, model) -> None:
        machine = service.react_service._execution_machine
        step_loop = machine._executor._step_loop
        self.assertIs(service.llm_service, model)
        self.assertIs(service.direct_chat_service.model, model)
        self.assertIs(service.planner_service.llm_service, model)
        self.assertIs(machine._critic._model, model)
        self.assertIs(machine._summarizer._model, model)
        self.assertIs(step_loop.llm_service, model)

    def test_agent_runner_module_stays_within_file_limit(self) -> None:
        path = Path(__file__).parents[1] / "app/application/agent_runner_service.py"

        self.assertLessEqual(len(path.read_text(encoding="utf-8").splitlines()), 320)

    def test_from_uow_shares_explicit_model_across_production_graph(self) -> None:
        model = object()
        uow = SimpleNamespace(session_events=object())

        service = AgentRunnerService.from_uow(uow, llm_service=model)

        self.assert_shared_model(service, model)

    def test_from_uow_injects_shared_model_into_default_planner(self) -> None:
        uow = SimpleNamespace()
        model = object()
        uow.session_events = object()
        with patch(
            "app.application.agent_runtime_composition.LLMService", return_value=model
        ) as model_class:
            service = AgentRunnerService.from_uow(uow)

        model_class.assert_called_once_with()
        self.assert_shared_model(service, model)

    # ===================== 第1步：验证对话执行流由统一 Runner 串起来 =====================
    async def test_stream_user_message_yields_unified_runner_events(self) -> None:
        session = build_session()
        service = AgentRunnerService(
            session_service=FakeSessionService(session),
            planner_service=FakePlannerService(),
            react_service=FakeReactService(),
            direct_chat_service=FakeDirectChatService(),
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
