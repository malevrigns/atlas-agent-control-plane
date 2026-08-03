from uuid import UUID

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.agent_runner_service import AgentRunnerService, AgentRunnerStreamItem
from app.application.context_engineering_service import ContextEngineeringService
from app.application.file_service import FileService
from app.application.llm_service import LLMService
from app.application.planner_service import PlannerService
from app.application.session_service import SessionService
from app.application.unit_of_work import UnitOfWork
from app.core.exceptions import AppException
from app.domain.agent_core.planner import AgentPlan
from app.domain.files.entities import SessionFile
from app.domain.sessions.entities import Session, SessionEvent, SessionMessage
from app.infrastructure.database.session import get_db_session
from app.infrastructure.task_queue import AgentTask, RedisAgentTaskQueue
from app.presentation.http.routes.files import to_file_response
from app.presentation.http.sse import encode_sse
from app.schemas.common import ApiResponse
from app.schemas.file import SessionFileListResponse, SessionFileResponse
from app.schemas.session import (
    AgentTaskResponse,
    ContextBudgetResponse,
    ContextEventSummaryResponse,
    ContextFileReferenceResponse,
    ContextMessageResponse,
    MemoryContextItemResponse,
    MemoryContextResponse,
    MessageCreateRequest,
    MessageCreateResponse,
    MessageListResponse,
    MessageResponse,
    PlanCreateRequest,
    PlanCreateResponse,
    PlanExecuteResponse,
    PlanResponse,
    PlanStepResponse,
    SessionCreateRequest,
    SessionContextResponse,
    SessionEventListResponse,
    SessionEventResponse,
    SessionListResponse,
    SessionResponse,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


def build_session_service(
    db_session: AsyncSession = Depends(get_db_session),
) -> SessionService:
    return SessionService(UnitOfWork(db_session))


def build_file_service(
    db_session: AsyncSession = Depends(get_db_session),
) -> FileService:
    return FileService(UnitOfWork(db_session))


def build_context_engineering_service(
    db_session: AsyncSession = Depends(get_db_session),
) -> ContextEngineeringService:
    return ContextEngineeringService(UnitOfWork(db_session))


def build_planner_service(
    db_session: AsyncSession = Depends(get_db_session),
) -> PlannerService:
    return PlannerService(UnitOfWork(db_session), LLMService())


def build_agent_runner_service(
    db_session: AsyncSession = Depends(get_db_session),
) -> AgentRunnerService:
    uow = UnitOfWork(db_session)
    return AgentRunnerService.from_uow(
        uow,
        planner_service=PlannerService(uow, LLMService()),
    )


def get_task_queue(request: Request) -> RedisAgentTaskQueue:
    return request.app.state.task_queue


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
    return PlanResponse(
        id=plan.id,
        title=plan.title,
        goal=plan.goal,
        source=plan.source,
        steps=[
            PlanStepResponse(
                id=step.id,
                title=step.title,
                description=step.description,
                expected_output=step.expected_output,
                status=step.status.value,
            )
            for step in plan.steps
        ],
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
        messages=[
            ContextMessageResponse(
                role=message.role,
                content=message.content,
                original_chars=message.original_chars,
                truncated=message.truncated,
                created_at=message.created_at,
            )
            for message in snapshot.messages
        ],
        event_summaries=[
            ContextEventSummaryResponse(
                type=event.type,
                count=event.count,
                latest_at=event.latest_at,
            )
            for event in snapshot.event_summaries
        ],
        files=[
            ContextFileReferenceResponse(
                id=file.id,
                name=file.name,
                content_type=file.content_type,
                size=file.size,
                usage_hint=file.usage_hint,
            )
            for file in snapshot.files
        ],
        memory_context=MemoryContextResponse(
            query=snapshot.memory_context.query,
            items=[
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
                for item in snapshot.memory_context.items
            ],
            candidate_count=snapshot.memory_context.candidate_count,
            omitted_count=snapshot.memory_context.omitted_count,
            total_chars=snapshot.memory_context.total_chars,
            max_chars=snapshot.memory_context.max_chars,
        ),
        budget=ContextBudgetResponse(
            message_limit=snapshot.budget.message_limit,
            event_limit=snapshot.budget.event_limit,
            max_message_chars=snapshot.budget.max_message_chars,
            included_messages=snapshot.budget.included_messages,
            omitted_messages=snapshot.budget.omitted_messages,
            included_events=snapshot.budget.included_events,
            omitted_events=snapshot.budget.omitted_events,
            total_message_chars=snapshot.budget.total_message_chars,
            memory_limit=snapshot.budget.memory_limit,
            max_memory_chars=snapshot.budget.max_memory_chars,
            included_memories=snapshot.budget.included_memories,
            omitted_memories=snapshot.budget.omitted_memories,
            total_memory_chars=snapshot.budget.total_memory_chars,
        ),
    )


def to_runner_stream_payload(item: AgentRunnerStreamItem) -> dict:
    """把 Runner 产出的领域对象转换成 SSE 可以发送的 JSON 数据。"""

    if isinstance(item.payload, Session):
        return to_session_response(item.payload).model_dump(mode="json")
    if isinstance(item.payload, SessionEvent):
        return to_event_response(item.payload).model_dump(mode="json")
    return item.payload


@router.post("", response_model=ApiResponse[SessionResponse])
async def create_session(
    payload: SessionCreateRequest,
    service: SessionService = Depends(build_session_service),
) -> ApiResponse[SessionResponse]:
    session = await service.create_session(payload.title)
    return ApiResponse(data=to_session_response(session))


@router.get("", response_model=ApiResponse[SessionListResponse])
async def list_sessions(
    service: SessionService = Depends(build_session_service),
) -> ApiResponse[SessionListResponse]:
    sessions = await service.list_sessions()
    return ApiResponse(
        data=SessionListResponse(
            items=[to_session_response(session) for session in sessions],
        )
    )


@router.get("/{session_id}", response_model=ApiResponse[SessionResponse])
async def get_session(
    session_id: UUID,
    service: SessionService = Depends(build_session_service),
) -> ApiResponse[SessionResponse]:
    session = await service.get_session(session_id)
    return ApiResponse(data=to_session_response(session))


@router.get(
    "/{session_id}/context",
    response_model=ApiResponse[SessionContextResponse],
)
async def get_session_context(
    session_id: UUID,
    service: ContextEngineeringService = Depends(build_context_engineering_service),
) -> ApiResponse[SessionContextResponse]:
    snapshot = await service.build_snapshot(session_id)
    return ApiResponse(data=to_context_response(snapshot))


@router.get(
    "/{session_id}/messages",
    response_model=ApiResponse[MessageListResponse],
)
async def list_messages(
    session_id: UUID,
    service: SessionService = Depends(build_session_service),
) -> ApiResponse[MessageListResponse]:
    messages = await service.list_messages(session_id)
    return ApiResponse(
        data=MessageListResponse(
            items=[to_message_response(message) for message in messages],
        )
    )


@router.post(
    "/{session_id}/messages",
    response_model=ApiResponse[MessageCreateResponse],
)
async def create_message(
    session_id: UUID,
    payload: MessageCreateRequest,
    service: SessionService = Depends(build_session_service),
) -> ApiResponse[MessageCreateResponse]:
    message, event = await service.create_user_message(
        session_id=session_id,
        content=payload.content,
    )
    return ApiResponse(
        data=MessageCreateResponse(
            message=to_message_response(message),
            event=to_event_response(event),
        )
    )


@router.post("/{session_id}/messages/stream")
async def stream_message(
    session_id: UUID,
    payload: MessageCreateRequest,
    runner: AgentRunnerService = Depends(build_agent_runner_service),
) -> StreamingResponse:
    async def event_stream():
        # ===================== 第1步：Runner 统一产出 SSE 需要的状态和事件 =====================
        async for item in runner.stream_user_message(
            session_id=session_id,
            content=payload.content,
        ):
            yield encode_sse(item.name, to_runner_stream_payload(item))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{session_id}/stop", response_model=ApiResponse[SessionResponse])
async def stop_session(
    session_id: UUID,
    service: SessionService = Depends(build_session_service),
) -> ApiResponse[SessionResponse]:
    session = await service.stop_session(session_id)
    return ApiResponse(data=to_session_response(session))


@router.post("/{session_id}/read", response_model=ApiResponse[SessionResponse])
async def clear_unread(
    session_id: UUID,
    service: SessionService = Depends(build_session_service),
) -> ApiResponse[SessionResponse]:
    session = await service.clear_unread(session_id)
    return ApiResponse(data=to_session_response(session))


@router.get(
    "/{session_id}/events",
    response_model=ApiResponse[SessionEventListResponse],
)
async def list_events(
    session_id: UUID,
    service: SessionService = Depends(build_session_service),
) -> ApiResponse[SessionEventListResponse]:
    events = await service.list_events(session_id)
    return ApiResponse(
        data=SessionEventListResponse(
            items=[to_event_response(event) for event in events],
        )
    )


@router.post(
    "/{session_id}/plan",
    response_model=ApiResponse[PlanCreateResponse],
)
async def create_plan(
    session_id: UUID,
    payload: PlanCreateRequest,
    service: PlannerService = Depends(build_planner_service),
) -> ApiResponse[PlanCreateResponse]:
    plan, event = await service.create_plan(
        session_id=session_id,
        task=payload.task,
    )
    return ApiResponse(
        data=PlanCreateResponse(
            plan=to_plan_response(plan),
            event=to_event_response(event),
        )
    )


@router.post(
    "/{session_id}/plan/execute",
    response_model=ApiResponse[PlanExecuteResponse],
)
async def execute_plan(
    session_id: UUID,
    service: AgentRunnerService = Depends(build_agent_runner_service),
) -> ApiResponse[PlanExecuteResponse]:
    events = await service.execute_latest_plan(session_id)
    return ApiResponse(
        data=PlanExecuteResponse(
            events=[to_event_response(event) for event in events],
        )
    )


@router.post(
    "/{session_id}/plan/tasks",
    response_model=ApiResponse[AgentTaskResponse],
)
async def start_plan_task(
    session_id: UUID,
    service: SessionService = Depends(build_session_service),
    queue: RedisAgentTaskQueue = Depends(get_task_queue),
) -> ApiResponse[AgentTaskResponse]:
    # ===================== 第1步：先确认会话存在 =====================
    await service.get_session(session_id)

    # ===================== 第2步：把执行计划任务写入 Redis Stream =====================
    task = await queue.enqueue_execute_plan(session_id)
    return ApiResponse(data=to_agent_task_response(task))


@router.get(
    "/tasks/{task_id}",
    response_model=ApiResponse[AgentTaskResponse],
)
async def get_agent_task(
    task_id: str,
    queue: RedisAgentTaskQueue = Depends(get_task_queue),
) -> ApiResponse[AgentTaskResponse]:
    task = await queue.get_task(task_id)
    if task is None:
        raise AppException(
            message="task not found",
            code=404,
            status_code=404,
        )
    return ApiResponse(data=to_agent_task_response(task))


@router.post(
    "/tasks/{task_id}/cancel",
    response_model=ApiResponse[AgentTaskResponse],
)
async def cancel_agent_task(
    task_id: str,
    request: Request,
    queue: RedisAgentTaskQueue = Depends(get_task_queue),
) -> ApiResponse[AgentTaskResponse]:
    task = await queue.cancel_task(task_id)
    if task is None:
        raise AppException(
            message="task not found",
            code=404,
            status_code=404,
        )
    request.app.state.task_runner.cancel_task(task_id)
    return ApiResponse(data=to_agent_task_response(task))


@router.post(
    "/tasks/{task_id}/retry",
    response_model=ApiResponse[AgentTaskResponse],
)
async def retry_agent_task(
    task_id: str,
    queue: RedisAgentTaskQueue = Depends(get_task_queue),
) -> ApiResponse[AgentTaskResponse]:
    task = await queue.retry_task(task_id)
    if task is None:
        raise AppException(
            message="task not found",
            code=404,
            status_code=404,
        )
    return ApiResponse(data=to_agent_task_response(task))


@router.get(
    "/{session_id}/tasks/latest",
    response_model=ApiResponse[AgentTaskResponse],
)
async def recover_latest_session_task(
    session_id: UUID,
    queue: RedisAgentTaskQueue = Depends(get_task_queue),
) -> ApiResponse[AgentTaskResponse]:
    task = await queue.recover_session_task(session_id)
    if task is None:
        raise AppException(
            message="task not found",
            code=404,
            status_code=404,
        )
    return ApiResponse(data=to_agent_task_response(task))


@router.post(
    "/{session_id}/files",
    response_model=ApiResponse[SessionFileResponse],
)
async def upload_session_file(
    session_id: UUID,
    upload: UploadFile = File(...),
    service: FileService = Depends(build_file_service),
) -> ApiResponse[SessionFileResponse]:
    content = await upload.read()
    session_file = await service.save_session_upload(
        session_id=session_id,
        original_name=upload.filename or "",
        content_type=upload.content_type,
        content=content,
    )
    return ApiResponse(data=to_session_file_response(session_file))


@router.get(
    "/{session_id}/files",
    response_model=ApiResponse[SessionFileListResponse],
)
async def list_session_files(
    session_id: UUID,
    service: FileService = Depends(build_file_service),
) -> ApiResponse[SessionFileListResponse]:
    files = await service.list_session_files(session_id)
    return ApiResponse(
        data=SessionFileListResponse(
            items=[to_session_file_response(file) for file in files],
        )
    )


@router.delete("/{session_id}", status_code=204)
async def delete_session(
    session_id: UUID,
    service: SessionService = Depends(build_session_service),
) -> Response:
    await service.delete_session(session_id)
    return Response(status_code=204)
