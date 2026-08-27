import asyncio
import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from logging import getLogger
from typing import Any
from uuid import UUID, uuid4

from app.application.tool_runtime_support import (
    InvocationOutcome,
    StoredToolOutput,
    ToolExecutionContext,
    ToolPolicyDecision,
    ToolPolicyEngine,
    invoke_tool,
    reset_current_context,
    set_current_context,
    store_tool_output,
)
from app.application.unit_of_work import UnitOfWork
from app.core.config import settings
from app.core.exceptions import AppException
from app.core.module_policy import module_enabled, module_for_tool
from app.domain.agent_core.tool_cache import ToolResultCache
from app.domain.agent_core.tool_resilience import (
    RetryPolicy,
    is_retryable_error_text,
    retry_delay,
)
from app.domain.agent_core.tools import (
    AgentTool,
    ToolCallResult,
    ToolDefinition,
    ToolInvocationStatus,
    ToolRegistry,
    ToolRiskLevel,
)

logger = getLogger(__name__)


# 哨兵值：用于区分 ToolRuntime 构造时「未传 result_cache」（按配置决定）
# 与「显式传 None 禁用缓存」两种情况。
_RESULT_CACHE_UNSET = object()


class ToolRuntime:
    def __init__(
        self,
        registry: ToolRegistry,
        *,
        uow: UnitOfWork | None = None,
        policy: ToolPolicyEngine | None = None,
        result_cache: Any = _RESULT_CACHE_UNSET,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self.registry = registry
        self.uow = uow
        self.policy = policy or ToolPolicyEngine()
        # 结果缓存：未显式传入时按 tool_cache_* 配置决定是否启用；
        # 显式传 None 表示禁用缓存（区别于缺省）。
        if result_cache is _RESULT_CACHE_UNSET:
            if settings.tool_cache_enabled:
                self.result_cache = ToolResultCache(
                    max_entries=settings.tool_cache_max_entries,
                    default_ttl_seconds=settings.tool_cache_ttl_seconds,
                )
            else:
                self.result_cache = None
        else:
            self.result_cache = result_cache
        # 重试策略：显式传入优先（测试可用零延迟策略），否则读 tool_retry_* 配置。
        self.retry_policy = retry_policy or RetryPolicy(
            enabled=settings.tool_retry_enabled,
            max_retries=settings.tool_retry_max_retries,
            base_backoff_seconds=settings.tool_retry_base_backoff_seconds,
            backoff_factor=settings.tool_retry_backoff_factor,
        )
        self._memory_idempotency: dict[tuple[str, str], ToolCallResult] = {}

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: ToolExecutionContext,
    ) -> ToolCallResult:
        """统一执行入口：权限、风险、幂等、超时、重试、降级、结果缓存与审计。"""
        return await self._execute_one(tool_name, arguments, context, allow_fallback=True)

    async def _execute_one(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: ToolExecutionContext,
        *,
        allow_fallback: bool,
    ) -> ToolCallResult:
        """单次工具执行管线；allow_fallback 用于防止降级链递归。"""
        tool = self.registry.get(tool_name)
        definition = tool.definition
        checked_arguments = tool._validate_arguments(arguments)
        call_hash = self._request_hash(tool_name, definition.version, checked_arguments)
        decision = self._policy_decision(tool_name, definition, context)
        cached = await self._cache_hit(tool_name, context, request_hash=call_hash)
        if cached is not None:
            return cached

        # 结果缓存：只对低风险 + 幂等且声明 cacheable 的工具生效。
        # 命中时不产生新的 invocation 记录，cache_hit 标记随 tool_called 事件落审计。
        cache_key: str | None = None
        if decision.executable and self.result_cache is not None and tool.is_cache_eligible:
            cache_key = ToolResultCache.build_key(
                tool_name, checked_arguments, version=definition.version
            )
            cached_result = self.result_cache.get(cache_key)
            if cached_result is not None:
                return self._mark_result_cache_hit(checked_arguments, cached_result)

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
        token = set_current_context(context)
        try:
            outcome, retry_events = await self._invoke_with_resilience(tool, checked_arguments)
        finally:
            reset_current_context(token)
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
        if retry_events:
            # 每次重试写审计：重试事件随结果 audit 进入 tool_called 事件。
            result.audit = {**(result.audit or {}), "retries": retry_events}
        await self._record_finish(result, error=outcome.error)

        # 成功结果写入结果缓存（仅限可缓存工具），失败结果不缓存。
        if cache_key is not None and result.status is ToolInvocationStatus.succeeded:
            self.result_cache.put(cache_key, result, ttl_seconds=tool.cache_ttl_seconds)
        self._remember_success(tool_name, context.idempotency_key, result)

        # 降级：主工具失败/超时且声明了 fallback_tool 时自动切换。
        if (
            allow_fallback
            and result.status
            in (ToolInvocationStatus.failed, ToolInvocationStatus.timed_out)
            and tool.fallback_tool
            and tool.fallback_tool != tool_name
        ):
            fallback_result = await self._try_fallback(
                fallback_name=tool.fallback_tool,
                arguments=arguments,
                context=context,
            )
            if fallback_result is not None:
                result = self._mark_fallback(
                    tool.definition.name, outcome.error, fallback_result
                )
        return result

    async def _try_fallback(
        self,
        *,
        fallback_name: str,
        arguments: dict[str, Any],
        context: ToolExecutionContext,
    ) -> ToolCallResult | None:
        """执行降级工具；降级工具不存在或参数不兼容时返回 None（保留主工具结果）。"""
        try:
            return await self._execute_one(
                fallback_name, arguments, context, allow_fallback=False
            )
        except AppException as error:
            logger.info(
                "fallback tool %s unavailable: %s", fallback_name, error.message
            )
            return None

    async def _invoke_with_resilience(
        self,
        tool: AgentTool,
        arguments: dict[str, Any],
    ) -> tuple[InvocationOutcome, list[dict[str, Any]]]:
        """带重试语义地执行工具。

        - 只有幂等工具参与重试，避免非幂等工具被重复执行产生副作用；
        - 只对超时/网络类错误重试（参数类错误重试无意义）；
        - 每次重试产生一条审计事件（attempt / delay_seconds / error）。
        """
        policy = self.retry_policy
        outcome = await invoke_tool(tool, arguments)
        if not policy.enabled or not tool.definition.idempotent:
            return outcome, []
        retry_events: list[dict[str, Any]] = []
        attempt = 0
        while (
            outcome.status
            in (ToolInvocationStatus.failed, ToolInvocationStatus.timed_out)
            and attempt < policy.max_retries
            and is_retryable_error_text(outcome.error)
        ):
            attempt += 1
            delay = retry_delay(
                attempt,
                base_backoff=policy.base_backoff_seconds,
                factor=policy.backoff_factor,
            )
            retry_events.append(
                {
                    "attempt": attempt,
                    "delay_seconds": delay,
                    "error": outcome.error,
                }
            )
            logger.info(
                "tool %s retrying (attempt=%d, delay=%.2fs): %s",
                tool.definition.name, attempt, delay, outcome.error,
            )
            await asyncio.sleep(delay)
            outcome = await invoke_tool(tool, arguments)
        return outcome, retry_events

    @staticmethod
    def _mark_result_cache_hit(
        arguments: dict[str, Any],
        cached: ToolCallResult,
    ) -> ToolCallResult:
        """结果缓存命中：返回带 cache_hit 标记的新结果，不改缓存对象本身。"""
        return replace(
            cached,
            arguments=dict(arguments),
            audit={**(cached.audit or {}), "cache_hit": True},
            cache_hit=True,
        )

    @staticmethod
    def _mark_fallback(
        primary_name: str,
        primary_error: str | None,
        fallback_result: ToolCallResult,
    ) -> ToolCallResult:
        """在降级结果上注明主工具失败信息与所用降级工具。"""
        audit = {
            **(fallback_result.audit or {}),
            "fallback": {
                "from": primary_name,
                "to": fallback_result.tool_name,
                "primary_error": primary_error,
            },
        }
        if fallback_result.status is ToolInvocationStatus.succeeded:
            note = f"[降级提示：主工具 {primary_name} 失败，已自动切换降级工具 {fallback_result.tool_name}]"
        else:
            note = f"[降级提示：主工具 {primary_name} 与降级工具 {fallback_result.tool_name} 均失败]"
        return replace(
            fallback_result,
            output=f"{note}\n{fallback_result.output}",
            audit=audit,
        )

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
