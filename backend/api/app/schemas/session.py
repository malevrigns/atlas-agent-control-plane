from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SessionCreateRequest(BaseModel):
    # 标题允许留空：留空时服务端落「新工作区」，首条消息后由模型自动命名。
    title: str = Field(default="", max_length=200)
    # 本地工作区目录（相对沙箱挂载根）；full_access 为 True 时可访问整个挂载根。
    workspace_dir: str = Field(default="", max_length=512)
    full_access: bool = False


class SessionResponse(BaseModel):
    id: UUID
    title: str
    status: str
    unread_count: int
    created_at: datetime
    updated_at: datetime
    workspace_dir: str
    full_access: bool


class SessionListResponse(BaseModel):
    items: list[SessionResponse]


class MessageCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    # 用户通过输入 / 显式调用的技能 id（published 且启用的技能才会被注入）。
    skill_ids: list[UUID] = Field(default_factory=list, max_length=4)
    # 为 true 时从上次失败处续跑：不重新规划、不重复创建用户消息。
    resume: bool = False


class PlanCreateRequest(BaseModel):
    task: str = Field(min_length=1, max_length=4000)


class MessageResponse(BaseModel):
    id: UUID
    session_id: UUID
    role: str
    content: str
    created_at: datetime


class MessageListResponse(BaseModel):
    items: list[MessageResponse]


class SessionEventResponse(BaseModel):
    id: UUID
    session_id: UUID
    type: str
    payload: dict
    created_at: datetime


class SessionEventListResponse(BaseModel):
    items: list[SessionEventResponse]


class MessageCreateResponse(BaseModel):
    message: MessageResponse
    event: SessionEventResponse


class PlanStepResponse(BaseModel):
    id: UUID
    title: str
    description: str
    expected_output: str
    status: str


class PlanResponse(BaseModel):
    id: UUID
    title: str
    goal: str
    source: str
    steps: list[PlanStepResponse]


class PlanCreateResponse(BaseModel):
    plan: PlanResponse
    event: SessionEventResponse


class PlanExecuteResponse(BaseModel):
    events: list[SessionEventResponse]


class AgentTaskResponse(BaseModel):
    id: str
    session_id: UUID
    type: str
    status: str
    error: str | None
    created_at: str
    updated_at: str
    parent_task_id: str | None = None
    retry_count: int = 0


class ContextMessageResponse(BaseModel):
    role: str
    content: str
    original_chars: int
    truncated: bool
    created_at: datetime


class ContextEventSummaryResponse(BaseModel):
    type: str
    count: int
    latest_at: datetime


class ContextFileReferenceResponse(BaseModel):
    id: UUID
    name: str
    content_type: str
    size: int
    usage_hint: str


class MemoryContextItemResponse(BaseModel):
    id: UUID
    kind: str
    content: str
    importance: int
    relevance_score: float
    matched_terms: list[str]
    original_chars: int
    truncated: bool
    source_session_id: UUID | None
    source_event_id: UUID | None
    updated_at: datetime | None
    scope: str
    status: str
    confidence: float
    authority: str
    provenance: list[str]
    reason_retrieved: str


class MemoryContextResponse(BaseModel):
    query: str
    items: list[MemoryContextItemResponse]
    candidate_count: int
    omitted_count: int
    total_chars: int
    max_chars: int


class ContextBudgetResponse(BaseModel):
    message_limit: int
    event_limit: int
    max_message_chars: int
    included_messages: int
    omitted_messages: int
    included_events: int
    omitted_events: int
    total_message_chars: int
    memory_limit: int
    max_memory_chars: int
    included_memories: int
    omitted_memories: int
    total_memory_chars: int


class SessionContextResponse(BaseModel):
    session_id: UUID
    summary: str
    messages: list[ContextMessageResponse]
    event_summaries: list[ContextEventSummaryResponse]
    files: list[ContextFileReferenceResponse]
    memory_context: MemoryContextResponse
    budget: ContextBudgetResponse
