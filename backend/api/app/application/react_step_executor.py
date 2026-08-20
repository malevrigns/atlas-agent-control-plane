import hashlib
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol
from uuid import UUID

from app.application.agent_loop import StepAgentLoop
from app.application.tool_runtime import ToolExecutionContext
from app.application.unit_of_work import UnitOfWork
from app.domain.agent_core.tools import ToolCallResult, ToolInvocationStatus
from app.domain.agent_runtime.entities import StepObservation
from app.domain.agent_runtime.router import SUCCESS_STATUSES
from app.domain.context_engineering.entities import MemoryContext
from app.domain.sessions.entities import SessionEvent, SessionEventType


ALLOWED_TOOL_PERMISSIONS = {
    "filesystem:read",
    "filesystem:write",
    "browser:read",
    "browser:navigate",
    "browser:control",
    "network:access",
    "agent:delegate",
    "shell:execute",
    "shell:read",
    "integration:mcp",
    "integration:a2a",
}
ToolCaller = Callable[..., Awaitable[Mapping[str, object]]]
OutputSummarizer = Callable[[str, str], str]


class ToolSelector(Protocol):
    async def call_tool_for_step(
        self,
        *,
        plan: dict,
        step: dict,
        index: int,
        agent_context: str,
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolCallResult: ...


class SelectedToolCaller:
    def __init__(self, selector: ToolSelector) -> None:
        self._selector = selector

    async def __call__(
        self,
        *,
        request: "StepExecutionRequest",
        agent_context: str,
        execution_context: ToolExecutionContext,
    ) -> Mapping[str, object]:
        result = await self._selector.call_tool_for_step(
            plan=dict(request.plan),
            step=dict(request.step),
            index=request.step_index + 1,
            agent_context=agent_context,
            execution_context=execution_context,
        )
        return {
            "tool_name": result.tool_name,
            "arguments": result.arguments,
            "output": result.output,
            "invocation_id": result.invocation_id,
            "status": result.status.value,
            "risk_level": result.risk_level.value,
            "artifact_id": result.artifact_id,
            "duration_ms": result.duration_ms,
            "audit": result.audit or {},
        }


@dataclass(frozen=True, slots=True)
class StepExecutionRequest:
    session_id: UUID
    run_id: UUID
    plan_revision: int
    plan: Mapping[str, object]
    step: Mapping[str, object]
    step_index: int
    attempt: int
    memory_context: MemoryContext
    agent_context: str
    step_history: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, UUID):
            raise TypeError("run_id must be a UUID")
        if (
            isinstance(self.plan_revision, bool)
            or not isinstance(self.plan_revision, int)
            or self.plan_revision < 0
        ):
            raise ValueError("plan_revision must be a non-negative integer")
        if self.step_index < 0:
            raise ValueError("step_index must be zero-based and non-negative")
        if self.attempt < 1:
            raise ValueError("attempt must be positive")
        object.__setattr__(self, "plan", MappingProxyType(dict(self.plan)))
        object.__setattr__(self, "step", MappingProxyType(dict(self.step)))
        object.__setattr__(self, "step_history", tuple(self.step_history))


@dataclass(frozen=True, slots=True)
class StepExecutionOutcome:
    events: tuple[SessionEvent, ...]
    observation: StepObservation


