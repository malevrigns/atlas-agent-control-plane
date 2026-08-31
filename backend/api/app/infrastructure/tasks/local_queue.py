"""AgentTaskQueue 的进程内适配器（SQLite 持久化）。

存在的理由是「单副本部署不该被迫先装 Redis」。它不是测试玩具：
任务状态与投递记录都落在 SQLite 文件里，进程重启后未完成的任务仍能
被重新领取，语义与 Redis 适配器一致（同一套契约测试同时跑在两者上）。

它明确**不**支持的场景：多进程 / 多副本共享同一个队列。SQLite 能承受
多进程读，但这里的「预留」语义依赖单写入者假设，跨进程消费会互相抢占。
需要横向扩展时切回 Redis——这也是 ``health()`` 里如实上报
``multi_process: False`` 的原因。
"""

import asyncio
import json
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from app.core.config import settings
from app.domain.tasks.entities import AgentTask, AgentTaskStatus, QueuedTaskMessage

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_queue_tasks (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    type TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    parent_task_id TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS agent_queue_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payload TEXT NOT NULL,
    enqueued_at REAL NOT NULL,
    reserved_at REAL,
    acknowledged_at REAL
);
CREATE INDEX IF NOT EXISTS ix_queue_messages_pending
    ON agent_queue_messages (acknowledged_at, reserved_at);
CREATE INDEX IF NOT EXISTS ix_queue_tasks_session
    ON agent_queue_tasks (session_id, updated_at);
