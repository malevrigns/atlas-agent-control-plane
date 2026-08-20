import unittest
from types import SimpleNamespace
from uuid import UUID, uuid4

from app.application.agent_execution_machine import (
    AgentExecutionContext,
    AgentExecutionMachine,
)
from app.application.react_agent_service import ReActAgentService
from app.core.exceptions import AppException
from app.domain.agent_core.tools import ToolInvocationStatus
from app.domain.agent_runtime.entities import ReflectionAction
from app.domain.agent_runtime.router import AgentStateRouter
from app.domain.sessions.entities import SessionEvent, SessionEventType, SessionStatus
from tests.test_agent_execution_machine import (
    FakeCritic,
    FakeExecutor,
    FakeReplanner,
    FakeSummarizer,
    plan_payload,
)
from tests.test_step_failure_semantics import FakeUnitOfWork, build_plan_event


class FakeContextService:
    async def build_snapshot(self, session_id, task):
        from tests.test_agent_execution_machine import empty_memory_context

        return SimpleNamespace(memory_context=empty_memory_context())

    @staticmethod
    def render_for_agent(snapshot) -> str:
        return "agent context"


class FakeFileSync:
    def __init__(self) -> None:
        self.session_ids = []

    async def sync(self, session_id) -> None:
        self.session_ids.append(session_id)


class RaisingSummarizer:
    async def stream(self, request):
        raise AppException(message="summary provider failed")
        yield


def build_terminal_service(status, action):
    session_id = uuid4()
    uow = FakeUnitOfWork([build_plan_event(session_id)])
    order = []
    critic = FakeCritic([action, action], order)
    machine = AgentExecutionMachine(
        executor=FakeExecutor([status, status], order),
        critic=critic,
        summarizer=FakeSummarizer(order),
        event_sink=uow.session_events,
        router=AgentStateRouter(),
    )
    sync = FakeFileSync()
    service = ReActAgentService(
        uow,
        execution_machine=machine,
        file_sync_service=sync,
        context_service=FakeContextService(),
    )
    return session_id, service, uow, critic, sync


