import asyncio
import re
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, cast
from uuid import UUID

from app.application.control_plane_service import ControlPlaneService
from app.application.unit_of_work import UnitOfWork
from app.core.config import settings
from app.domain.agent_core.tools import (
    AgentTool,
    ToolDefinition,
    ToolInvocationStatus,
    ToolRiskLevel,
)


SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}"),
)


@dataclass(slots=True)
class ToolExecutionContext:
    project_id: str = "default"
    task_id: UUID | None = None
    session_id: UUID | None = None
    actor: str = "agent"
    allowed_permissions: set[str] = field(default_factory=set)
    approved: bool = False
    approval_reason: str = ""
    idempotency_key: str | None = None
    # 本地工作区：文件/Shell 工具据此限域；full_access 放行整个挂载根。
    workspace_dir: str = ""
    full_access: bool = False


# 当前工具执行的上下文：工具 handler 通过它拿到工作区限域。
_current_context: ContextVar[ToolExecutionContext | None] = ContextVar(
    "atlas_tool_context", default=None
)


def current_workspace() -> tuple[str, bool]:
    """返回当前工具执行的 (workspace_dir, full_access)。"""
    ctx = _current_context.get()
    if ctx is None:
        return "", False
    return ctx.workspace_dir, ctx.full_access


def set_current_context(context: ToolExecutionContext):
    """设置当前工具执行上下文，返回 reset token。"""
    return _current_context.set(context)


def reset_current_context(token) -> None:
    _current_context.reset(token)


@dataclass(slots=True)
class ToolPolicyDecision:
    decision: str
    reason: str
    executable: bool
    status: ToolInvocationStatus


class ToolPolicyEngine:
    _ORDER = {
        ToolRiskLevel.low: 0,
        ToolRiskLevel.medium: 1,
        ToolRiskLevel.high: 2,
        ToolRiskLevel.critical: 3,
    }

    def evaluate(
        self,
        definition: ToolDefinition,
        context: ToolExecutionContext,
    ) -> ToolPolicyDecision:
        missing = sorted(set(definition.required_permissions) - context.allowed_permissions)
        if missing:
            return ToolPolicyDecision(
                "deny",
                "missing permissions: " + ", ".join(missing),
                False,
                ToolInvocationStatus.denied,
            )
        auto_approve = ToolRiskLevel(settings.tool_auto_approve_risk)
        needs_approval = self._ORDER[definition.risk_level] > self._ORDER[auto_approve]
        if needs_approval and not context.approved:
            return ToolPolicyDecision(
                "require_approval",
                f"{definition.risk_level.value} risk tool requires explicit approval",
                False,
                ToolInvocationStatus.approval_required,
            )
        return ToolPolicyDecision(
            "allow",
            context.approval_reason or "policy and permission checks passed",
            True,
            ToolInvocationStatus.running,
        )


@dataclass(frozen=True, slots=True)
class InvocationOutcome:
    output: str
    status: ToolInvocationStatus
    error: str | None
    duration_ms: int
    timeout_seconds: float


@dataclass(frozen=True, slots=True)
class StoredToolOutput:
    preview: str
    redactions: int
    artifact_id: str | None
    truncated: bool


async def invoke_tool(
    tool: AgentTool,
    arguments: dict[str, Any],
) -> InvocationOutcome:
    timeout = max(0.1, tool.definition.timeout_seconds or settings.tool_default_timeout_seconds)
    started = perf_counter()
    try:
        raw = await _invoke_handler(tool, arguments, timeout)
        output = str(raw)
        status = ToolInvocationStatus.succeeded
        error = None
    except TimeoutError:
        output = f"tool timed out after {timeout:g}s"
        status = ToolInvocationStatus.timed_out
        error = output
    except Exception as exc:
        output = f"tool failed: {type(exc).__name__}: {exc}"
        status = ToolInvocationStatus.failed
        error = output
    return InvocationOutcome(
        output,
        status,
        error,
        round((perf_counter() - started) * 1000),
        timeout,
    )


async def store_tool_output(
    uow: UnitOfWork | None,
    raw_output: str,
    context: ToolExecutionContext,
    *,
    tool_name: str,
    request_hash: str,
) -> StoredToolOutput:
    preview, redactions = redact(raw_output)
    encoded = raw_output.encode("utf-8", errors="replace")
    if len(encoded) <= settings.tool_output_inline_limit or uow is None:
        return StoredToolOutput(preview, redactions, None, False)
    artifact = await ControlPlaneService(uow).persist_artifact(
        encoded,
        kind="tool_output",
        media_type="text/plain; charset=utf-8",
        project_id=context.project_id,
        task_id=context.task_id,
        metadata={
            "tool_name": tool_name,
            "request_hash": request_hash,
            "redactions_in_preview": redactions,
        },
        sensitivity="confidential" if redactions else "internal",
    )
    artifact_id = str(artifact["id"])
    preview = preview[: settings.tool_output_inline_limit]
    preview += f"\n\n[完整输出已保存为 Artifact {artifact_id}]"
    return StoredToolOutput(preview, redactions, artifact_id, True)


async def _invoke_handler(
    tool: AgentTool,
    arguments: dict[str, Any],
    timeout: float,
) -> str:
    if tool.is_async:
        handler = cast(Callable[..., Awaitable[str]], tool.handler)
        return await asyncio.wait_for(handler(**arguments), timeout=timeout)
    handler = cast(Callable[..., str], tool.handler)
    return await asyncio.wait_for(
        asyncio.to_thread(handler, **arguments),
        timeout=timeout,
    )


def redact(value: str) -> tuple[str, int]:
    output = value
    count = 0
    for pattern in SECRET_PATTERNS:
        output, replacements = pattern.subn("[REDACTED]", output)
        count += replacements
    return output, count
