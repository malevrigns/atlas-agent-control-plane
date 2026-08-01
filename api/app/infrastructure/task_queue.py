from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from redis.asyncio import Redis

from app.core.config import settings


class AgentTaskStatus(StrEnum):
    queued = "queued"
    running = "running"
    waiting = "waiting"
    completed = "completed"
    failed = "failed"
    stopped = "stopped"
    # 兼容早期章节已经返回过的状态值。
    succeeded = "succeeded"
    cancelled = "cancelled"


@dataclass(slots=True)
class AgentTask:
    id: str
    session_id: UUID
    type: str
    status: AgentTaskStatus
    error: str | None
    created_at: str
    updated_at: str
    parent_task_id: str | None = None
    retry_count: int = 0


class RedisAgentTaskQueue:
    """基于 Redis Stream 的 Agent 任务队列。

    本章只使用一个 Stream 和一个 API 内置 Runner，先把后台任务模型跑通。
    后续可以继续扩展 consumer group、多个 worker 和任务重试策略。
    """

    def __init__(self, redis: Redis, stream_name: str | None = None) -> None:
        # ===================== 第1步：保存 Redis 连接和 Stream 名称 =====================
        self.redis = redis
        self.stream_name = stream_name or settings.agent_task_stream

    # ===================== 第2步：创建任务并写入 Stream =====================
    async def enqueue_execute_plan(
        self,
        session_id: UUID,
        *,
        parent_task_id: str | None = None,
        retry_count: int = 0,
    ) -> AgentTask:
        """创建一个执行计划任务，并把任务 ID 写入 Redis Stream。"""

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

    # ===================== 第3步：读取单个任务状态 =====================
    async def get_task(self, task_id: str) -> AgentTask | None:
        """从 Redis Hash 中读取任务状态。"""

        data = await self.redis.hgetall(self._task_key(task_id))
        if not data:
            return None
        return self._to_task(data)

    # ===================== 第4步：取消还没有完成的任务 =====================
    async def cancel_task(self, task_id: str) -> AgentTask | None:
        """把任务标记为 stopped。

        第 44 章开始使用 stopped 表达“用户主动停止”。
        cancelled 作为早期状态仍然保留在枚举中，用于读取旧任务。
        """

        task = await self.get_task(task_id)
        if task is None:
            return None
        if task.status in {
            AgentTaskStatus.completed,
            AgentTaskStatus.succeeded,
            AgentTaskStatus.failed,
            AgentTaskStatus.stopped,
            AgentTaskStatus.cancelled,
        }:
            return task

        task.status = AgentTaskStatus.stopped
        task.updated_at = self._now()
        await self._write_task(task)
        await self._write_latest_session_task(task)
        return task

    # ===================== 第5步：失败或停止后的重试与恢复 =====================
    async def retry_task(self, task_id: str) -> AgentTask | None:
        """基于历史任务创建一个新的 queued 任务。"""

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

    async def recover_session_task(self, session_id: UUID) -> AgentTask | None:
        """读取某个会话最近一次后台任务状态。"""

        data = await self.redis.hgetall(self._latest_task_key(session_id))
        task_id = str(data.get("task_id") or "")
        if not task_id:
            return None
        return await self.get_task(task_id)

    # ===================== 第6步：更新任务状态 =====================
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

    # ===================== 第7步：封装 Redis Hash 读写细节 =====================
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
