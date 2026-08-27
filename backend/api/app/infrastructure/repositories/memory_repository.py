from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.memories.entities import (
    AgentMemory,
    MemoryAuthority,
    MemoryKind,
    MemoryScope,
    MemorySensitivity,
    MemoryStatus,
)
from app.domain.memories.repositories import AgentMemoryRepository
from app.infrastructure.database.models.agent_memory import AgentMemoryModel, MemoryAuditEventModel


class SqlAlchemyAgentMemoryRepository(AgentMemoryRepository):
    """使用 SQLAlchemy 实现长期记忆读写。"""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

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
        # 1. Repository 只负责把领域数据写入当前数据库会话。
        #    是否提交事务，由应用服务统一决定。
        model = AgentMemoryModel(
            kind=kind.value,
            content=content,
            importance=importance,
            source_session_id=source_session_id,
            source_event_id=source_event_id,
            expires_at=expires_at,
            metadata_json=metadata,
            scope=scope.value,
            status=status.value,
            subject=subject or content[:160],
            predicate=predicate,
            value_json=value or {"text": content},
            confidence=max(0.0, min(1.0, confidence)),
            authority=authority.value,
            valid_from=valid_from,
            valid_to=valid_to,
            ttl_seconds=ttl_seconds,
            provenance_json=provenance or [],
            supersedes=supersedes,
            sensitivity=sensitivity.value,
            project_id=project_id,
            task_id=task_id,
            user_id=user_id,
            created_by=created_by,
            verification_json=verification or {},
        )
        self.db_session.add(model)

        # 2. flush + refresh 后可以拿到数据库生成的 id、created_at 等字段。
        await self.db_session.flush()
        await self.db_session.refresh(model)
        return model.to_entity()

    async def get(self, memory_id: UUID) -> AgentMemory | None:
        stmt = (
            select(AgentMemoryModel)
            .where(AgentMemoryModel.id == memory_id)
            .where(AgentMemoryModel.deleted_at.is_(None))
        )
        result = await self.db_session.execute(stmt)
        model = result.scalar_one_or_none()
        return model.to_entity() if model else None

    async def list_active(
        self,
        *,
        kind: MemoryKind | None = None,
        enabled_only: bool = False,
        limit: int = 100,
    ) -> list[AgentMemory]:
        # 1. 默认只查未删除记忆。
        stmt = select(AgentMemoryModel).where(AgentMemoryModel.deleted_at.is_(None))

        # 2. 按类型和启用状态过滤，给前端管理面板和第41章检索复用。
        if kind is not None:
            stmt = stmt.where(AgentMemoryModel.kind == kind.value)
        if enabled_only:
            stmt = stmt.where(AgentMemoryModel.enabled.is_(True))

        # 3. 重要度高、更新时间新的记忆优先展示。
        stmt = stmt.order_by(
            AgentMemoryModel.importance.desc(),
            AgentMemoryModel.updated_at.desc(),
        ).limit(limit)
        result = await self.db_session.execute(stmt)
        return [model.to_entity() for model in result.scalars()]

    # ===================== 第4步：读取可以进入检索候选池的长期记忆 =====================
    async def list_retrievable(
        self,
        *,
        now: datetime,
        limit: int,
        project_id: str | None = None,
        task_id: UUID | None = None,
        user_id: str | None = None,
    ) -> list[AgentMemory]:
        """过滤禁用、软删除和已经过期的记忆。

        Repository 先做数据库层过滤，MemoryRetrievalService 再计算相关度。
        这样不会把明显无效的记录加载到应用层参与评分。
        """

        stmt = (
            select(AgentMemoryModel)
            .where(AgentMemoryModel.deleted_at.is_(None))
            .where(AgentMemoryModel.enabled.is_(True))
            .where(AgentMemoryModel.status == MemoryStatus.verified.value)
            .where(AgentMemoryModel.sensitivity != MemorySensitivity.secret.value)
            .where(
                or_(
                    AgentMemoryModel.valid_from.is_(None),
                    AgentMemoryModel.valid_from <= now,
                )
            )
            .where(
                or_(
                    AgentMemoryModel.valid_to > now,
                    AgentMemoryModel.valid_to.is_(None),
                )
            )
            .where(
                or_(
                    AgentMemoryModel.expires_at > now,
                    AgentMemoryModel.expires_at.is_(None),
                )
            )
            .order_by(
                AgentMemoryModel.importance.desc(),
                AgentMemoryModel.updated_at.desc(),
            )
            .limit(limit)
        )
        if project_id:
            stmt = stmt.where(
                or_(
                    AgentMemoryModel.project_id == project_id,
                    AgentMemoryModel.scope.in_([MemoryScope.user.value, MemoryScope.organization.value]),
                )
            )
        if task_id:
            stmt = stmt.where(
                or_(AgentMemoryModel.task_id == task_id, AgentMemoryModel.task_id.is_(None))
            )
        if user_id:
            stmt = stmt.where(
                or_(AgentMemoryModel.user_id == user_id, AgentMemoryModel.user_id.is_(None))
            )
        result = await self.db_session.execute(stmt)
        return [model.to_entity() for model in result.scalars()]

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
        stmt = (
            select(AgentMemoryModel)
            .where(AgentMemoryModel.id == memory_id)
            .where(AgentMemoryModel.deleted_at.is_(None))
        )
        result = await self.db_session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None

        # 1. 只更新调用方明确传入的字段，避免 PATCH 请求误清空数据。
        if content is not None:
            model.content = content
        if importance is not None:
            model.importance = importance
        if enabled is not None:
            model.enabled = enabled
        if expires_at is not None:
            model.expires_at = expires_at
        if metadata is not None:
            model.metadata_json = metadata
        if status is not None:
            model.status = status.value
        if provenance is not None:
            model.provenance_json = provenance
        if verification is not None:
            model.verification_json = verification
        if valid_to is not None:
            model.valid_to = valid_to
        if confidence is not None:
            model.confidence = max(0.0, min(1.0, confidence))
        if authority is not None:
            model.authority = authority.value
        if related_ids is not None:
            model.related_ids_json = [str(item) for item in related_ids]

        # 2. 手动更新时间，方便排序和前端判断最近改动。
        model.updated_at = datetime.now(UTC)
        await self.db_session.flush()
        await self.db_session.refresh(model)
        return model.to_entity()

    async def soft_delete(self, memory_id: UUID) -> AgentMemory | None:
        stmt = (
            select(AgentMemoryModel)
            .where(AgentMemoryModel.id == memory_id)
            .where(AgentMemoryModel.deleted_at.is_(None))
        )
        result = await self.db_session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        model.deleted_at = datetime.now(UTC)
        model.status = MemoryStatus.deleted.value
        model.updated_at = datetime.now(UTC)
        await self.db_session.flush()
        await self.db_session.refresh(model)
        return model.to_entity()

    async def mark_superseded(
        self,
        memory_id: UUID,
        *,
        replacement_id: UUID,
    ) -> AgentMemory | None:
        stmt = select(AgentMemoryModel).where(AgentMemoryModel.id == memory_id)
        result = await self.db_session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        model.status = MemoryStatus.superseded.value
        model.enabled = False
        model.valid_to = datetime.now(UTC)
        model.updated_at = datetime.now(UTC)
        metadata = dict(model.metadata_json or {})
        metadata["superseded_by"] = str(replacement_id)
        model.metadata_json = metadata
        await self.db_session.flush()
        await self.db_session.refresh(model)
        return model.to_entity()

    # ===================== 第5步：使用统计（检索命中自动 +1） =====================
    async def touch_access(self, memory_id: UUID, *, now: datetime) -> AgentMemory | None:
        """记录一次检索命中：access_count +1 并刷新 last_accessed_at。

        last_accessed_at 是艾宾浩斯衰减公式的时间锚点，命中越多记忆越不容易被遗忘。
        """
        stmt = select(AgentMemoryModel).where(AgentMemoryModel.id == memory_id)
        result = await self.db_session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        model.access_count = (model.access_count or 0) + 1
        model.last_accessed_at = now
        await self.db_session.flush()
        await self.db_session.refresh(model)
        return model.to_entity()

    # ===================== 第6步：生命周期任务扫描 =====================
    async def list_for_lifecycle(self, *, limit: int | None = None) -> list[AgentMemory]:
        """返回所有未软删除的记忆，供衰减/巩固等后台任务批量处理。"""
        stmt = select(AgentMemoryModel).where(AgentMemoryModel.deleted_at.is_(None))
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.db_session.execute(stmt)
        return [model.to_entity() for model in result.scalars()]

    # ===================== 第7步：生命周期审计事件 =====================
    async def record_audit_event(
        self,
        *,
        memory_id: UUID | None,
        event_type: str,
        payload: dict[str, object],
    ) -> UUID:
        """为记忆写入一条审计事件（冲突消解、巩固等自动化动作留痕）。"""
        model = MemoryAuditEventModel(
            memory_id=memory_id,
            event_type=event_type,
            payload=dict(payload or {}),
        )
        self.db_session.add(model)
        await self.db_session.flush()
        return model.id
