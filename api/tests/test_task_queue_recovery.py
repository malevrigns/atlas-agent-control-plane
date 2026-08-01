import unittest
from uuid import uuid4

from app.infrastructure.task_queue import AgentTaskStatus, RedisAgentTaskQueue


class FakeRedis:
    """用内存字典模拟 Redis Hash 和 Stream，避免单元测试依赖真实 Redis。"""

    def __init__(self) -> None:
        self.hashes: dict[str, dict] = {}
        self.streams: list[tuple[str, dict]] = []

    async def hset(self, key: str, mapping: dict) -> None:
        self.hashes[key] = dict(mapping)

    async def hgetall(self, key: str) -> dict:
        return dict(self.hashes.get(key, {}))

    async def xadd(self, stream_name: str, payload: dict) -> str:
        self.streams.append((stream_name, dict(payload)))
        return f"{len(self.streams)}-0"


class RedisAgentTaskQueueRecoveryTest(unittest.IsolatedAsyncioTestCase):
    # ===================== 第1步：失败任务可以创建重试任务 =====================
    async def test_retry_failed_task_creates_new_task_with_parent(self) -> None:
        session_id = uuid4()
        redis = FakeRedis()
        queue = RedisAgentTaskQueue(redis)

        original = await queue.enqueue_execute_plan(session_id)
        await queue.mark_failed(original.id, "tool failed")

        retry = await queue.retry_task(original.id)

        self.assertIsNotNone(retry)
        assert retry is not None
        self.assertEqual(retry.session_id, session_id)
        self.assertEqual(retry.status, AgentTaskStatus.queued)
        self.assertEqual(retry.parent_task_id, original.id)
        self.assertEqual(retry.retry_count, 1)

    # ===================== 第2步：会话可以恢复最近一次任务状态 =====================
    async def test_recover_session_task_returns_latest_task(self) -> None:
        session_id = uuid4()
        redis = FakeRedis()
        queue = RedisAgentTaskQueue(redis)

        first = await queue.enqueue_execute_plan(session_id)
        await queue.mark_failed(first.id, "first failed")
        retry = await queue.retry_task(first.id)

        latest = await queue.recover_session_task(session_id)

        self.assertIsNotNone(latest)
        assert latest is not None
        assert retry is not None
        self.assertEqual(latest.id, retry.id)
        self.assertEqual(latest.parent_task_id, first.id)

    # ===================== 第3步：运行中的任务可以进入 waiting，再恢复为 running =====================
    async def test_task_can_enter_waiting_and_resume_running(self) -> None:
        session_id = uuid4()
        redis = FakeRedis()
        queue = RedisAgentTaskQueue(redis)

        task = await queue.enqueue_execute_plan(session_id)
        await queue.mark_running(task.id)
        waiting = await queue.mark_waiting(task.id, "waiting for external tool")
        running = await queue.mark_running(task.id)

        self.assertIsNotNone(waiting)
        self.assertEqual(waiting.status, AgentTaskStatus.waiting)
        self.assertEqual(waiting.error, "waiting for external tool")
        self.assertIsNotNone(running)
        self.assertEqual(running.status, AgentTaskStatus.running)


if __name__ == "__main__":
    unittest.main()
