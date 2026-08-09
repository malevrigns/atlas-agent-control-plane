from typing import Protocol
from uuid import UUID

from app.domain.skills.entities import Skill, SkillStatus


class SkillRepository(Protocol):
    """技能注册中心仓库协议。"""

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
        raise NotImplementedError

    async def get(self, skill_id: UUID) -> Skill | None:
        raise NotImplementedError

    async def get_by_key_version(self, skill_key: str, version: str) -> Skill | None:
        raise NotImplementedError

    async def list_versions(self, skill_key: str) -> list[Skill]:
        raise NotImplementedError

    async def list_active(
        self,
        *,
        status: SkillStatus | None = None,
        enabled_only: bool = False,
        search: str | None = None,
        limit: int = 200,
    ) -> list[Skill]:
        raise NotImplementedError

    async def list_injectable(self, *, limit: int = 100) -> list[Skill]:
        """返回 published 且 enabled 的技能，供上下文注入使用。"""

        raise NotImplementedError

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
        raise NotImplementedError

    async def set_status(
        self,
        skill_id: UUID,
        *,
        status: SkillStatus,
        mark_published: bool = False,
    ) -> Skill | None:
        raise NotImplementedError

    async def set_enabled(self, skill_id: UUID, *, enabled: bool) -> Skill | None:
        raise NotImplementedError

    async def record_test(
        self,
        skill_id: UUID,
        *,
        test_record: dict[str, object],
    ) -> Skill | None:
        raise NotImplementedError

    async def soft_delete(self, skill_id: UUID) -> Skill | None:
        raise NotImplementedError
