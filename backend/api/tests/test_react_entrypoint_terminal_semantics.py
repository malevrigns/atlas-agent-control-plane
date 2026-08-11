import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from app.domain.agent_core.tools import ToolInvocationStatus
from app.domain.sessions.entities import SessionEvent, SessionEventType
from tests.test_step_failure_semantics import (
    FakeContextEngineeringService,
    FakeLLMService,
    FakeUnitOfWork,
    StubReActAgentService,
    build_plan_event,
)


class ReActEntryPointTerminalSemanticsTest(unittest.IsolatedAsyncioTestCase):
    def build_service(
        self,
        status: ToolInvocationStatus,
    ) -> tuple[UUID, StubReActAgentService]:
        session_id = uuid4()
        uow = FakeUnitOfWork([build_plan_event(session_id)])
        return session_id, StubReActAgentService(status, uow)

    async def run_sync(self, status: ToolInvocationStatus):
        session_id, service = self.build_service(status)
        with patch(
            "app.application.react_agent_service.ContextEngineeringService",
            FakeContextEngineeringService,
        ):
            events = await service.execute_latest_plan(session_id)
        return service, events

    async def run_stream(self, status: ToolInvocationStatus):
        session_id, service = self.build_service(status)
        with (
            patch(
                "app.application.react_agent_service.ContextEngineeringService",
                FakeContextEngineeringService,
            ),
            patch(
                "app.application.react_agent_service.LLMService",
                FakeLLMService,
            ),
        ):
            items = [item async for item in service.stream_latest_plan(session_id)]
        events = [item for item in items if isinstance(item, SessionEvent)]
        return service, events

    async def test_sync_failure_stops_plan_and_emits_task_error(self) -> None:
        service, events = await self.run_sync(ToolInvocationStatus.failed)
        event_types = [event.type for event in events]

        self.assertEqual(service.tool_calls, 1)
        self.assertIn(SessionEventType.step_failed, event_types)
        self.assertIn(SessionEventType.task_error, event_types)
        self.assertNotIn(SessionEventType.task_done, event_types)

    async def test_stream_failure_stops_plan_and_emits_task_error(self) -> None:
        service, events = await self.run_stream(ToolInvocationStatus.failed)
        event_types = [event.type for event in events]

        self.assertEqual(service.tool_calls, 1)
        self.assertIn(SessionEventType.step_failed, event_types)
        self.assertIn(SessionEventType.task_error, event_types)
        self.assertNotIn(SessionEventType.task_done, event_types)

    async def test_sync_blocked_stops_without_task_done_or_error(self) -> None:
        service, events = await self.run_sync(ToolInvocationStatus.approval_required)
        event_types = [event.type for event in events]

        self.assertEqual(service.tool_calls, 1)
        self.assertIn(SessionEventType.step_blocked, event_types)
        self.assertNotIn(SessionEventType.task_error, event_types)
        self.assertNotIn(SessionEventType.task_done, event_types)

    async def test_stream_blocked_stops_without_task_done_or_error(self) -> None:
        service, events = await self.run_stream(ToolInvocationStatus.approval_required)
        event_types = [event.type for event in events]

        self.assertEqual(service.tool_calls, 1)
        self.assertIn(SessionEventType.step_blocked, event_types)
        self.assertNotIn(SessionEventType.task_error, event_types)
        self.assertNotIn(SessionEventType.task_done, event_types)


if __name__ == "__main__":
    unittest.main()