"""


class LocalAgentTaskQueue:
    """单进程持久化任务队列。"""

    backend_name = "local"

    def __init__(self, database_path: str | None = None) -> None:
        raw_path = database_path or settings.agent_task_local_path
        self._path = Path(raw_path).expanduser()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(self._path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        # WAL 让读写不互相阻塞；这个队列的写入很频繁但都很小。
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.executescript(_SCHEMA)
        self._connection.commit()
        # 所有 SQLite 调用都在锁内完成：sqlite3 连接不是并发安全的，而
        # Runner 会从多个协程同时读写。
        self._lock = asyncio.Lock()

    # ===================== 生命周期 =====================
    async def start(self) -> None:
        """把上次进程遗留的「已预留未确认」消息释放回待处理。

        进程重启意味着那些消息的持有者已经不存在了，必须归还，否则任务
        会永久卡住——等价于 Redis 适配器里 xautoclaim 的作用。
        """

        async with self._lock:
            self._connection.execute(
                "UPDATE agent_queue_messages SET reserved_at = NULL "
                "WHERE acknowledged_at IS NULL"
            )
            self._connection.commit()

    async def close(self) -> None:
        async with self._lock:
            self._connection.close()

    # ===================== 读取与确认 =====================
    async def reserve_messages(self, *, count: int = 1) -> list[QueuedTaskMessage]:
        async with self._lock:
            rows = self._connection.execute(
                "SELECT id, payload FROM agent_queue_messages "
                "WHERE acknowledged_at IS NULL AND reserved_at IS NULL "
                "ORDER BY id LIMIT ?",
                (max(1, count),),
            ).fetchall()
            if rows:
                now = time.time()
                self._connection.executemany(
                    "UPDATE agent_queue_messages SET reserved_at = ? WHERE id = ?",
                    [(now, row["id"]) for row in rows],
                )
                self._connection.commit()
            messages = [
                QueuedTaskMessage(id=str(row["id"]), payload=json.loads(row["payload"]))
                for row in rows
            ]

        if not messages:
            # 和 Redis 的 block 参数对齐：空队列时让出事件循环，避免忙等。
            await asyncio.sleep(settings.agent_task_poll_timeout_ms / 1000)
        return messages

    async def reclaim_stale_messages(self, *, count: int = 100) -> list[QueuedTaskMessage]:
        cutoff = time.time() - settings.agent_task_claim_idle_ms / 1000
        async with self._lock:
            rows = self._connection.execute(
                "SELECT id, payload FROM agent_queue_messages "
                "WHERE acknowledged_at IS NULL AND reserved_at IS NOT NULL "
                "AND reserved_at < ? ORDER BY id LIMIT ?",
                (cutoff, max(1, count)),
            ).fetchall()
            if not rows:
                return []
            now = time.time()
            self._connection.executemany(
                "UPDATE agent_queue_messages SET reserved_at = ? WHERE id = ?",
                [(now, row["id"]) for row in rows],
            )
            self._connection.commit()
            return [
                QueuedTaskMessage(id=str(row["id"]), payload=json.loads(row["payload"]))
                for row in rows
            ]

    async def acknowledge(self, message_id: str) -> None:
        async with self._lock:
            self._connection.execute(
                "UPDATE agent_queue_messages SET acknowledged_at = ? WHERE id = ?",
                (time.time(), int(message_id)),
            )
            self._connection.commit()

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
        payload = {
            "task_id": task.id,
            "session_id": str(session_id),
            "type": task.type,
            "parent_task_id": parent_task_id or "",
            "retry_count": str(retry_count),
        }
        async with self._lock:
            self._write_task(task)
            self._connection.execute(
                "INSERT INTO agent_queue_messages (payload, enqueued_at) VALUES (?, ?)",
                (json.dumps(payload), time.time()),
            )
            self._connection.commit()
        return task

    # ===================== 查询 =====================
    async def get_task(self, task_id: str) -> AgentTask | None:
        async with self._lock:
            return self._read_task(task_id)

    async def recover_session_task(self, session_id: UUID) -> AgentTask | None:
        async with self._lock:
            row = self._connection.execute(
                "SELECT * FROM agent_queue_tasks WHERE session_id = ? "
                "ORDER BY created_at DESC, rowid DESC LIMIT 1",
                (str(session_id),),
            ).fetchone()
            return self._to_task(row) if row else None

    # ===================== 取消与重试 =====================
    async def cancel_task(self, task_id: str) -> AgentTask | None:
        async with self._lock:
            task = self._read_task(task_id)
            if task is None:
                return None
            if task.is_terminal:
                return task
            task.status = AgentTaskStatus.stopped
            task.updated_at = self._now()
            self._write_task(task)
            self._connection.commit()
            return task

    async def retry_task(self, task_id: str) -> AgentTask | None:
        async with self._lock:
            task = self._read_task(task_id)
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
        async with self._lock:
            task = self._read_task(task_id)
            if task is None:
                return None
            task.status = status
            task.error = error
            task.updated_at = self._now()
            self._write_task(task)
            self._connection.commit()
            return task

    async def health(self) -> dict[str, object]:
        async with self._lock:
            pending = int(
                self._connection.execute(
                    "SELECT count(*) FROM agent_queue_messages WHERE acknowledged_at IS NULL"
                ).fetchone()[0]
            )
        return {
            "backend": self.backend_name,
            "durable": True,
            # 单进程限制如实上报，不假装能横向扩展。
            "multi_process": False,
            "path": str(self._path),
            "pending": pending,
        }

    # ===================== SQLite 读写细节 =====================
    def _write_task(self, task: AgentTask) -> None:
        self._connection.execute(
            "INSERT INTO agent_queue_tasks "
            "(id, session_id, type, status, error, created_at, updated_at, parent_task_id, retry_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET status=excluded.status, error=excluded.error, "
            "updated_at=excluded.updated_at",
            (
                task.id,
                str(task.session_id),
                task.type,
                task.status.value,
                task.error or "",
                task.created_at,
                task.updated_at,
                task.parent_task_id or "",
                task.retry_count,
            ),
        )

    def _read_task(self, task_id: str) -> AgentTask | None:
        row = self._connection.execute(
            "SELECT * FROM agent_queue_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        return self._to_task(row) if row else None

    @staticmethod
    def _to_task(row: sqlite3.Row) -> AgentTask:
        return AgentTask(
            id=str(row["id"]),
            session_id=UUID(str(row["session_id"])),
            type=str(row["type"]),
            status=AgentTaskStatus(str(row["status"])),
            error=str(row["error"] or "") or None,
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            parent_task_id=str(row["parent_task_id"] or "") or None,
            retry_count=int(row["retry_count"] or 0),
        )

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()
