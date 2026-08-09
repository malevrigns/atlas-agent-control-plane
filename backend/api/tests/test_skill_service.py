import asyncio
import unittest
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.core.exceptions import AppException
from app.domain.agent_core.tools import ToolRiskLevel
from app.domain.skills.entities import Skill, SkillStatus
from app.application.skill_service import SkillService


class FakeSkillRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, Skill] = {}

    async def add(self, **kwargs) -> Skill:
        skill = Skill(
            id=uuid4(),
            skill_key=kwargs["skill_key"],
            version=kwargs["version"],
            name=kwargs["name"],
            description=kwargs["description"],
            instructions=kwargs["instructions"],
            definition=kwargs["definition"],
            risk_level=ToolRiskLevel(kwargs["risk_level"]),
            status=SkillStatus.draft,
            enabled=False,
            tags=kwargs["tags"],
            created_by=kwargs["created_by"],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self.items[skill.id] = skill
        return skill

    async def get(self, skill_id):
        skill = self.items.get(skill_id)
        return skill if skill and skill.deleted_at is None else None

    async def get_by_key_version(self, skill_key, version):
        for skill in self.items.values():
            if (
                skill.skill_key == skill_key
                and skill.version == version
                and skill.deleted_at is None
            ):
                return skill
        return None

    async def list_versions(self, skill_key):
        return [
            skill
            for skill in self.items.values()
            if skill.skill_key == skill_key and skill.deleted_at is None
        ]

    async def list_active(self, *, status=None, enabled_only=False, search=None, limit=200):
        skills = [skill for skill in self.items.values() if skill.deleted_at is None]
        if status is not None:
            skills = [skill for skill in skills if skill.status is status]
        if enabled_only:
            skills = [skill for skill in skills if skill.enabled]
        return skills[:limit]

    async def list_injectable(self, *, limit=100):
        return [
            skill
            for skill in self.items.values()
            if skill.is_injectable()
        ][:limit]

    async def update_draft(self, skill_id, **kwargs):
        skill = self.items.get(skill_id)
        if skill is None:
            return None
        for key, value in kwargs.items():
            if value is not None:
                if key == "risk_level":
                    value = ToolRiskLevel(value)
                setattr(skill, key, value)
        return skill

    async def set_status(self, skill_id, *, status, mark_published=False):
        skill = self.items.get(skill_id)
        if skill is None:
            return None
        skill.status = status
        if mark_published:
            skill.published_at = datetime.now(UTC)
        return skill

    async def set_enabled(self, skill_id, *, enabled):
        skill = self.items.get(skill_id)
        if skill is None:
            return None
        skill.enabled = enabled
        return skill

    async def record_test(self, skill_id, *, test_record):
        skill = self.items.get(skill_id)
        if skill is None:
            return None
        skill.test_record = test_record
        return skill

    async def soft_delete(self, skill_id):
        skill = self.items.get(skill_id)
        if skill is None:
            return None
        skill.deleted_at = datetime.now(UTC)
        skill.enabled = False
        return skill


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.skills = FakeSkillRepository()
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        pass


def build_service() -> tuple[SkillService, FakeUnitOfWork]:
    uow = FakeUnitOfWork()
    return SkillService(uow), uow


async def create_published_skill(service: SkillService, **overrides) -> Skill:
    payload = {
        "skill_key": "deploy-check",
        "name": "部署前检查",
        "description": "发布前的标准检查动作",
        "instructions": "先运行测试，再核对迁移，最后检查回滚脚本。",
        "tags": ["部署", "发布"],
    }
    payload.update(overrides)
    skill = await service.create_skill(**payload)
    skill = await service.publish_skill(skill.id)
    return await service.set_enabled(skill.id, enabled=True)


class SkillServiceTests(unittest.TestCase):
    """技能治理：生命周期、版本演进与上下文注入。"""

    def test_create_validates_key_and_version(self) -> None:
        async def scenario() -> None:
            service, _ = build_service()
            with self.assertRaises(AppException):
                await service.create_skill(
                    skill_key="Bad Key!", name="n", description="", instructions="i"
                )
            with self.assertRaises(AppException):
                await service.create_skill(
                    skill_key="good-key",
                    name="n",
                    description="",
                    instructions="i",
                    version="not-semver",
                )

        asyncio.run(scenario())

    def test_published_skill_cannot_be_edited_in_place(self) -> None:
        async def scenario() -> None:
            service, _ = build_service()
            skill = await create_published_skill(service)
            with self.assertRaises(AppException) as context:
                await service.update_skill(skill.id, instructions="改内容")
            self.assertEqual(context.exception.status_code, 409)

        asyncio.run(scenario())

    def test_only_published_skill_can_be_enabled(self) -> None:
        async def scenario() -> None:
            service, _ = build_service()
            draft = await service.create_skill(
                skill_key="draft-skill",
                name="草稿",
                description="",
                instructions="草稿内容",
            )
            with self.assertRaises(AppException):
                await service.set_enabled(draft.id, enabled=True)

        asyncio.run(scenario())

    def test_new_version_copies_content_and_bumps_semver(self) -> None:
        async def scenario() -> None:
            service, _ = build_service()
            skill = await create_published_skill(service)
            draft = await service.create_new_version(skill.id)
            self.assertEqual(draft.version, "1.0.1")
            self.assertIs(draft.status, SkillStatus.draft)
            self.assertEqual(draft.instructions, skill.instructions)
            with self.assertRaises(AppException):
                await service.create_new_version(skill.id, version="0.9.0")

        asyncio.run(scenario())

    def test_deprecate_disables_injection(self) -> None:
        async def scenario() -> None:
            service, _ = build_service()
            skill = await create_published_skill(service)
            deprecated = await service.deprecate_skill(skill.id)
            self.assertIs(deprecated.status, SkillStatus.deprecated)
            self.assertFalse(deprecated.enabled)
            context = await service.build_skill_context(query="部署 发布 检查")
            self.assertEqual(context.items, [])

        asyncio.run(scenario())

    def test_context_selects_relevant_skills_with_budget(self) -> None:
        async def scenario() -> None:
            service, _ = build_service()
            await create_published_skill(service)
            await create_published_skill(
                service,
                skill_key="incident-response",
                name="故障响应",
                description="线上故障的分级与止血",
                instructions="先定级，再止血，最后写复盘。",
                tags=["故障"],
            )
            context = await service.build_skill_context(query="准备一次生产部署发布")
            self.assertGreaterEqual(len(context.items), 1)
            self.assertEqual(context.items[0].skill_key, "deploy-check")
            rendered = SkillService.render_skill_context(context)
            self.assertIn("deploy-check@1.0.0", rendered)
            unrelated = await service.build_skill_context(query="完全无关的话题词汇")
            self.assertEqual(unrelated.items, [])

        asyncio.run(scenario())

    def test_enabled_published_skill_cannot_be_deleted_directly(self) -> None:
        async def scenario() -> None:
            service, _ = build_service()
            skill = await create_published_skill(service)
            with self.assertRaises(AppException):
                await service.delete_skill(skill.id)
            await service.set_enabled(skill.id, enabled=False)
            deleted = await service.delete_skill(skill.id)
            self.assertIsNotNone(deleted.deleted_at)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
