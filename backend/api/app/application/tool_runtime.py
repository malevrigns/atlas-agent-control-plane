import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.application.tool_runtime_support import (
    InvocationOutcome,
    StoredToolOutput,
    ToolExecutionContext,
    ToolPolicyDecision,
    ToolPolicyEngine,
    invoke_tool,
    store_tool_output,
)
from app.application.unit_of_work import UnitOfWork
from app.core.exceptions import AppException
from app.core.module_policy import module_enabled, module_for_tool
from app.domain.agent_core.tools import (
    ToolCallResult,
    ToolDefinition,
    ToolInvocationStatus,
    ToolRegistry,
    ToolRiskLevel,
)


class ToolRuntime:
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
        call_hash = self._request_hash(tool_name, definition.version, checked_arguments)
        decision = self._policy_decision(tool_name, definition, context)
        cached = await self._cache_hit(tool_name, context, request_hash=call_hash)
        if cached is not None:
            return cached

        invocation_id = uuid4()
        await self._record_start(
            invocation_id=invocation_id, definition=definition, context=context,
            request_hash=call_hash, decision=decision,
            arguments=checked_arguments,
            started_at=datetime.now(UTC),
        )

        if not decision.executable:
            return await self._finish_denied(
                tool_name,
                checked_arguments,
                invocation_id=invocation_id,
                decision=decision,
                definition=definition,
            )

        outcome = await invoke_tool(tool, checked_arguments)
        stored = await store_tool_output(
            self.uow,
            outcome.output,
            context,
            tool_name=tool_name,
            request_hash=call_hash,
        )
        result = self._build_result(
            tool_name,
            checked_arguments,
            invocation_id=invocation_id,
            decision=decision,
            definition=definition,
            outcome=outcome,
            stored=stored,
            request_hash=call_hash,
        )
        await self._record_finish(result, error=outcome.error)
        self._remember_success(tool_name, context.idempotency_key, result)
        return result

    def _policy_decision(
        self,
        tool_name: str,
        definition: ToolDefinition,
        context: ToolExecutionContext,
    ) -> ToolPolicyDecision:
        module_key = module_for_tool(tool_name)
        if not module_key or module_enabled(module_key):
            return self.policy.evaluate(definition, context)
        return ToolPolicyDecision(
            decision="deny",
            reason=f"module is disabled: {module_key}",
            executable=False,
            status=ToolInvocationStatus.denied,
        )

    async def _cache_hit(
        self,
        tool_name: str,
        context: ToolExecutionContext,
        *,
        request_hash: str,
    ) -> ToolCallResult | None:
        cached = await self._find_idempotent(
            tool_name,
            context.idempotency_key,
            request_hash=request_hash,
        )
        if cached is None:
            return None
        if cached.status is ToolInvocationStatus.succeeded:
            cached.status = ToolInvocationStatus.deduplicated
        cached.audit = {**(cached.audit or {}), "idempotency": "cache_hit"}
        return cached

    async def _finish_denied(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        invocation_id: UUID,
        decision: ToolPolicyDecision,
        definition: ToolDefinition,
    ) -> ToolCallResult:
        result = ToolCallResult(
            tool_name=tool_name,
            arguments=arguments,
            output=decision.reason,
            invocation_id=str(invocation_id),
            status=decision.status,
            risk_level=definition.risk_level,
            audit={"decision": decision.decision, "reason": decision.reason},
        )
        await self._record_finish(result, error=None)
        return result

    @staticmethod
    def _build_result(
        tool_name: str,
        arguments: dict[str, Any],
        *,
        invocation_id: UUID,
        decision: ToolPolicyDecision,
        definition: ToolDefinition,
        outcome: InvocationOutcome,
        stored: StoredToolOutput,
        request_hash: str,
    ) -> ToolCallResult:
        return ToolCallResult(
            tool_name=tool_name,
            arguments=arguments,
            output=stored.preview,
            invocation_id=str(invocation_id),
            status=outcome.status,
            risk_level=definition.risk_level,
            duration_ms=outcome.duration_ms,
            artifact_id=stored.artifact_id,
            output_truncated=stored.truncated,
            audit={
                "decision": decision.decision,
                "reason": decision.reason,
                "request_hash": request_hash,
                "redactions": stored.redactions,
                "timeout_seconds": outcome.timeout_seconds,
            },
        )

    def _remember_success(
        self,
        tool_name: str,
        idempotency_key: str | None,
        result: ToolCallResult,
    ) -> None:
        if idempotency_key and result.status is ToolInvocationStatus.succeeded:
            self._memory_idempotency[(tool_name, idempotency_key)] = result

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
            status=ToolInvocationStatus(original_status),
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
