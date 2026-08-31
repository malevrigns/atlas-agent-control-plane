from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.agent_core.tools import ToolRiskLevel
from app.domain.skills.entities import Skill, SkillStatus
from app.infrastructure.database.base import Base
from app.infrastructure.database.types import JsonValue, UtcDateTime, UuidValue, json_default


class SkillModel(Base):
    """技能注册中心数据库模型。

    第 45 章的 Control Plane 迁移已经预留了 skills 表，本章把它
    从"休眠表"激活为完整的注册中心：补充展示名、指引正文、标签、
    启用开关与审计时间，并保持 (skill_key, version) 唯一约束。
    """

    __tablename__ = "skills"

    id: Mapped[UUID] = mapped_column(UuidValue, primary_key=True, default=uuid4)
    skill_key: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # instructions 是技能的核心资产：注入模型上下文的操作指引正文。
    instructions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    definition: Mapped[dict[str, object]] = mapped_column(
        JsonValue, nullable=False, default=dict, server_default=json_default("{}")
    )
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, default="low")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    tags: Mapped[list[object]] = mapped_column(
        JsonValue, nullable=False, default=list, server_default=json_default("[]")
    )
    test_record: Mapped[dict[str, object]] = mapped_column(
        JsonValue, nullable=False, default=dict, server_default=json_default("{}")
    )
    created_by: Mapped[str] = mapped_column(String(128), nullable=False, default="system")
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    published_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    deleted_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    def to_entity(self) -> Skill:
        # 兼容第 45 章迁移创建的历史行：status 可能仍是 candidate。
        raw_status = self.status if self.status in set(SkillStatus) else SkillStatus.draft.value
        return Skill(
            id=self.id,
            skill_key=self.skill_key,
            version=self.version,
            name=self.name or self.skill_key,
            description=self.description,
            instructions=self.instructions,
            definition=dict(self.definition or {}),
            risk_level=ToolRiskLevel(self.risk_level),
            status=SkillStatus(raw_status),
            enabled=self.enabled,
            tags=[str(tag) for tag in (self.tags or [])],
            test_record=dict(self.test_record or {}),
            created_by=self.created_by,
            created_at=self.created_at,
            updated_at=self.updated_at,
            published_at=self.published_at,
            deleted_at=self.deleted_at,
        )
