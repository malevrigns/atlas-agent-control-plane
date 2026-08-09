import asyncio
import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from time import perf_counter
from collections.abc import Awaitable, Callable
from typing import Any, cast
from uuid import UUID, uuid4

from app.application.control_plane_service import ControlPlaneService
from app.application.unit_of_work import UnitOfWork
from app.core.config import settings
from app.core.exceptions import AppException
from app.core.module_policy import module_enabled, module_for_tool
from app.domain.agent_core.tools import (
    ToolCallResult,
    ToolInvocationStatus,
    ToolRegistry,
    ToolRiskLevel,
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

    def evaluate(self, definition, context: ToolExecutionContext) -> ToolPolicyDecision:
        missing_permissions = sorted(
            set(definition.required_permissions) - context.allowed_permissions
        )
        if missing_permissions:
            return ToolPolicyDecision(
                decision="deny",
                reason="missing permissions: " + ", ".join(missing_permissions),
                executable=False,
                status=ToolInvocationStatus.denied,
            )
        auto_approve = ToolRiskLevel(settings.tool_auto_approve_risk)
        needs_approval = self._ORDER[definition.risk_level] > self._ORDER[auto_approve]
        if needs_approval and not context.approved:
            return ToolPolicyDecision(
                decision="require_approval",
                reason=f"{definition.risk_level.value} risk tool requires explicit approval",
                executable=False,
                status=ToolInvocationStatus.approval_required,
            )
        return ToolPolicyDecision(
            decision="allow",
            reason=context.approval_reason or "policy and permission checks passed",
            executable=True,
            status=ToolInvocationStatus.running,
        )


class ToolRuntime:
    _SECRET_PATTERNS = (
        re.compile(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*[^\s,;]+"),
        re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    )

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        uow: UnitOfWork | None = None,
        policy: ToolPolicyEngine | None = None,
    ) -> None:
        self.registry = registry
        self.uow = uow
        self.policy = policy or ToolPolicyEngine()
        self._memory_idempotency: dict[tuple[str, str], ToolCallResult] = {}

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: ToolExecutionContext,
    ) -> ToolCallResult:
        tool = self.registry.get(tool_name)
        definition = tool.definition
        checked_arguments = tool._validate_arguments(arguments)
        request_hash = self._request_hash(tool_name, definition.version, checked_arguments)
        module_key = module_for_tool(tool_name)
        if module_key and not module_enabled(module_key):
            decision = ToolPolicyDecision(
                decision="deny",
                reason=f"module is disabled: {module_key}",
                executable=False,
                status=ToolInvocationStatus.denied,
            )
        else:
            decision = self.policy.evaluate(definition, context)

        cached = await self._find_idempotent(
            tool_name,
            context.idempotency_key,
            request_hash=request_hash,
        )
        if cached is not None:
            cached.status = ToolInvocationStatus.deduplicated
            cached.audit = {**(cached.audit or {}), "idempotency": "cache_hit"}
            return cached

        invocation_id = uuid4()
        started_at = datetime.now(UTC)
        await self._record_start(
            invocation_id=invocation_id,
            definition=definition,
            context=context,
            request_hash=request_hash,
            decision=decision,
            arguments=checked_arguments,
            started_at=started_at,
        )

        if not decision.executable:
            result = ToolCallResult(
                tool_name=tool_name,
                arguments=checked_arguments,
                output=decision.reason,
                invocation_id=str(invocation_id),
                status=decision.status,
                risk_level=definition.risk_level,
                audit={"decision": decision.decision, "reason": decision.reason},
            )
            await self._record_finish(result, error=None)
            return result

        started_clock = perf_counter()
        timeout_seconds = max(0.1, definition.timeout_seconds or settings.tool_default_timeout_seconds)
        try:
            # 同步 handler 走线程池；异步 handler（如 RAG 检索）直接 await，
            # 避免在工作线程里再开事件循环。
            if tool.is_async:
                async_handler = cast(Callable[..., Awaitable[str]], tool.handler)
                raw = await asyncio.wait_for(
                    async_handler(**checked_arguments),
                    timeout=timeout_seconds,
                )
            else:
                sync_handler = cast(Callable[..., str], tool.handler)
                raw = await asyncio.wait_for(
                    asyncio.to_thread(sync_handler, **checked_arguments),
                    timeout=timeout_seconds,
                )
            raw_output = str(raw)
            status = ToolInvocationStatus.succeeded
            error = None
        except TimeoutError:
            raw_output = f"tool timed out after {timeout_seconds:g}s"
            status = ToolInvocationStatus.timed_out
            error = raw_output
        except Exception as exc:  # observable tool failure; caller receives a safe result
            raw_output = f"tool failed: {type(exc).__name__}: {exc}"
            status = ToolInvocationStatus.failed
            error = raw_output

        duration_ms = round((perf_counter() - started_clock) * 1000)
        safe_output, redactions = self._redact(raw_output)
        artifact_id = None
        output_truncated = False
        encoded = raw_output.encode("utf-8", errors="replace")
        if len(encoded) > settings.tool_output_inline_limit and self.uow is not None:
            artifact = await ControlPlaneService(self.uow).persist_artifact(
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
            safe_output = safe_output[: settings.tool_output_inline_limit]
            safe_output += f"\n\n[完整输出已保存为 Artifact {artifact_id}]"
            output_truncated = True

        result = ToolCallResult(
            tool_name=tool_name,
            arguments=checked_arguments,
            output=safe_output,
            invocation_id=str(invocation_id),
            status=status,
            risk_level=definition.risk_level,
            duration_ms=duration_ms,
            artifact_id=artifact_id,
            output_truncated=output_truncated,
            audit={
                "decision": decision.decision,
                "reason": decision.reason,
                "request_hash": request_hash,
                "redactions": redactions,
                "timeout_seconds": timeout_seconds,
            },
        )
        await self._record_finish(result, error=error)
        if context.idempotency_key and status is ToolInvocationStatus.succeeded:
            self._memory_idempotency[(tool_name, context.idempotency_key)] = result
        return result

    async def _find_idempotent(
        self,
        tool_name: str,
        idempotency_key: str | None,
        *,
        request_hash: str,
    ) -> ToolCallResult | None:
        if not idempotency_key:
            return None
        memory_result = self._memory_idempotency.get((tool_name, idempotency_key))
        if memory_result:
            cached_hash = str((memory_result.audit or {}).get("request_hash") or "")
            self._assert_idempotency_matches(cached_hash, request_hash)
            return replace(memory_result, audit=dict(memory_result.audit or {}))
        if self.uow is None:
            return None
        existing = await self.uow.control_plane.get_tool_invocation_by_idempotency(
            tool_name, idempotency_key
        )
        if not existing:
            return None
        self._assert_idempotency_matches(str(existing["request_hash"]), request_hash)
        original_status = str(existing["status"])
        return ToolCallResult(
            tool_name=tool_name,
            arguments=dict(existing["arguments"]),
            output=str(existing["output_preview"]),
            invocation_id=str(existing["id"]),
            status=ToolInvocationStatus.deduplicated,
            risk_level=ToolRiskLevel(existing["risk_level"]),
            duration_ms=existing["duration_ms"],
            artifact_id=str(existing["artifact_id"]) if existing["artifact_id"] else None,
            output_truncated=existing["artifact_id"] is not None,
            audit={
                "idempotency": "persistent_cache_hit",
                "original_status": original_status,
                "request_hash": request_hash,
            },
        )

    @staticmethod
    def _assert_idempotency_matches(cached_hash: str, request_hash: str) -> None:
        if cached_hash and cached_hash != request_hash:
            raise AppException(
                message="idempotency key was already used with different arguments",
                code=409,
                status_code=409,
                details={"cached_request_hash": cached_hash, "request_hash": request_hash},
            )

    async def _record_start(self, **payload: Any) -> None:
        if self.uow is None:
            return
        definition = payload["definition"]
        context = payload["context"]
        decision = payload["decision"]
        await self.uow.control_plane.create_tool_invocation({
            "id": payload["invocation_id"],
            "tool_name": definition.name,
            "tool_version": definition.version,
            "task_id": context.task_id,
            "session_id": context.session_id,
            "project_id": context.project_id,
            "idempotency_key": context.idempotency_key,
            "request_hash": payload["request_hash"],
            "risk_level": definition.risk_level.value,
            "permissions": list(definition.required_permissions),
            "decision": decision.decision,
            "decision_reason": decision.reason,
            "status": decision.status.value,
            "arguments": payload["arguments"],
            "output_preview": "",
            "started_at": payload["started_at"],
        })
        await self.uow.commit()

    async def _record_finish(self, result: ToolCallResult, error: str | None) -> None:
        if self.uow is None or not result.invocation_id:
            return
        await self.uow.control_plane.finish_tool_invocation(
            UUID(result.invocation_id),
            {
                "status": result.status.value,
                "output_preview": result.output,
                "artifact_id": UUID(result.artifact_id) if result.artifact_id else None,
                "error": error,
                "duration_ms": result.duration_ms,
                "finished_at": datetime.now(UTC),
            },
        )
        await self.uow.commit()

    @staticmethod
    def _request_hash(tool_name: str, version: str, arguments: dict[str, Any]) -> str:
        body = json.dumps(
            {"tool": tool_name, "version": version, "arguments": arguments},
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return f"sha256:{hashlib.sha256(body).hexdigest()}"

    @classmethod
    def _redact(cls, value: str) -> tuple[str, int]:
        output = value
        count = 0
        for pattern in cls._SECRET_PATTERNS:
            output, replacements = pattern.subn("[REDACTED]", output)
            count += replacements
        return output, count