class ReActEntryPointTerminalSemanticsTest(unittest.IsolatedAsyncioTestCase):
    def build_service(self, status, action):
        return build_terminal_service(status, action)

    async def test_stream_failure_emits_task_error_and_sets_failed(self) -> None:
        session_id, service, uow, critic, sync = self.build_service(
            ToolInvocationStatus.failed, ReflectionAction.fail
        )

        items = [item async for item in service.stream_latest_plan(session_id)]
        events = [item for item in items if isinstance(item, SessionEvent)]
        event_types = [event.type for event in events]

        self.assertEqual(critic.calls[0][1].status, ToolInvocationStatus.failed)
        self.assertEqual(uow.sessions.status, SessionStatus.failed)
        self.assertEqual(sync.session_ids, [session_id])
        self.assertIn(SessionEventType.step_failed, event_types)
        self.assertIn(SessionEventType.task_error, event_types)
        self.assertNotIn(SessionEventType.step_completed, event_types)
        self.assertNotIn(SessionEventType.task_done, event_types)

    async def test_completed_summary_is_persisted_before_consumer_closes(self) -> None:
        session_id, service, uow, _, _ = self.build_service(
            ToolInvocationStatus.succeeded, ReflectionAction.accept
        )
        stream = service.stream_latest_plan(session_id)

        async for item in stream:
            if (
                isinstance(item, SessionEvent)
                and item.type is SessionEventType.message_created
            ):
                break
        await stream.aclose()

        event_types = [event.type for event in uow.session_events.events]
        self.assertEqual(event_types[-1], SessionEventType.task_done)
        self.assertEqual(uow.sessions.status, SessionStatus.idle)

    async def test_failed_reflection_is_persisted_before_consumer_closes(self) -> None:
        session_id, service, uow, _, _ = self.build_service(
            ToolInvocationStatus.failed, ReflectionAction.fail
        )
        stream = service.stream_latest_plan(session_id)

        async for item in stream:
            if (
                isinstance(item, SessionEvent)
                and item.type is SessionEventType.step_reflected
            ):
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

    async def test_stream_blocked_skips_critic_and_task_done(self) -> None:
        session_id, service, uow, critic, _ = self.build_service(
            ToolInvocationStatus.approval_required, ReflectionAction.accept
        )

        items = [item async for item in service.stream_latest_plan(session_id)]
        event_types = [
            item.type for item in items if isinstance(item, SessionEvent)
        ]

        self.assertEqual(critic.calls, [])
        self.assertEqual(uow.sessions.status, SessionStatus.idle)
        self.assertIn(SessionEventType.step_blocked, event_types)
        self.assertNotIn(SessionEventType.task_error, event_types)
        self.assertNotIn(SessionEventType.task_done, event_types)

    async def test_execute_latest_plan_collects_the_same_stream_events(self) -> None:
        service = ReActAgentService.__new__(ReActAgentService)
        session_id = uuid4()
        expected = SessionEvent(
            uuid4(), session_id, SessionEventType.step_started, {}, SimpleNamespace()
        )

        async def stream(_session_id: UUID, *, resume: bool = False):
            del resume
            yield ("answer_delta", "ignored")
            yield expected

        service.stream_latest_plan = stream
        events = await service.execute_latest_plan(session_id)

        self.assertEqual(events, [expected])

    async def test_summary_error_surfaces_as_task_error_without_task_done(self) -> None:
        session_id = uuid4()
        uow = FakeUnitOfWork([build_plan_event(session_id)])
        order = []
        machine = AgentExecutionMachine(
            executor=FakeExecutor(
                [ToolInvocationStatus.succeeded, ToolInvocationStatus.succeeded], order
            ),
            critic=FakeCritic(
                [ReflectionAction.accept, ReflectionAction.accept], order
            ),
            summarizer=RaisingSummarizer(),
            event_sink=uow.session_events,
            router=AgentStateRouter(),
        )
        service = ReActAgentService(
            uow,
            execution_machine=machine,
            file_sync_service=FakeFileSync(),
            context_service=FakeContextService(),
        )

        events = await service.execute_latest_plan(session_id)

        self.assertEqual(events[-1].type, SessionEventType.task_error)
        self.assertEqual(events[-1].payload["message"], "summary provider failed")
        self.assertNotIn(SessionEventType.task_done, [event.type for event in events])

    async def test_replanned_payload_becomes_next_timeline_plan(self) -> None:
        session_id = uuid4()
        original_event = build_plan_event(session_id)
        replacement = plan_payload(1)
        uow = FakeUnitOfWork([original_event])
        order = []
        machine = AgentExecutionMachine(
            executor=FakeExecutor(
                [ToolInvocationStatus.succeeded, ToolInvocationStatus.succeeded], order
            ),
            critic=FakeCritic(
                [ReflectionAction.replan, ReflectionAction.accept], order
            ),
            summarizer=FakeSummarizer(order),
            event_sink=uow.session_events,
            replanner=FakeReplanner(replacement),
            router=AgentStateRouter(),
        )
        service = ReActAgentService(
            uow,
            execution_machine=machine,
            file_sync_service=FakeFileSync(),
            context_service=FakeContextService(),
        )
        await service.execute_latest_plan(session_id)

        observed_plans = []

        class RecordingMachine:
            async def stream(
                self,
                _session_id,
                plan,
                _context,
                *,
                run_id=None,
                start_step_index=0,
                step_history=(),
            ):
                del run_id, start_step_index, step_history
                observed_plans.append(dict(plan))
                if False:
                    yield None

        service._execution_machine = RecordingMachine()
        await service.execute_latest_plan(session_id)

        self.assertEqual(len(observed_plans), 1)
        observed = observed_plans[0]
        self.assertEqual(observed["id"], replacement["id"])
        self.assertEqual(observed["steps"], replacement["steps"])
        self.assertEqual(observed["plan_revision"], 1)
        UUID(str(observed["run_id"]))


if __name__ == "__main__":
    unittest.main()
