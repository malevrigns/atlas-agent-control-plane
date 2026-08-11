import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from app.application.agent_task_runner import AgentTaskRunner
from app.domain.sessions.entities import SessionEventType
from app.infrastructure.task_queue import AgentTask, AgentTaskStatus


class FakeRunnerQueue:
    def __init__(self) -> None:
        self.status = AgentTaskStatus.queued
        self.error: str | None = None
        self.succeeded_calls = 0

    async def get_task(self, task_id: str) -> AgentTask:
        return AgentTask(
            id=task_id,
            session_id=uuid4(),
            type="execute_plan",
            status=self.status,
            error=self.error,
            created_at="now",
            updated_at="now",
        )

    async def mark_running(self, task_id: str) -> None:
        self.status = AgentTaskStatus.running

    async def mark_waiting(self, task_id: str, reason: str | None = None) -> None:
        self.status = AgentTaskStatus.waiting
        self.error = reason

    async def mark_failed(self, task_id: str, error: str) -> None:
        self.status = AgentTaskStatus.failed
        self.error = error

    async def mark_succeeded(self, task_id: str) -> None:
        self.succeeded_calls += 1
        self.status = AgentTaskStatus.completed


def task_payload() -> dict:
    return {
        "task_id": "task-1",
        "type": "execute_plan",
        "session_id": str(uuid4()),
    }


class AgentTaskRunnerTerminalSemanticsTest(unittest.IsolatedAsyncioTestCase):
    async def test_step_blocked_marks_task_waiting_not_succeeded(self) -> None:
        queue = FakeRunnerQueue()
        runner = AgentTaskRunner(queue, session_factory=None)
        runner._execute_plan = AsyncMock(
            return_value=[
                SimpleNamespace(
                    type=SessionEventType.step_blocked,
                    payload={"summary": "approval required"},
                )
            ]
        )

        acknowledged = await runner._handle_message(task_payload())

        self.assertTrue(acknowledged)
        self.assertEqual(queue.status, AgentTaskStatus.waiting)
        self.assertEqual(queue.succeeded_calls, 0)

    async def test_task_error_marks_task_failed(self) -> None:
        queue = FakeRunnerQueue()
        runner = AgentTaskRunner(queue, session_factory=None)
        runner._execute_plan = AsyncMock(
            return_value=[
                SimpleNamespace(
                    type=SessionEventType.task_error,
                    payload={"message": "tool failed"},
                )
            ]
        )

        acknowledged = await runner._handle_message(task_payload())

        self.assertTrue(acknowledged)
        self.assertEqual(queue.status, AgentTaskStatus.failed)
        self.assertEqual(queue.succeeded_calls, 0)


if __name__ == "__main__":
    unittest.main()
