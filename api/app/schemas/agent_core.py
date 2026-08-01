from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# ===================== 第1步：定义工具 schema 响应 =====================
class ToolParameterResponse(BaseModel):
    name: str
    type: str
    description: str
    required: bool


class ToolDefinitionResponse(BaseModel):
    name: str
    description: str
    parameters: list[ToolParameterResponse]
    version: str
    risk_level: str
    required_permissions: list[str]
    idempotent: bool
    timeout_seconds: float
    output_mode: str


class ToolListResponse(BaseModel):
    items: list[ToolDefinitionResponse]


# ===================== 第2步：定义 Memory 消息响应 =====================
class MemoryMessageResponse(BaseModel):
    id: UUID
    role: str
    content: str
    created_at: datetime
    name: str | None = None


# ===================== 第3步：定义工具调用结果响应 =====================
class ToolCallResultResponse(BaseModel):
    tool_name: str
    arguments: dict
    output: str
    invocation_id: str | None = None
    status: str = "succeeded"
    risk_level: str = "low"
    duration_ms: int | None = None
    artifact_id: str | None = None
    output_truncated: bool = False
    audit: dict | None = None


class ToolInvokeRequest(BaseModel):
    arguments: dict = Field(default_factory=dict)
    project_id: str = "default"
    task_id: UUID | None = None
    session_id: UUID | None = None
    actor: str = "user"
    allowed_permissions: list[str] = Field(default_factory=list)
    approved: bool = False
    approval_reason: str = ""
    idempotency_key: str | None = Field(default=None, max_length=160)


# ===================== 第4步：定义最小 Agent 演示请求和响应 =====================
class AgentCoreDemoRequest(BaseModel):
    task: str = Field(min_length=1, max_length=1000)
    tool_name: str | None = None


class AgentCoreDemoResponse(BaseModel):
    messages: list[MemoryMessageResponse]
    selected_tool: ToolDefinitionResponse
    tool_result: ToolCallResultResponse
    next_step: str
