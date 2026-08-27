from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domain.memories.entities import (
    AgentMemory,
    MemoryAuthority,
    MemoryKind,
    MemoryScope,
    MemorySensitivity,
    MemoryStatus,
)


class AgentMemoryRepository(Protocol):
    """长期记忆仓库协议。

    应用服务只依赖这个协议，不直接依赖 SQLAlchemy。
    第41章做记忆检索时，也会继续通过这个协议扩展查询方法。
    """

    async def add(
        self,
        *,
        kind: MemoryKind,
        content: str,
        importance: int,
        source_session_id: UUID | None,
        source_event_id: UUID | None,
        expires_at: datetime | None,
        metadata: dict[str, object],
        scope: MemoryScope = MemoryScope.project,
        status: MemoryStatus = MemoryStatus.candidate,
        subject: str = "",
        predicate: str = "states",
        value: dict[str, object] | None = None,
        confidence: float = 0.5,
        authority: MemoryAuthority = MemoryAuthority.agent_inferred,
        valid_from: datetime | None = None,
        valid_to: datetime | None = None,
        ttl_seconds: int | None = None,
        provenance: list[str] | None = None,
        supersedes: UUID | None = None,
        sensitivity: MemorySensitivity = MemorySensitivity.internal,
        project_id: str | None = None,
        task_id: UUID | None = None,
        user_id: str | None = None,
        created_by: str = "system",
        verification: dict[str, object] | None = None,
    ) -> AgentMemory:
        raise NotImplementedError

    async def get(self, memory_id: UUID) -> AgentMemory | None:
        raise NotImplementedError

    async def list_active(
        self,
        *,
        kind: MemoryKind | None = None,
        enabled_only: bool = False,
        limit: int = 100,
    ) -> list[AgentMemory]:
        raise NotImplementedError

    async def list_retrievable(
        self,
        *,
        now: datetime,
        limit: int,
        project_id: str | None = None,
        task_id: UUID | None = None,
        user_id: str | None = None,
    ) -> list[AgentMemory]:
        """返回启用、未删除并且尚未过期的检索候选。"""

        raise NotImplementedError

    async def update(
        self,
        memory_id: UUID,
        *,
        content: str | None = None,
        importance: int | None = None,
        enabled: bool | None = None,
        expires_at: datetime | None = None,
        metadata: dict[str, object] | None = None,
        status: MemoryStatus | None = None,
        provenance: list[str] | None = None,
        verification: dict[str, object] | None = None,
        valid_to: datetime | None = None,
        confidence: float | None = None,
        authority: MemoryAuthority | None = None,
        related_ids: list[UUID] | None = None,
    ) -> AgentMemory | None:
        raise NotImplementedError

    async def soft_delete(self, memory_id: UUID) -> AgentMemory | None:
        raise NotImplementedError

    async def mark_superseded(
        self,
        memory_id: UUID,
        *,
        replacement_id: UUID,
    ) -> AgentMemory | None:
        raise NotImplementedError

    async def touch_access(self, memory_id: UUID, *, now: datetime) -> AgentMemory | None:
        """记录一次检索命中：access_count +1 并刷新 last_accessed_at。"""

        raise NotImplementedError

    async def list_for_lifecycle(self, *, limit: int | None = None) -> list[AgentMemory]:
        """返回所有未软删除的记忆，供衰减/巩固等生命周期任务扫描。"""

        raise NotImplementedError

    async def record_audit_event(
        self,
        *,
        memory_id: UUID | None,
        event_type: str,
        payload: dict[str, object],
    ) -> UUID:
        """为一条记忆写入可审计的生命周期/冲突事件。"""

        raise NotImplementedError
