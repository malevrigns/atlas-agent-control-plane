from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID


class MemoryKind(StrEnum):
    """长期记忆的业务类型。

    旧版四种类型继续保留，避免破坏已有 API；新增类型对应 Memory Control
    Plane 中的情景、决策、环境与已验证缺陷经验。
    """

    user_preference = "user_preference"
    project_fact = "project_fact"
    task_experience = "task_experience"
    constraint = "constraint"
    requirement = "requirement"
    decision = "decision"
    environment = "environment"
    bug_lesson = "bug_lesson"
    episode = "episode"
    code_fact = "code_fact"


class MemoryScope(StrEnum):
    session = "session"
    task = "task"
    project = "project"
    user = "user"
    organization = "organization"


class MemoryStatus(StrEnum):
    candidate = "candidate"
    verified = "verified"
    superseded = "superseded"
    expired = "expired"
    deleted = "deleted"


class MemoryAuthority(StrEnum):
    """记忆的权威级别。"""

    explicit_user = "explicit_user"
    tool_verified = "tool_verified"
    test_verified = "test_verified"
    suggested = "suggested"
    verified = "verified"
    agent_inferred = "agent_inferred"

class MemorySensitivity(StrEnum):
    public = "public"
    internal = "internal"
    confidential = "confidential"
    secret = "secret"


@dataclass(slots=True)
class AgentMemory:
    """经过写入门禁管理的一条类型化长期记忆。

    ``content`` 和 ``enabled`` 是旧版兼容投影；事实字段由
    subject/predicate/value、status、provenance 和有效期共同定义。
    """

    id: UUID
    kind: MemoryKind
    content: str
    importance: int
    enabled: bool
    source_session_id: UUID | None
    source_event_id: UUID | None
    expires_at: datetime | None
    metadata: dict[str, object] = field(default_factory=dict)
    scope: MemoryScope = MemoryScope.project
    status: MemoryStatus = MemoryStatus.verified
    subject: str = ""
    predicate: str = "states"
    value: dict[str, object] = field(default_factory=dict)
    confidence: float = 1.0
    authority: MemoryAuthority = MemoryAuthority.explicit_user
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    ttl_seconds: int | None = None
    provenance: list[str] = field(default_factory=list)
    supersedes: UUID | None = None
    sensitivity: MemorySensitivity = MemorySensitivity.internal
    project_id: str | None = None
    task_id: UUID | None = None
    user_id: str | None = None
    created_by: str = "system"
    verification: dict[str, object] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None
    # 图谱关联：与当前记忆存在 supports/contradicts/extends/duplicates 关系的记忆 id。
    related_ids: list[UUID] = field(default_factory=list)
    # 使用统计：检索命中次数与最近一次命中时间，供衰减公式锚定。
    access_count: int = 0
    last_accessed_at: datetime | None = None

    def is_retrievable(self, now: datetime | None = None) -> bool:
        current_time = now or datetime.now(UTC)
        deadline = self.valid_to or self.expires_at
        return (
            self.enabled
            and self.deleted_at is None
            and self.status is MemoryStatus.verified
            and (self.valid_from is None or self.valid_from <= current_time)
            and (deadline is None or deadline > current_time)
            and self.sensitivity is not MemorySensitivity.secret
        )


@dataclass(slots=True)
class MemoryCandidate:
    """等待 Memory Write Gate 校验、尚不能注入上下文的记忆提案。"""

    kind: MemoryKind
    content: str
    importance: int
    reason: str
    source_session_id: UUID | None = None
    source_event_id: UUID | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    scope: MemoryScope = MemoryScope.task
    status: MemoryStatus = MemoryStatus.candidate
    subject: str = ""
    predicate: str = "states"
    value: dict[str, object] = field(default_factory=dict)
    confidence: float = 0.5
    authority: MemoryAuthority = MemoryAuthority.agent_inferred
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    ttl_seconds: int | None = None
    provenance: list[str] = field(default_factory=list)
    sensitivity: MemorySensitivity = MemorySensitivity.internal
    project_id: str | None = None
    task_id: UUID | None = None
    user_id: str | None = None
    created_by: str = "memory_extractor"
    verification: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class MemoryWriteDecision:
    """写入门禁的可审计判定。"""

    candidate: MemoryCandidate
    accepted: bool
    target_status: MemoryStatus
    reasons: list[str]
    redactions: int = 0
