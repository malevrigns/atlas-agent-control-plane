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
    # 范围审计（summarize 前）完成事件：记录规则层/LLM 复核结论与违规文件。
    scope_audit_finished = "scope_audit_finished"
    # 验收门禁：任务完成（summarize）前的客观验证
    acceptance_gate_started = "acceptance_gate_started"
    acceptance_gate_finished = "acceptance_gate_finished"
    # Todo 清单状态变更（T6）：payload 记 todo_id / status / progress 快照。
    todo_updated = "todo_updated"
    # 覆盖度评审：任务进入 summarize 前的 LLM 测试覆盖评审结论（建议性，失败开放）。
    coverage_review_finished = "coverage_review_finished"
    # 验收链汇总：summarize 前链（验收门禁/范围审计/覆盖度评审）全部跑完后，
    # 一条事件汇总各 stage 结论（passed/skipped + detail）。
    acceptance_chain_finished = "acceptance_chain_finished"


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