class ReActStepExecutor:
    def __init__(
        self,
        *,
        uow: UnitOfWork,
        tool_caller: ToolCaller | None = None,
        step_loop: StepAgentLoop | None = None,
        output_summarizer: OutputSummarizer | None = None,
    ) -> None:
        self._uow = uow
        self._tool_caller = tool_caller
        self._step_loop = step_loop
        self._output_summarizer = output_summarizer or self._default_summary

    async def execute(self, request: StepExecutionRequest) -> StepExecutionOutcome:
        started = await self._add_started_event(request)
        if self._step_loop is not None:
            return await self._execute_with_loop(request, started)
        if self._tool_caller is None:
            raise ValueError("step executor requires tool_caller or step_loop")
        tool_result = await self._tool_caller(
            request=request,
            agent_context=self._render_agent_context(request),
            execution_context=self._tool_execution_context(request),
        )
        tool_called = await self._add_tool_event(request, tool_result)
        observation = StepObservation(
            status=ToolInvocationStatus(str(tool_result["status"])),
            output=str(tool_result["output"]),
        )
        return StepExecutionOutcome(
            events=(started, tool_called),
            observation=observation,
        )

    async def _execute_with_loop(
        self,
        request: StepExecutionRequest,
        started: SessionEvent,
    ) -> StepExecutionOutcome:
        loop_result = await self._step_loop.run_step(
            session_id=request.session_id,
            plan=dict(request.plan),
            step=dict(request.step),
            index=request.step_index + 1,
            context=self._render_agent_context(request),
            execution_context=self._tool_execution_context(request),
        )
        tool_events: list[SessionEvent] = []
        for item in loop_result.tool_calls:
            result = item.result
            tool_events.append(
                await self._add_tool_event(
                    request,
                    {
                        "tool_name": result.tool_name,
                        "arguments": result.arguments,
                        "output": result.output,
                        "invocation_id": result.invocation_id,
                        "status": result.status.value,
                        "risk_level": result.risk_level.value,
                        "artifact_id": result.artifact_id,
                        "duration_ms": result.duration_ms,
                        "audit": result.audit or {},
                        "turn": item.turn,
                    },
                )
            )
        status = (
            loop_result.tool_calls[-1].result.status
            if loop_result.tool_calls
            else ToolInvocationStatus.succeeded
        )
        observation = StepObservation(status=status, output=loop_result.summary)
        return StepExecutionOutcome(
            events=(started, *tool_events),
            observation=observation,
        )

    def format_step_history(
        self,
        *,
        step_index: int,
        step: Mapping[str, object],
        events: tuple[SessionEvent, ...],
    ) -> str:
        tool_events = [
            event for event in events if event.type is SessionEventType.tool_called
        ]
        if not tool_events:
            return f"- 步骤{step_index + 1}《{step.get('title') or ''}》已完成。"
        tool_event = tool_events[-1]
        status = ToolInvocationStatus(str(tool_event.payload["status"]))
        prefix = "已完成" if status in SUCCESS_STATUSES else "⚠️ 失败"
        tool_name = str(tool_event.payload.get("tool_name") or "")
        output = str(tool_event.payload.get("output") or "")
        summary = self._output_summarizer(tool_name, output)
        title = str(step.get("title") or "")
        return (
            f"- 步骤{step_index + 1}《{title}》{prefix}（{tool_name}）："
            f"{self._trim_text(summary, 200)}"
        )

    async def _add_started_event(self, request: StepExecutionRequest) -> SessionEvent:
        return await self._uow.session_events.add(
            session_id=request.session_id,
            event_type=SessionEventType.step_started,
            payload={
                **self._step_identity(request),
                "title": str(request.step.get("title") or ""),
            },
        )

    async def _add_tool_event(
        self,
        request: StepExecutionRequest,
        result: Mapping[str, object],
    ) -> SessionEvent:
        return await self._uow.session_events.add(
            session_id=request.session_id,
            event_type=SessionEventType.tool_called,
            payload={
                **self._step_identity(request),
                **dict(result),
                "memory_ids": [str(item.id) for item in request.memory_context.items],
                "memory_count": len(request.memory_context.items),
            },
        )

    @staticmethod
    def _step_identity(request: StepExecutionRequest) -> dict[str, object]:
        return {
            "plan_id": request.plan.get("id") or request.plan.get("plan_id"),
            "plan_revision": request.plan_revision,
            "run_id": str(request.run_id),
            "step_id": request.step.get("id"),
            "index": request.step_index + 1,
            "attempt": request.attempt,
        }

    @staticmethod
    def _tool_execution_context(request: StepExecutionRequest) -> ToolExecutionContext:
        plan_id = str(request.plan.get("id") or request.plan.get("plan_id") or "plan")
        step_id = str(request.step.get("id") or "step")
        return ToolExecutionContext(
            project_id=str(request.plan.get("project_id") or "default"),
            session_id=request.session_id,
            actor="react_agent",
            allowed_permissions=set(ALLOWED_TOOL_PERMISSIONS),
            idempotency_key=hashlib.sha256(
                (
                    f"{request.session_id}:{request.run_id}:{plan_id}:"
                    f"{request.plan_revision}:{step_id}:{request.attempt}"
                ).encode("utf-8")
            ).hexdigest(),
        )

    def _render_agent_context(self, request: StepExecutionRequest) -> str:
        context = self._merge_memory_context(request)
        if not request.step_history:
            return context
        history = "\n".join(request.step_history)
        heading = "本轮已完成步骤的结果（不要重复做）："
        return f"{context}\n\n{heading}\n{history}" if context else f"{heading}\n{history}"

    @staticmethod
    def _merge_memory_context(request: StepExecutionRequest) -> str:
        memory = "\n".join(
            f"- [{item.kind.value}] {item.content}"
            for item in request.memory_context.items
        )
        if request.agent_context and memory and memory not in request.agent_context:
            return f"{request.agent_context}\n\n长期记忆补充：\n{memory}"
        return request.agent_context or memory

    @staticmethod
    def _require_tool_event(events: tuple[SessionEvent, ...]) -> SessionEvent:
        for event in events:
            if event.type is SessionEventType.tool_called:
                return event
        raise ValueError("step events do not contain tool_called")

    @staticmethod
    def _default_summary(tool_name: str, output: str) -> str:
        del tool_name
        for line in output.splitlines():
            if line.strip():
                return line.strip()
        return "工具已返回结果。"

    @staticmethod
    def _trim_text(value: str, max_length: int) -> str:
        clean_value = " ".join(value.split())
        if len(clean_value) <= max_length:
            return clean_value
        return f"{clean_value[:max_length]}..."
