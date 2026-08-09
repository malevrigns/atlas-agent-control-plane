from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.skills.entities import Skill, SkillStatus
from app.domain.skills.repositories import SkillRepository
from app.infrastructure.database.models.skill import SkillModel


class SqlAlchemySkillRepository(SkillRepository):
    """使用 SQLAlchemy 实现技能注册中心读写。"""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def add(
        self,
        *,
        skill_key: str,
        version: str,
        name: str,
        description: str,
        instructions: str,
        definition: dict[str, object],
        risk_level: str,
        tags: list[str],
        created_by: str,
    ) -> Skill:
        model = SkillModel(
            skill_key=skill_key,
            version=version,
            name=name,
            description=description,
            instructions=instructions,
            definition=definition,
            risk_level=risk_level,
            status=SkillStatus.draft.value,
            enabled=False,
            tags=list(tags),
            created_by=created_by,
        )
        self.db_session.add(model)
        await self.db_session.flush()
        await self.db_session.refresh(model)
        return model.to_entity()

    async def get(self, skill_id: UUID) -> Skill | None:
        model = await self._get_model(skill_id)
        return model.to_entity() if model else None

    async def get_by_key_version(self, skill_key: str, version: str) -> Skill | None:
        stmt = (
            select(SkillModel)
            .where(SkillModel.skill_key == skill_key)
            .where(SkillModel.version == version)
            .where(SkillModel.deleted_at.is_(None))
        )
        result = await self.db_session.execute(stmt)
        model = result.scalar_one_or_none()
        return model.to_entity() if model else None

    async def list_versions(self, skill_key: str) -> list[Skill]:
        stmt = (
            select(SkillModel)
            .where(SkillModel.skill_key == skill_key)
            .where(SkillModel.deleted_at.is_(None))
            .order_by(SkillModel.created_at.desc())
        )
        result = await self.db_session.execute(stmt)
        return [model.to_entity() for model in result.scalars()]

    async def list_active(
        self,
        *,
        status: SkillStatus | None = None,
        enabled_only: bool = False,
        search: str | None = None,
        limit: int = 200,
    ) -> list[Skill]:
        stmt = select(SkillModel).where(SkillModel.deleted_at.is_(None))
        if status is not None:
            stmt = stmt.where(SkillModel.status == status.value)
        if enabled_only:
            stmt = stmt.where(SkillModel.enabled.is_(True))
        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    SkillModel.skill_key.ilike(pattern),
                    SkillModel.name.ilike(pattern),
                    SkillModel.description.ilike(pattern),
                )
            )
        stmt = stmt.order_by(SkillModel.updated_at.desc()).limit(limit)
        result = await self.db_session.execute(stmt)
        return [model.to_entity() for model in result.scalars()]

    async def list_injectable(self, *, limit: int = 100) -> list[Skill]:
        stmt = (
            select(SkillModel)
            .where(SkillModel.deleted_at.is_(None))
            .where(SkillModel.enabled.is_(True))
            .where(SkillModel.status == SkillStatus.published.value)
            .order_by(SkillModel.updated_at.desc())
            .limit(limit)
        )
        result = await self.db_session.execute(stmt)
        return [model.to_entity() for model in result.scalars()]

    async def update_draft(
        self,
        skill_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        instructions: str | None = None,
        definition: dict[str, object] | None = None,
        risk_level: str | None = None,
        tags: list[str] | None = None,
    ) -> Skill | None:
        model = await self._get_model(skill_id)
        if model is None:
            return None
        if name is not None:
            model.name = name
        if description is not None:
            model.description = description
        if instructions is not None:
            model.instructions = instructions
        if definition is not None:
            model.definition = definition
        if risk_level is not None:
            model.risk_level = risk_level
        if tags is not None:
            model.tags = list(tags)
        model.updated_at = datetime.now(UTC)
        await self.db_session.flush()
        await self.db_session.refresh(model)
        return model.to_entity()

    async def set_status(
        self,
        skill_id: UUID,
        *,
        status: SkillStatus,
        mark_published: bool = False,
    ) -> Skill | None:
        model = await self._get_model(skill_id)
        if model is None:
            return None
        model.status = status.value
        if mark_published:
            model.published_at = datetime.now(UTC)
        model.updated_at = datetime.now(UTC)
        await self.db_session.flush()
        await self.db_session.refresh(model)
        return model.to_entity()

    async def set_enabled(self, skill_id: UUID, *, enabled: bool) -> Skill | None:
        model = await self._get_model(skill_id)
        if model is None:
            return None
        model.enabled = enabled
        model.updated_at = datetime.now(UTC)
        await self.db_session.flush()
        await self.db_session.refresh(model)
        return model.to_entity()

    async def record_test(
        self,
        skill_id: UUID,
        *,
        test_record: dict[str, object],
    ) -> Skill | None:
        model = await self._get_model(skill_id)
        if model is None:
            return None
        model.test_record = test_record
        model.updated_at = datetime.now(UTC)
        await self.db_session.flush()
        await self.db_session.refresh(model)
        return model.to_entity()

    async def soft_delete(self, skill_id: UUID) -> Skill | None:
        model = await self._get_model(skill_id)
        if model is None:
            return None
        model.deleted_at = datetime.now(UTC)
        model.enabled = False
        model.updated_at = datetime.now(UTC)
        await self.db_session.flush()
        await self.db_session.refresh(model)
        return model.to_entity()

    async def _get_model(self, skill_id: UUID) -> SkillModel | None:
        stmt = (
            select(SkillModel)
            .where(SkillModel.id == skill_id)
            .where(SkillModel.deleted_at.is_(None))
        )
        result = await self.db_session.execute(stmt)
        return result.scalar_one_or_none()
