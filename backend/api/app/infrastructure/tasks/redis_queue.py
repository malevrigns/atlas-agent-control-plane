"""AgentTaskQueue 的 Redis Stream 适配器。

多进程 / 多副本部署的默认后端：任务状态放 Hash，投递走 Stream +
consumer group，消费者崩溃后未 ACK 的消息由 ``xautoclaim`` 取回。

这个文件是整个工程里唯一知道 ``xreadgroup`` / ``BUSYGROUP`` 的地方。
"""

import os
import socket
from datetime import UTC, datetime
from uuid import UUID, uuid4

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from app.core.config import settings
from app.domain.tasks.entities import AgentTask, AgentTaskStatus, QueuedTaskMessage


class RedisAgentTaskQueue:
    """基于 Redis Stream 的 Agent 任务队列。"""

    backend_name = "redis"

    def __init__(self, redis: Redis, stream_name: str | None = None) -> None:
        self.redis = redis
        self.stream_name = stream_name or settings.agent_task_stream
        self.consumer_group = settings.agent_task_consumer_group
        self.consumer_name = f"{socket.gethostname()}-{os.getpid()}-{uuid4().hex[:8]}"

    # ===================== 生命周期 =====================
    async def start(self) -> None:
        """Create a group at 0-0 so messages queued before startup are not skipped."""

        try:
            await self.redis.xgroup_create(
                self.stream_name,
                self.consumer_group,
                id="0-0",
                mkstream=True,
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def close(self) -> None:
        await self.redis.aclose()

    # 兼容旧调用点：语义与 start() 相同。
    ensure_consumer_group = start

    # ===================== 读取与确认 =====================
    async def reserve_messages(self, *, count: int = 1) -> list[QueuedTaskMessage]:
        streams = await self.redis.xreadgroup(
            self.consumer_group,
            self.consumer_name,
            {self.stream_name: ">"},
            block=settings.agent_task_poll_timeout_ms,
            count=count,
        )
        return self._flatten_streams(streams)

    async def reclaim_stale_messages(self, *, count: int = 100) -> list[QueuedTaskMessage]:
        result = await self.redis.xautoclaim(
            self.stream_name,
            self.consumer_group,
            self.consumer_name,
            min_idle_time=settings.agent_task_claim_idle_ms,
            start_id="0-0",
            count=count,
        )
        messages = result[1] if len(result) > 1 else []
        return [
            QueuedTaskMessage(id=str(message_id), payload=dict(payload))
            for message_id, payload in messages
        ]

    async def acknowledge(self, message_id: str) -> None:
        await self.redis.xack(self.stream_name, self.consumer_group, message_id)

    @staticmethod
    def _flatten_streams(streams: list) -> list[QueuedTaskMessage]:
        return [
            QueuedTaskMessage(id=str(message_id), payload=dict(payload))
            for _, messages in streams
            for message_id, payload in messages
        ]

    # ===================== 入队 =====================
    async def enqueue_execute_plan(
        self,
        session_id: UUID,
        *,
        parent_task_id: str | None = None,
        retry_count: int = 0,
    ) -> AgentTask:
        now = self._now()
        task = AgentTask(
            id=str(uuid4()),
            session_id=session_id,
            type="execute_plan",
            status=AgentTaskStatus.queued,
            error=None,
            created_at=now,
            updated_at=now,
            parent_task_id=parent_task_id,
            retry_count=retry_count,
        )
        await self._write_task(task)
        await self._write_latest_session_task(task)
        await self.redis.xadd(
            self.stream_name,
            {
                "task_id": task.id,
                "session_id": str(session_id),
                "type": task.type,
                "parent_task_id": parent_task_id or "",
                "retry_count": str(retry_count),
            },
        )
        return task

    # ===================== 查询 =====================
    async def get_task(self, task_id: str) -> AgentTask | None:
        data = await self.redis.hgetall(self._task_key(task_id))
        if not data:
            return None
        return self._to_task(data)

    async def recover_session_task(self, session_id: UUID) -> AgentTask | None:
        data = await self.redis.hgetall(self._latest_task_key(session_id))
        task_id = str(data.get("task_id") or "")
        if not task_id:
            return None
        return await self.get_task(task_id)

    # ===================== 取消与重试 =====================
    async def cancel_task(self, task_id: str) -> AgentTask | None:
        task = await self.get_task(task_id)
        if task is None:
            return None
        if task.is_terminal:
            return task

        task.status = AgentTaskStatus.stopped
        task.updated_at = self._now()
        await self._write_task(task)
        await self._write_latest_session_task(task)
        return task

    async def retry_task(self, task_id: str) -> AgentTask | None:
        task = await self.get_task(task_id)
        if task is None:
            return None
        if task.status not in {
            AgentTaskStatus.failed,
            AgentTaskStatus.stopped,
            AgentTaskStatus.cancelled,
        }:
            return task

        return await self.enqueue_execute_plan(
            task.session_id,
            parent_task_id=task.id,
            retry_count=task.retry_count + 1,
        )

    # ===================== 状态流转 =====================
    async def mark_running(self, task_id: str) -> AgentTask | None:
        return await self._update_status(task_id, AgentTaskStatus.running)

    async def mark_waiting(self, task_id: str, reason: str | None = None) -> AgentTask | None:
        return await self._update_status(task_id, AgentTaskStatus.waiting, error=reason)

    async def mark_succeeded(self, task_id: str) -> AgentTask | None:
        return await self._update_status(task_id, AgentTaskStatus.completed)

    async def mark_failed(self, task_id: str, error: str) -> AgentTask | None:
        return await self._update_status(task_id, AgentTaskStatus.failed, error=error)

    async def _update_status(
        self,
        task_id: str,
        status: AgentTaskStatus,
        error: str | None = None,
    ) -> AgentTask | None:
        task = await self.get_task(task_id)
        if task is None:
            return None
        task.status = status
        task.error = error
        task.updated_at = self._now()
        await self._write_task(task)
        await self._write_latest_session_task(task)
        return task

    async def health(self) -> dict[str, object]:
        pending = 0
        try:
            groups = await self.redis.xinfo_groups(self.stream_name)
            for group in groups:
                if str(group.get("name")) == self.consumer_group:
                    pending = int(group.get("pending") or 0)
                    break
        except ResponseError:
            # Stream 尚未创建：还没有任何任务入队。
            pending = 0
        return {
            "backend": self.backend_name,
            "durable": True,
            "multi_process": True,
            "stream": self.stream_name,
            "pending": pending,
        }

    # ===================== Redis 读写细节 =====================
    async def _write_task(self, task: AgentTask) -> None:
        await self.redis.hset(
            self._task_key(task.id),
            mapping={
                "id": task.id,
                "session_id": str(task.session_id),
                "type": task.type,
                "status": task.status.value,
                "error": task.error or "",
                "created_at": task.created_at,
                "updated_at": task.updated_at,
                "parent_task_id": task.parent_task_id or "",
                "retry_count": str(task.retry_count),
            },
        )

    async def _write_latest_session_task(self, task: AgentTask) -> None:
        await self.redis.hset(
            self._latest_task_key(task.session_id),
            mapping={
                "task_id": task.id,
                "updated_at": task.updated_at,
            },
        )

    def _to_task(self, data: dict) -> AgentTask:
        return AgentTask(
            id=str(data["id"]),
            session_id=UUID(str(data["session_id"])),
            type=str(data["type"]),
            status=AgentTaskStatus(str(data["status"])),
            error=str(data["error"]) or None,
            created_at=str(data["created_at"]),
            updated_at=str(data["updated_at"]),
            parent_task_id=str(data.get("parent_task_id") or "") or None,
            retry_count=int(data.get("retry_count") or 0),
        )

    def _task_key(self, task_id: str) -> str:
        return f"agent:task:{task_id}"

    def _latest_task_key(self, session_id: UUID) -> str:
        return f"agent:session:{session_id}:latest-task"

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()


def create_redis_client() -> Redis:
    """创建 Redis 客户端。

    decode_responses=True 会把 Redis 返回值解码成字符串，代码里不需要反复处理 bytes。
    """

    return Redis.from_url(settings.redis_url, decode_responses=True)
