"""AgentTaskQueue 端口的契约测试。

同一批断言跑在所有适配器上。「可插拔」如果没有这层保证就只是口号：
两个实现可以各自都有测试、各自都过，但语义并不一致，切换后端时才发现
任务会丢或被重复消费。

新增一个队列适配器时，只要在 ``_make_queue`` 里加一个分支，它就必须
满足和 Redis 完全相同的语义，否则测试失败。
"""

import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from app.domain.tasks.entities import AgentTaskStatus
from app.infrastructure.tasks.local_queue import LocalAgentTaskQueue
from app.infrastructure.tasks.redis_queue import RedisAgentTaskQueue

from tests.support.fake_redis import FakeRedis


class AgentTaskQueueContract:
    """所有 AgentTaskQueue 实现都必须满足的语义。

    这个类刻意不继承 TestCase：它只提供断言，由下面两个具体类混入，
    避免契约本身被当成一个独立用例收集。
    """

    async def _make_queue(self):
        raise NotImplementedError

    # ===================== 契约1：入队后可以被领取，并携带任务标识 =====================
    async def test_enqueued_message_can_be_reserved(self) -> None:
        queue = await self._make_queue()
        task = await queue.enqueue_execute_plan(uuid4())

        messages = await queue.reserve_messages()

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].payload["task_id"], task.id)

    # ===================== 契约2：已领取未确认的消息不会被重复领取 =====================
    async def test_reserved_message_is_not_delivered_twice(self) -> None:
        queue = await self._make_queue()
        await queue.enqueue_execute_plan(uuid4())

        first = await queue.reserve_messages()
        second = await queue.reserve_messages()

        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])

    # ===================== 契约3：启动前入队的消息不会被跳过 =====================
    async def test_messages_enqueued_before_start_are_still_readable(self) -> None:
        queue = await self._make_queue()
        task = await queue.enqueue_execute_plan(uuid4())

        # 模拟「消息先入队，消费者后启动」：这是重启场景的常态。
        await queue.start()
        messages = await queue.reserve_messages()

        self.assertEqual([message.payload["task_id"] for message in messages], [task.id])

    # ===================== 契约4：终态任务上取消是幂等的 =====================
    async def test_cancel_is_idempotent_on_terminal_task(self) -> None:
        queue = await self._make_queue()
        task = await queue.enqueue_execute_plan(uuid4())
        await queue.mark_succeeded(task.id)

        cancelled = await queue.cancel_task(task.id)

        self.assertIsNotNone(cancelled)
        assert cancelled is not None
        self.assertEqual(cancelled.status, AgentTaskStatus.completed)

    # ===================== 契约5：重试派生新任务并记录父子关系 =====================
    async def test_retry_creates_child_task(self) -> None:
        queue = await self._make_queue()
        session_id = uuid4()
        original = await queue.enqueue_execute_plan(session_id)
        await queue.mark_failed(original.id, "tool failed")

        retry = await queue.retry_task(original.id)

        self.assertIsNotNone(retry)
        assert retry is not None
        self.assertEqual(retry.parent_task_id, original.id)
        self.assertEqual(retry.retry_count, 1)
        self.assertEqual(retry.status, AgentTaskStatus.queued)
        self.assertEqual(retry.session_id, session_id)

    # ===================== 契约6：运行中任务未结束前不算终态 =====================
    async def test_running_task_is_not_terminal(self) -> None:
        queue = await self._make_queue()
        task = await queue.enqueue_execute_plan(uuid4())

        running = await queue.mark_running(task.id)

        assert running is not None
        self.assertFalse(running.is_terminal)
        self.assertFalse(running.is_aborted)

    # ===================== 契约7：取消后的任务是「用户中止」语义 =====================
    async def test_cancelled_task_is_aborted(self) -> None:
        queue = await self._make_queue()
        task = await queue.enqueue_execute_plan(uuid4())

        cancelled = await queue.cancel_task(task.id)

        assert cancelled is not None
        self.assertTrue(cancelled.is_aborted)
        self.assertTrue(cancelled.is_terminal)

    # ===================== 契约8：会话可以恢复最近一次任务 =====================
    async def test_recover_session_task_returns_latest(self) -> None:
        queue = await self._make_queue()
        session_id = uuid4()
        first = await queue.enqueue_execute_plan(session_id)
        await queue.mark_failed(first.id, "boom")
        retry = await queue.retry_task(first.id)

        latest = await queue.recover_session_task(session_id)

        assert latest is not None and retry is not None
        self.assertEqual(latest.id, retry.id)

    # ===================== 契约9：未知任务返回 None，而不是抛异常 =====================
    async def test_unknown_task_returns_none(self) -> None:
        queue = await self._make_queue()

        self.assertIsNone(await queue.get_task(str(uuid4())))
        self.assertIsNone(await queue.cancel_task(str(uuid4())))

    # ===================== 契约10：health 必须自报后端与并发能力 =====================
    async def test_health_reports_backend_identity(self) -> None:
        queue = await self._make_queue()

        health = await queue.health()

        self.assertEqual(health["backend"], queue.backend_name)
        self.assertIn("multi_process", health)


class RedisQueueContractTest(AgentTaskQueueContract, unittest.IsolatedAsyncioTestCase):
    async def _make_queue(self):
        return RedisAgentTaskQueue(FakeRedis())


class LocalQueueContractTest(AgentTaskQueueContract, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)

    async def _make_queue(self):
        path = Path(self._tempdir.name) / "queue.db"
        queue = LocalAgentTaskQueue(str(path))
        self.addAsyncCleanup(queue.close)
        return queue


class LocalQueueDurabilityTest(unittest.IsolatedAsyncioTestCase):
    """进程内队列的持久化与崩溃恢复行为。

    这几条是 local 后端特有的保证，无法用 FakeRedis 表达，所以放在契约
    之外单独验证。
    """

    async def asyncSetUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self._path = str(Path(self._tempdir.name) / "queue.db")

    async def test_task_survives_restart(self) -> None:
        first = LocalAgentTaskQueue(self._path)
        task = await first.enqueue_execute_plan(uuid4())
        await first.close()

        # 换一个实例代表进程重启：状态必须还在文件里。
        second = LocalAgentTaskQueue(self._path)
        self.addAsyncCleanup(second.close)
        restored = await second.get_task(task.id)

        assert restored is not None
        self.assertEqual(restored.id, task.id)
        self.assertEqual(restored.status, AgentTaskStatus.queued)

    async def test_reserved_but_unacked_message_is_released_on_restart(self) -> None:
        first = LocalAgentTaskQueue(self._path)
        task = await first.enqueue_execute_plan(uuid4())
        reserved = await first.reserve_messages()
        self.assertEqual(len(reserved), 1)
        # 故意不 acknowledge，模拟消费者崩溃。
        await first.close()

        second = LocalAgentTaskQueue(self._path)
        self.addAsyncCleanup(second.close)
        await second.start()
        redelivered = await second.reserve_messages()

        self.assertEqual([m.payload["task_id"] for m in redelivered], [task.id])

    async def test_acknowledged_message_is_not_redelivered(self) -> None:
        queue = LocalAgentTaskQueue(self._path)
        self.addAsyncCleanup(queue.close)
        await queue.enqueue_execute_plan(uuid4())
        messages = await queue.reserve_messages()
        await queue.acknowledge(messages[0].id)

        await queue.start()
        self.assertEqual(await queue.reserve_messages(), [])


if __name__ == "__main__":
    unittest.main()
