from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.domain.memories.entities import MemoryKind
from app.domain.skills.entities import SkillContext


@dataclass(slots=True)
class ContextMessage:
    role: str
    content: str
    original_chars: int  # 保留原始长度，方便判断内容被裁剪了多少。
    truncated: bool  # 标记 content 是否已经按上下文预算裁剪。
    created_at: datetime


@dataclass(slots=True)
class ContextEventSummary:
    type: str
    count: int  # 同类型事件在最近事件窗口里出现了多少次。
    latest_at: datetime  # 这个事件类型最近一次出现的时间。


@dataclass(slots=True)
class ContextFileReference:
    id: UUID
    name: str
    content_type: str
    size: int
    usage_hint: str  # 提醒 Agent 后续应该如何使用这个文件。


@dataclass(slots=True)
class MemoryContextItem:
    """经过检索和压缩、准备注入 Agent 上下文的一条长期记忆。"""

    id: UUID
    kind: MemoryKind
    content: str
    importance: int
    relevance_score: float  # 综合相关度、重要度和新鲜度后的最终分数。
    matched_terms: list[str]  # 与当前任务匹配的关键词，便于解释检索结果。
    original_chars: int  # 裁剪前字符数。
    truncated: bool  # 是否按单条记忆预算裁剪。
    source_session_id: UUID | None
    source_event_id: UUID | None
    updated_at: datetime | None
    scope: str = "project"
    status: str = "verified"
    confidence: float = 1.0
    authority: str = "explicit_user"
    provenance: list[str] | None = None
    reason_retrieved: str = ""


@dataclass(slots=True)
class MemoryContext:
    """本次任务最终选中的长期记忆上下文。"""

    query: str
    items: list[MemoryContextItem]
    candidate_count: int
    omitted_count: int
    total_chars: int
    max_chars: int


@dataclass(slots=True)
class ContextBudget:
    message_limit: int  # 配置允许纳入的最大消息条数。
    event_limit: int  # 配置允许参考的最大事件条数。
    max_message_chars: int  # 单条消息允许保留的最大字符数。
    included_messages: int  # 本次快照实际纳入的消息条数。
    omitted_messages: int  # 因预算限制被省略的历史消息条数。
    included_events: int  # 本次快照参考的最近事件数量。
    omitted_events: int  # 因预算限制被省略的历史事件数量。
    total_message_chars: int  # 裁剪后消息内容的总字符数。
    memory_limit: int  # 本次最多注入多少条长期记忆。
    max_memory_chars: int  # 长期记忆区域允许使用的总字符数。
    included_memories: int  # 本次实际注入的长期记忆数量。
    omitted_memories: int  # 因相关度或预算限制未注入的候选数量。
    total_memory_chars: int  # 本次注入的长期记忆总字符数。


@dataclass(slots=True)
class SessionContextSnapshot:
    session_id: UUID
    summary: str
    messages: list[ContextMessage]
    event_summaries: list[ContextEventSummary]
    files: list[ContextFileReference]
    memory_context: MemoryContext
    budget: ContextBudget
    # 命中的技能注册中心条目（published + enabled），
    # 渲染成 Agent 提示词时会作为独立段落注入。
    skill_context: SkillContext | None = None
