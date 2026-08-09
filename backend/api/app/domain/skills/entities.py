from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from app.domain.agent_core.tools import ToolRiskLevel


class SkillStatus(StrEnum):
    """技能的发布生命周期。

    - draft：可以随意修改，不会注入 Agent 上下文；
    - published：内容冻结，允许启用并注入；
    - deprecated：保留历史记录与审计，不再注入；
    - archived：彻底下线，仅供追溯。

    生产纪律：published 版本不可原地修改。要改内容必须开新版本，
    这样每一次 Agent 行为都能回溯到当时生效的技能定义。
    """

    draft = "draft"
    published = "published"
    deprecated = "deprecated"
    archived = "archived"


@dataclass(slots=True)
class Skill:
    """技能注册中心里的一条技能版本。

    技能 = 一段结构化的操作指引（instructions）+ 元数据。
    Agent 执行时把命中的技能注入上下文，让模型按团队沉淀的
    最佳实践行事，而不是每次从零发挥。
    """

    id: UUID
    skill_key: str
    version: str
    name: str
    description: str
    instructions: str
    definition: dict[str, object]
    risk_level: ToolRiskLevel
    status: SkillStatus
    enabled: bool
    tags: list[str] = field(default_factory=list)
    test_record: dict[str, object] = field(default_factory=dict)
    created_by: str = "system"
    created_at: datetime | None = None
    updated_at: datetime | None = None
    published_at: datetime | None = None
    deleted_at: datetime | None = None

    def is_injectable(self) -> bool:
        """只有已发布且启用的技能才能进入 Agent 上下文。"""

        return (
            self.enabled
            and self.deleted_at is None
            and self.status is SkillStatus.published
        )


@dataclass(slots=True)
class SkillContextItem:
    """注入上下文的技能条目，附带可解释的选中原因。"""

    id: UUID
    skill_key: str
    version: str
    name: str
    instructions: str
    risk_level: str
    relevance_score: float
    matched_terms: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SkillContext:
    """一次技能选择的结果，与 MemoryContext 使用相同的预算语言。"""

    query: str
    items: list[SkillContextItem] = field(default_factory=list)
    candidate_count: int = 0
    omitted_count: int = 0
    total_chars: int = 0
