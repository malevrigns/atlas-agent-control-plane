from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.memories.entities import (
    AgentMemory,
    MemoryAuthority,
    MemoryKind,
    MemoryScope,
    MemorySensitivity,
    MemoryStatus,
)
from app.infrastructure.database.base import Base
from app.infrastructure.database.types import JsonValue, UtcDateTime, UuidValue, json_default


class AgentMemoryModel(Base):
    """长期记忆数据库模型。

    这个模型只描述 PostgreSQL 表结构和 ORM 映射。记忆抽取、确认、
    禁用等业务规则仍然放在 MemoryService 中。
    """

    __tablename__ = "agent_memories"

    # ===================== 第1步：定义记忆主体字段 =====================
    id: Mapped[UUID] = mapped_column(UuidValue, primary_key=True, default=uuid4)
    # kind 保存稳定的业务分类，例如 user_preference、project_fact。
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    # content 是后续可能注入模型上下文的记忆正文。
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # importance 取值 1-5，第41章会把它作为检索排序权重之一。
    importance: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    # enabled=false 表示暂时禁用，但仍保留记录和来源信息。
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # ===================== 第2步：保存记忆来源和生命周期 =====================
    source_session_id: Mapped[UUID | None] = mapped_column(
        UuidValue,
        ForeignKey("sessions.id", ondelete="SET NULL"),
    )
    source_event_id: Mapped[UUID | None] = mapped_column(
        UuidValue,
        ForeignKey("session_events.id", ondelete="SET NULL"),
    )
    # expires_at 为空表示长期有效；有值时，第41章检索会过滤过期记忆。
    expires_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    # metadata 保存抽取规则、来源类型等可扩展信息。
    metadata_json: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JsonValue,
        nullable=False,
        default=dict,
        server_default=json_default("{}"),
    )

    # ===================== Memory Control Plane fields =====================
    scope: Mapped[str] = mapped_column(String(32), nullable=False, default="project")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="verified")
    subject: Mapped[str] = mapped_column(Text, nullable=False, default="")
    predicate: Mapped[str] = mapped_column(String(128), nullable=False, default="states")
    value_json: Mapped[dict[str, object]] = mapped_column(
        "value", JsonValue, nullable=False, default=dict, server_default=json_default("{}")
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    authority: Mapped[str] = mapped_column(String(32), nullable=False, default="explicit_user")
    valid_from: Mapped[datetime | None] = mapped_column(UtcDateTime)
    valid_to: Mapped[datetime | None] = mapped_column(UtcDateTime)
    ttl_seconds: Mapped[int | None] = mapped_column(Integer)
    provenance_json: Mapped[list[object]] = mapped_column(
        "provenance", JsonValue, nullable=False, default=list, server_default=json_default("[]")
    )
    supersedes: Mapped[UUID | None] = mapped_column(
        UuidValue, ForeignKey("agent_memories.id", ondelete="SET NULL")
    )
    sensitivity: Mapped[str] = mapped_column(String(32), nullable=False, default="internal")
    project_id: Mapped[str | None] = mapped_column(String(128))
    task_id: Mapped[UUID | None] = mapped_column(
        UuidValue, ForeignKey("agent_tasks.id", ondelete="SET NULL")
    )
    user_id: Mapped[str | None] = mapped_column(String(128))
    created_by: Mapped[str] = mapped_column(String(128), nullable=False, default="system")
    verification_json: Mapped[dict[str, object]] = mapped_column(
        "verification", JsonValue, nullable=False, default=dict, server_default=json_default("{}")
    )

    # ===================== Memory Lifecycle fields =====================
    # related_ids 保存图谱关联的记忆 id，检索命中时用于扩展上下文。
    related_ids_json: Mapped[list[object]] = mapped_column(
        "related_ids", JsonValue, nullable=False, default=list, server_default=json_default("[]")
    )
    # access_count 累计检索命中次数，last_accessed_at 是艾宾浩斯衰减的时间锚点。
    access_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_accessed_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    # ===================== 第3步：记录审计时间 =====================
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime,
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    # ===================== 第4步：把 ORM 模型转换为领域实体 =====================
    def to_entity(self) -> AgentMemory:
        """返回不依赖 SQLAlchemy 的领域对象，供应用层继续处理。"""

        return AgentMemory(
            id=self.id,
            kind=MemoryKind(self.kind),
            content=self.content,
            importance=self.importance,
            enabled=self.enabled,
            source_session_id=self.source_session_id,
            source_event_id=self.source_event_id,
            expires_at=self.expires_at,
            metadata=dict(self.metadata_json or {}),
            scope=MemoryScope(self.scope),
            status=MemoryStatus(self.status),
            subject=self.subject,
            predicate=self.predicate,
            value=dict(self.value_json or {}),
            confidence=self.confidence,
            authority=MemoryAuthority(self.authority),
            valid_from=self.valid_from,
            valid_to=self.valid_to,
            ttl_seconds=self.ttl_seconds,
            provenance=[str(item) for item in (self.provenance_json or [])],
            supersedes=self.supersedes,
            sensitivity=MemorySensitivity(self.sensitivity),
            project_id=self.project_id,
            task_id=self.task_id,
            user_id=self.user_id,
            created_by=self.created_by,
            verification=dict(self.verification_json or {}),
            created_at=self.created_at,
            updated_at=self.updated_at,
            deleted_at=self.deleted_at,
            related_ids=self._parse_uuid_list(self.related_ids_json),
            access_count=self.access_count or 0,
            last_accessed_at=self.last_accessed_at,
        )

    @staticmethod
    def _parse_uuid_list(raw: list[object] | None) -> list[UUID]:
        """把 JsonValue 中保存的关联 id 解析回 UUID，跳过非法条目。"""

        result: list[UUID] = []
        for item in raw or []:
            try:
                result.append(UUID(str(item)))
            except (TypeError, ValueError):
                continue
        return result


class MemoryAuditEventModel(Base):
    """记忆生命周期审计事件表。

    冲突消解、衰减、巩固等自动化动作都会在这里留下一条可追溯记录，
    便于事后回答“这条记忆为什么被标记 superseded / 权威度为什么变了”。
    """

    __tablename__ = "memory_audit_events"

    id: Mapped[UUID] = mapped_column(UuidValue, primary_key=True, default=uuid4)
    # memory_id 为空表示事件不绑定单条记忆（例如整批衰减汇总）。
    memory_id: Mapped[UUID | None] = mapped_column(
        UuidValue, ForeignKey("agent_memories.id", ondelete="SET NULL")
    )
    # event_type 例如 conflict_resolved / conflict_manual_review / consolidated / decay_applied。
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(
        JsonValue, nullable=False, default=dict, server_default=json_default("{}")
    )
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, server_default=func.now()
    )
