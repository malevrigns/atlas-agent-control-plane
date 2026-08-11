from app.application.agent_runner_service import AgentRunnerStreamItem
from app.domain.agent_core.planner import AgentPlan
from app.domain.files.entities import SessionFile
from app.domain.sessions.entities import Session, SessionEvent, SessionMessage
from app.infrastructure.task_queue import AgentTask
from app.presentation.http.routes.files import to_file_response
from app.schemas.file import SessionFileResponse
from app.schemas.session import (
    AgentTaskResponse,
    ContextBudgetResponse,
    ContextEventSummaryResponse,
    ContextFileReferenceResponse,
    ContextMessageResponse,
    MemoryContextItemResponse,
    MemoryContextResponse,
    MessageResponse,
    PlanResponse,
    PlanStepResponse,
    SessionContextResponse,
    SessionEventResponse,
    SessionResponse,
)


def to_session_response(session: Session) -> SessionResponse:
    return SessionResponse(
        id=session.id,
        title=session.title,
        status=session.status.value,
        unread_count=session.unread_count,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def to_message_response(message: SessionMessage) -> MessageResponse:
    return MessageResponse(
        id=message.id,
        session_id=message.session_id,
        role=message.role.value,
        content=message.content,
        created_at=message.created_at,
    )


def to_event_response(event: SessionEvent) -> SessionEventResponse:
    return SessionEventResponse(
        id=event.id,
        session_id=event.session_id,
        type=event.type.value,
        payload=event.payload,
        created_at=event.created_at,
    )


def to_plan_response(plan: AgentPlan) -> PlanResponse:
    steps = [
        PlanStepResponse(
            id=step.id,
            title=step.title,
            description=step.description,
            expected_output=step.expected_output,
            status=step.status.value,
        )
        for step in plan.steps
    ]
    return PlanResponse(
        id=plan.id,
        title=plan.title,
        goal=plan.goal,
        source=plan.source,
        steps=steps,
    )


def to_session_file_response(session_file: SessionFile) -> SessionFileResponse:
    return SessionFileResponse(
        id=session_file.id,
        session_id=session_file.session_id,
        file=to_file_response(session_file.file),
        created_at=session_file.created_at,
    )


def to_agent_task_response(task: AgentTask) -> AgentTaskResponse:
    return AgentTaskResponse(
        id=task.id,
        session_id=task.session_id,
        type=task.type,
        status=task.status.value,
        error=task.error,
        created_at=task.created_at,
        updated_at=task.updated_at,
        parent_task_id=task.parent_task_id,
        retry_count=task.retry_count,
    )


def to_context_response(snapshot) -> SessionContextResponse:
    return SessionContextResponse(
        session_id=snapshot.session_id,
        summary=snapshot.summary,
        messages=_context_messages(snapshot.messages),
        event_summaries=_context_events(snapshot.event_summaries),
        files=_context_files(snapshot.files),
        memory_context=_memory_context(snapshot.memory_context),
        budget=_context_budget(snapshot.budget),
    )


def _context_messages(messages) -> list[ContextMessageResponse]:
    return [
        ContextMessageResponse(
            role=message.role,
            content=message.content,
            original_chars=message.original_chars,
            truncated=message.truncated,
            created_at=message.created_at,
        )
        for message in messages
    ]


def _context_events(events) -> list[ContextEventSummaryResponse]:
    return [
        ContextEventSummaryResponse(
            type=event.type,
            count=event.count,
            latest_at=event.latest_at,
        )
        for event in events
    ]


def _context_files(files) -> list[ContextFileReferenceResponse]:
    return [
        ContextFileReferenceResponse(
            id=file.id,
            name=file.name,
            content_type=file.content_type,
            size=file.size,
            usage_hint=file.usage_hint,
        )
        for file in files
    ]


def _memory_context(context) -> MemoryContextResponse:
    items = [
        MemoryContextItemResponse(
            id=item.id,
            kind=item.kind.value,
            content=item.content,
            importance=item.importance,
            relevance_score=item.relevance_score,
            matched_terms=item.matched_terms,
            original_chars=item.original_chars,
            truncated=item.truncated,
            source_session_id=item.source_session_id,
            source_event_id=item.source_event_id,
            updated_at=item.updated_at,
            scope=item.scope,
            status=item.status,
            confidence=item.confidence,
            authority=item.authority,
            provenance=list(item.provenance or []),
            reason_retrieved=item.reason_retrieved,
        )
        for item in context.items
    ]
    return MemoryContextResponse(
        query=context.query,
        items=items,
        candidate_count=context.candidate_count,
        omitted_count=context.omitted_count,
        total_chars=context.total_chars,
        max_chars=context.max_chars,
    )


def _context_budget(budget) -> ContextBudgetResponse:
    return ContextBudgetResponse(
        message_limit=budget.message_limit,
        event_limit=budget.event_limit,
        max_message_chars=budget.max_message_chars,
        included_messages=budget.included_messages,
        omitted_messages=budget.omitted_messages,
        included_events=budget.included_events,
        omitted_events=budget.omitted_events,
        total_message_chars=budget.total_message_chars,
        memory_limit=budget.memory_limit,
        max_memory_chars=budget.max_memory_chars,
        included_memories=budget.included_memories,
        omitted_memories=budget.omitted_memories,
        total_memory_chars=budget.total_memory_chars,
    )


def to_runner_stream_payload(item: AgentRunnerStreamItem) -> dict:
    if isinstance(item.payload, Session):
        return to_session_response(item.payload).model_dump(mode="json")
    if isinstance(item.payload, SessionEvent):
        return to_event_response(item.payload).model_dump(mode="json")
    return item.payload
