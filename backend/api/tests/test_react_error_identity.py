import unittest
from collections.abc import Mapping
from uuid import uuid4

from app.application.agent_execution_machine import AgentExecutionMachine
from app.application.react_agent_service import ReActAgentService
from app.application.react_step_executor import ReActStepExecutor
from app.core.exceptions import AppException
from app.domain.agent_core.tools import ToolInvocationStatus
from app.domain.agent_runtime.entities import ReflectionAction
from app.domain.agent_runtime.router import AgentStateRouter
from app.domain.sessions.entities import SessionEvent, SessionEventType
from tests.test_agent_execution_machine import (
    FakeCritic,
    FakeReplanner,
    FakeSummarizer,
    plan_payload,
)
from tests.test_react_entrypoint_terminal_semantics import (
    FakeContextService,
    FakeFileSync,
    RaisingSummarizer,
)
from tests.test_step_failure_semantics import FakeUnitOfWork, build_plan_event


class RaisingCritic:
    async def evaluate(self, step, observation):
        raise AppException(message="critic provider failed")


def build_service(critic, summarizer, replanner=None):
    session_id = uuid4()
    uow = FakeUnitOfWork([build_plan_event(session_id)])

    async def call_tool(**kwargs) -> Mapping[str, object]:
        return {
            "tool_name": "identity_tool",
            "arguments": {},
            "output": "ok",
            "status": ToolInvocationStatus.succeeded.value,
        }

    executor = ReActStepExecutor(uow=uow, tool_caller=call_tool)
    machine = AgentExecutionMachine(
        executor=executor,
        critic=critic,
        summarizer=summarizer,
        event_sink=uow.session_events,
        replanner=replanner,
        router=AgentStateRouter(),
    )
    service = ReActAgentService(
        uow,
        execution_machine=machine,
        file_sync_service=FakeFileSync(),
        context_service=FakeContextService(),
    )
    return session_id, service


def execution_identity(event: SessionEvent) -> tuple[object, object, object]:
    payload = event.payload
    return payload["run_id"], payload["plan_id"], payload["plan_revision"]


class ReActErrorIdentityTest(unittest.IsolatedAsyncioTestCase):
    async def test_critic_error_keeps_current_run_identity(self) -> None:
        session_id, service = build_service(RaisingCritic(), FakeSummarizer([]))

        events = await service.execute_latest_plan(session_id)

        tool_event = next(
            event for event in events if event.type is SessionEventType.tool_called
        )
        error_event = events[-1]
        self.assertEqual(error_event.type, SessionEventType.task_error)
        self.assertEqual(execution_identity(error_event), execution_identity(tool_event))

    async def test_summary_error_keeps_replanned_run_identity(self) -> None:
        order: list[str] = []
        critic = FakeCritic(
            [ReflectionAction.replan, ReflectionAction.accept],
            order,
        )
        session_id, service = build_service(
            critic,
            RaisingSummarizer(),
            FakeReplanner(plan_payload(1)),
        )

        events = await service.execute_latest_plan(session_id)

        completed = [
            event for event in events if event.type is SessionEventType.step_completed
        ][-1]
        error_event = events[-1]
        self.assertEqual(error_event.type, SessionEventType.task_error)
        self.assertEqual(execution_identity(error_event), execution_identity(completed))
        self.assertEqual(error_event.payload["plan_revision"], 1)


if __name__ == "__main__":
    unittest.main()
