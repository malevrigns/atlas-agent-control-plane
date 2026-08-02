import asyncio
import unittest
from unittest.mock import AsyncMock
from uuid import uuid4

from app.application.agent_task_runner import AgentTaskRunner
from app.infrastructure.task_queue import (
    AgentTask,
    AgentTaskStatus,
    QueuedTaskMessage,
)


class FakeRunnerQueue:
    def __init__(self, status: AgentTaskStatus) -> None:
        self.status = status
        self.acknowledged: list[str] = []

    async def get_task(self, task_id: str) -> AgentTask:
        return AgentTask(
            id=task_id,
            session_id=uuid4(),
            type="execute_plan",
            status=self.status,
            error=None,
            created_at="now",
            updated_at="now",
        )

    async def acknowledge(self, message_id: str) -> None:
        self.acknowledged.append(message_id)


class AgentTaskRunnerShutdownTest(unittest.IsolatedAsyncioTestCase):
    async def run_cancelled_message(self, status: AgentTaskStatus) -> FakeRunnerQueue:
        queue = FakeRunnerQueue(status)
        runner = AgentTaskRunner(queue, session_factory=None)
        runner._handle_message = AsyncMock(side_effect=asyncio.CancelledError)
        message = QueuedTaskMessage(
            id="1-0",
            payload={"task_id": "task-1", "session_id": str(uuid4())},
        )

        with self.assertRaises(asyncio.CancelledError):
            await runner._process_message(message)
        return queue

    async def test_shutdown_leaves_running_message_pending(self) -> None:
        queue = await self.run_cancelled_message(AgentTaskStatus.running)
        self.assertEqual(queue.acknowledged, [])

    async def test_user_cancelled_message_is_acknowledged(self) -> None:
        queue = await self.run_cancelled_message(AgentTaskStatus.stopped)
        self.assertEqual(queue.acknowledged, ["1-0"])


if __name__ == "__main__":
    unittest.main()
