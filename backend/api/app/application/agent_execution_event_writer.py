from collections.abc import Mapping
from uuid import UUID

from app.application.agent_execution_types import (
    AgentExecutionContext,
    EventSink,
    MachineSnapshot,
)
from app.application.agent_summary_service import AgentSummaryResult
from app.core.exceptions import AppException, ErrorSource, build_task_error_payload
from app.domain.agent_runtime.entities import AgentPhase, Reflection
from app.domain.sessions.entities import SessionEvent, SessionEventType


async def add_reflected_event(
    sink: EventSink,
    snapshot: MachineSnapshot,
    reflection: Reflection,
) -> SessionEvent:
    state = snapshot.state
    if state.observation is None:
        raise AppException(message="reflecting state has no observation")
    return await sink.add(
        session_id=state.session_id,
        event_type=SessionEventType.step_reflected,
        payload={
            **step_identity(snapshot),
            "attempt": state.attempt,
            "status": state.observation.status.value,
            "action": reflection.action.value,
            "reason": reflection.reason,
        },
    )


async def add_terminal_event(
    sink: EventSink,
    snapshot: MachineSnapshot,
    *,
    event_type: SessionEventType,
    reason: str | None,
) -> SessionEvent:
    state = snapshot.state
    if state.observation is None:
        raise AppException(message="terminal state has no observation")
    return await sink.add(
        session_id=state.session_id,
        event_type=event_type,
        payload={
            **step_identity(snapshot),
            "attempt": state.attempt,
            "title": state.plan.steps[state.step_index].title,
            "summary": state.observation.output,
            "status": state.observation.status.value,
            "reason": reason,
        },
    )


async def add_failure_event(
    sink: EventSink,
    snapshot: MachineSnapshot,
    reason: str,
) -> SessionEvent:
    state = snapshot.state
    step = state.plan.steps[state.step_index]
    payload = build_task_error_payload(
        AppException(message=reason, source=ErrorSource.agent),
        session_id=state.session_id,
        plan_id=plan_id(snapshot.plan),
        step={"id": str(step.id), "title": step.title},
        step_index=state.step_index + 1,
    )
    payload["phase"] = AgentPhase.failed.value
    payload["run_id"] = str(state.run_id)
    payload["plan_revision"] = state.plan_revision
    return await sink.add(
        session_id=state.session_id,
        event_type=SessionEventType.task_error,
        payload=payload,
    )


async def add_done_event(
    sink: EventSink,
    snapshot: MachineSnapshot,
    *,
    result: AgentSummaryResult,
    context: AgentExecutionContext,
) -> SessionEvent:
    return await sink.add(
        session_id=snapshot.state.session_id,
        event_type=SessionEventType.task_done,
        payload={
            "plan_id": plan_id(snapshot.plan),
            "plan_revision": snapshot.state.plan_revision,
            "run_id": str(snapshot.state.run_id),
            "final_answer": result.final_answer,
            "reasoning": result.reasoning,
            "message_id": str(result.message_id),
            "message": "计划步骤已全部执行完成。",
            "memory_ids": [str(item.id) for item in context.memory_context.items],
            "memory_count": len(context.memory_context.items),
        },
    )


async def add_plan_event(
    sink: EventSink,
    *,
    session_id: UUID,
    plan: Mapping[str, object],
) -> SessionEvent:
    return await sink.add(
        session_id=session_id,
        event_type=SessionEventType.plan_created,
        payload=dict(plan),
    )


def step_identity(snapshot: MachineSnapshot) -> dict[str, object]:
    state = snapshot.state
    step = state.plan.steps[state.step_index]
    return {
        "plan_id": plan_id(snapshot.plan),
        "plan_revision": state.plan_revision,
        "run_id": str(state.run_id),
        "step_id": str(step.id),
        "index": state.step_index + 1,
    }


def plan_id(plan: Mapping[str, object]) -> str | None:
    value = plan.get("id") or plan.get("plan_id")
    return str(value) if value is not None else None
