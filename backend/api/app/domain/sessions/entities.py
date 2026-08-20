from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class SessionStatus(StrEnum):
    idle = "idle"
    running = "running"
    stopped = "stopped"
    failed = "failed"


class MessageRole(StrEnum):
    user = "user"
    assistant = "assistant"
    system = "system"


class SessionEventType(StrEnum):
    message_created = "message_created"
    plan_created = "plan_created"
    step_started = "step_started"
    tool_called = "tool_called"
    step_completed = "step_completed"
    step_reflected = "step_reflected"
    step_failed = "step_failed"
    step_blocked = "step_blocked"
    task_done = "task_done"
    task_error = "task_error"


@dataclass(slots=True)
class Session:
    id: UUID
    title: str
    status: SessionStatus
    unread_count: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    # 本地工作区目录（相对沙箱挂载根）；full_access 为 True 时可访问整个挂载根。
    workspace_dir: str = ""
    full_access: bool = False


@dataclass(slots=True)
class SessionMessage:
    id: UUID
    session_id: UUID
    role: MessageRole
    content: str
    created_at: datetime


@dataclass(slots=True)
class SessionEvent:
    id: UUID
    session_id: UUID
    type: SessionEventType
    payload: dict
    created_at: datetime
