from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.application.agent_runner_service import AgentRunnerService
from app.application.context_engineering_service import ContextEngineeringService
from app.application.session_service import SessionService
from app.presentation.http.routes.session_route_dependencies import (
    build_agent_runner_service,
    build_context_engineering_service,
    build_session_service,
)
from app.presentation.http.routes.session_route_responses import (
    to_context_response,
    to_event_response,
    to_message_response,
    to_runner_stream_payload,
    to_session_response,
)
from app.presentation.http.sse import encode_sse
from app.schemas.common import ApiResponse
from app.schemas.session import (
    MessageCreateRequest,
    MessageCreateResponse,
    MessageListResponse,
    SessionContextResponse,
    SessionCreateRequest,
    SessionEventListResponse,
    SessionListResponse,
    SessionResponse,
)

router = APIRouter()


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
    items = [to_session_response(session) for session in sessions]
    return ApiResponse(data=SessionListResponse(items=items))


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
    items = [to_message_response(message) for message in messages]
    return ApiResponse(data=MessageListResponse(items=items))


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
        async for item in runner.stream_user_message(
            session_id=session_id,
            content=payload.content,
            skill_ids=payload.skill_ids,
            resume=payload.resume,
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
    items = [to_event_response(event) for event in events]
    return ApiResponse(data=SessionEventListResponse(items=items))
