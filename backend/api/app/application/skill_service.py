"""技能注册中心应用服务。

技能（Skill）是团队沉淀的可复用操作指引：一段结构化 instructions
加上风险等级、标签与版本。服务承担三类职责：

- 治理：draft → published → deprecated 生命周期，published 不可原地改；
- 管理：CRUD、启停、版本演进（新版本 = 复制 + 递增 semver）；
- 注入：按当前任务做可解释的相关度选择，把命中的技能渲染进
  Agent 上下文，让模型按团队最佳实践行事。
"""

import re
from uuid import UUID

from app.application.unit_of_work import UnitOfWork
from app.core.config import settings
from app.core.exceptions import AppException
from app.domain.agent_core.tools import ToolRiskLevel
from app.domain.skills.entities import (
    Skill,
    SkillContext,
    SkillContextItem,
    SkillStatus,
)

_SKILL_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")
_SEMVER_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


class SkillService:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    # ===================== 第1步：创建与修改草稿 =====================
    async def create_skill(
        self,
        *,
        skill_key: str,
        name: str,
        description: str,
        instructions: str,
        version: str = "1.0.0",
        definition: dict[str, object] | None = None,
        risk_level: str = "low",
        tags: list[str] | None = None,
        created_by: str = "operator",
    ) -> Skill:
        key = skill_key.strip().lower()
        if not _SKILL_KEY_PATTERN.match(key):
            raise AppException(
                message="skill_key must match ^[a-z][a-z0-9_-]{2,63}$",
                code=400,
                status_code=400,
            )
        self._validate_version(version)
        self._validate_risk(risk_level)
        if not name.strip():
            raise AppException(message="skill name is required", code=400, status_code=400)
        if not instructions.strip():
            raise AppException(message="skill instructions are required", code=400, status_code=400)
        existing = await self.uow.skills.get_by_key_version(key, version)
        if existing is not None:
            raise AppException(
                message=f"skill {key}@{version} already exists",
                code=409,
                status_code=409,
            )
        skill = await self.uow.skills.add(
            skill_key=key,
            version=version,
            name=name.strip(),
            description=description.strip(),
            instructions=instructions.strip(),
            definition=definition or {},
            risk_level=risk_level,
            tags=[tag.strip() for tag in (tags or []) if tag.strip()],
            created_by=created_by,
        )
        await self.uow.commit()
        return skill

    async def update_skill(
        self,
        skill_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        instructions: str | None = None,
        definition: dict[str, object] | None = None,
        risk_level: str | None = None,
        tags: list[str] | None = None,
    ) -> Skill:
        skill = await self._require_skill(skill_id)
        # 生产纪律：published 内容冻结。要改内容必须开新版本。
        if skill.status is not SkillStatus.draft:
            raise AppException(
                message="only draft skills can be edited; create a new version instead",
                code=409,
                status_code=409,
            )
        if risk_level is not None:
            self._validate_risk(risk_level)
        updated = await self.uow.skills.update_draft(
            skill_id,
            name=name.strip() if name else None,
            description=description,
            instructions=instructions,
            definition=definition,
            risk_level=risk_level,
            tags=[tag.strip() for tag in tags if tag.strip()] if tags is not None else None,
        )
        await self.uow.commit()
        assert updated is not None
        return updated

    # ===================== 第2步：发布、启停与版本演进 =====================
    async def publish_skill(self, skill_id: UUID) -> Skill:
        skill = await self._require_skill(skill_id)
        if skill.status is SkillStatus.published:
            return skill
        if skill.status is not SkillStatus.draft:
            raise AppException(
                message=f"cannot publish a {skill.status.value} skill",
                code=409,
                status_code=409,
            )
        if not skill.instructions.strip():
            raise AppException(
                message="cannot publish a skill without instructions",
                code=422,
                status_code=422,
            )
        published = await self.uow.skills.set_status(
            skill_id, status=SkillStatus.published, mark_published=True
        )
        await self.uow.commit()
        assert published is not None
        return published

    async def set_enabled(self, skill_id: UUID, *, enabled: bool) -> Skill:
        skill = await self._require_skill(skill_id)
        if enabled and skill.status is not SkillStatus.published:
            raise AppException(
                message="only published skills can be enabled",
                code=409,
                status_code=409,
            )
        updated = await self.uow.skills.set_enabled(skill_id, enabled=enabled)
        await self.uow.commit()
        assert updated is not None
        return updated

    async def deprecate_skill(self, skill_id: UUID) -> Skill:
        skill = await self._require_skill(skill_id)
        if skill.status is not SkillStatus.published:
            raise AppException(
                message="only published skills can be deprecated",
                code=409,
                status_code=409,
            )
        await self.uow.skills.set_enabled(skill_id, enabled=False)
        updated = await self.uow.skills.set_status(skill_id, status=SkillStatus.deprecated)
        await self.uow.commit()
        assert updated is not None
        return updated

    async def create_new_version(
        self,
        skill_id: UUID,
        *,
        version: str | None = None,
        created_by: str = "operator",
    ) -> Skill:
        """从既有版本复制出下一个 draft 版本。"""

        source = await self._require_skill(skill_id)
        next_version = version or self._bump_patch(source.version)
        self._validate_version(next_version)
        if not self._is_newer(next_version, source.version):
            raise AppException(
                message=f"new version {next_version} must be greater than {source.version}",
                code=400,
                status_code=400,
            )
        existing = await self.uow.skills.get_by_key_version(source.skill_key, next_version)
        if existing is not None:
            raise AppException(
                message=f"skill {source.skill_key}@{next_version} already exists",
                code=409,
                status_code=409,
            )
        draft = await self.uow.skills.add(
            skill_key=source.skill_key,
            version=next_version,
            name=source.name,
            description=source.description,
            instructions=source.instructions,
            definition=dict(source.definition),
            risk_level=source.risk_level.value,
            tags=list(source.tags),
            created_by=created_by,
        )
        await self.uow.commit()
        return draft

    async def record_test(self, skill_id: UUID, *, test_record: dict[str, object]) -> Skill:
        await self._require_skill(skill_id)
        updated = await self.uow.skills.record_test(skill_id, test_record=test_record)
        await self.uow.commit()
        assert updated is not None
        return updated

    # ===================== 第3步：查询与删除 =====================
    async def list_skills(
        self,
        *,
        status: SkillStatus | None = None,
        enabled_only: bool = False,
        search: str | None = None,
        limit: int = 200,
    ) -> list[Skill]:
        return await self.uow.skills.list_active(
            status=status, enabled_only=enabled_only, search=search, limit=limit
        )

    async def list_versions(self, skill_key: str) -> list[Skill]:
        versions = await self.uow.skills.list_versions(skill_key.strip().lower())
        if not versions:
            raise AppException(message="skill not found", code=404, status_code=404)
        return versions

    async def get_skill(self, skill_id: UUID) -> Skill:
        return await self._require_skill(skill_id)

    async def delete_skill(self, skill_id: UUID) -> Skill:
        skill = await self._require_skill(skill_id)
        if skill.status is SkillStatus.published and skill.enabled:
            raise AppException(
                message="disable the skill before deleting it",
                code=409,
                status_code=409,
            )
        deleted = await self.uow.skills.soft_delete(skill_id)
        await self.uow.commit()
        return deleted or skill

    # ===================== 第4步：Agent 上下文注入 =====================
    async def build_skill_context(self, *, query: str) -> SkillContext:
        """按词法相关度挑选少量可注入技能，带条数与字符双预算。"""

        clean_query = " ".join(query.split())
        candidates = await self.uow.skills.list_injectable(limit=100)
        query_terms = self._tokenize(clean_query)

        ranked: list[SkillContextItem] = []
        for skill in candidates:
            skill_text = " ".join([skill.name, skill.description, " ".join(skill.tags)])
            skill_terms = self._tokenize(skill_text + " " + skill.instructions[:400])
            matched = sorted(query_terms & skill_terms, key=lambda term: (-len(term), term))[:8]
            matched_weight = sum(max(len(term), 1) for term in matched)
            query_weight = min(sum(max(len(term), 1) for term in query_terms) or 1, 40)
            score = min(matched_weight / query_weight, 1.0)
            if score < settings.context_skill_min_score:
                continue
            ranked.append(
                SkillContextItem(
                    id=skill.id,
                    skill_key=skill.skill_key,
                    version=skill.version,
                    name=skill.name,
                    instructions=skill.instructions,
                    risk_level=skill.risk_level.value,
                    relevance_score=round(score, 4),
                    matched_terms=matched,
                )
            )
        ranked.sort(key=lambda item: item.relevance_score, reverse=True)

        included: list[SkillContextItem] = []
        used_chars = 0
        for item in ranked:
            if len(included) >= settings.context_skill_limit:
                break
            remaining = settings.context_skill_max_chars - used_chars
            if remaining <= 0:
                break
            if len(item.instructions) > remaining:
                if remaining <= 12:
                    break
                item.instructions = item.instructions[: remaining - 9] + "...[已裁剪]"
            included.append(item)
            used_chars += len(item.instructions)

        return SkillContext(
            query=clean_query[:1000],
            items=included,
            candidate_count=len(candidates),
            omitted_count=max(len(ranked) - len(included), 0),
            total_chars=used_chars,
        )

    @staticmethod
    def render_skill_context(context: SkillContext) -> str:
        """把技能上下文渲染成 Agent 提示词片段。"""

        if not context.items:
            return ""
        lines = [
            (
                f"- [{item.skill_key}@{item.version}] {item.name}"
                f"（风险 {item.risk_level}，相关度 {item.relevance_score:.2f}）：\n"
                f"  {item.instructions}"
            )
            for item in context.items
        ]
        return "可用技能（按团队沉淀的最佳实践执行）：\n" + "\n".join(lines)

    # ===================== 内部校验工具 =====================
    async def _require_skill(self, skill_id: UUID) -> Skill:
        skill = await self.uow.skills.get(skill_id)
        if skill is None:
            raise AppException(message="skill not found", code=404, status_code=404)
        return skill

    @staticmethod
    def _validate_version(version: str) -> None:
        if not _SEMVER_PATTERN.match(version):
            raise AppException(
                message="version must be semver: MAJOR.MINOR.PATCH",
                code=400,
                status_code=400,
            )

    @staticmethod
    def _validate_risk(risk_level: str) -> None:
        try:
            ToolRiskLevel(risk_level)
        except ValueError as exc:
            raise AppException(
                message=f"unsupported risk level: {risk_level}",
                code=400,
                status_code=400,
            ) from exc

    @staticmethod
    def _bump_patch(version: str) -> str:
        match = _SEMVER_PATTERN.match(version)
        if not match:
            return "1.0.0"
        major, minor, patch = (int(part) for part in match.groups())
        return f"{major}.{minor}.{patch + 1}"

    @staticmethod
    def _is_newer(candidate: str, current: str) -> bool:
        left = tuple(int(part) for part in candidate.split("."))
        right = tuple(int(part) for part in current.split("."))
        return left > right

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        normalized = text.lower()
        terms = set(re.findall(r"[a-z0-9_]+", normalized))
        for block in re.findall(r"[一-鿿]+", normalized):
            for size in (2, 3, 4):
                if len(block) < size:
                    continue
                terms.update(
                    block[index : index + size] for index in range(len(block) - size + 1)
                )
        return terms
