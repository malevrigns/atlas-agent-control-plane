from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.application.agent_runner_service import AgentRunnerService
from app.application.planner_service import PlannerService
from app.application.session_service import SessionService
from app.core.exceptions import AppException
from app.infrastructure.task_queue import RedisAgentTaskQueue
from app.presentation.http.routes.session_route_dependencies import (
    build_agent_runner_service,
    build_planner_service,
    build_session_service,
    get_task_queue,
)
from app.presentation.http.routes.session_route_responses import (
    to_agent_task_response,
    to_event_response,
    to_plan_response,
)
from app.schemas.common import ApiResponse
from app.schemas.session import (
    AgentTaskResponse,
    PlanCreateRequest,
    PlanCreateResponse,
    PlanExecuteResponse,
)

router = APIRouter()


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
    items = [to_event_response(event) for event in events]
    return ApiResponse(data=PlanExecuteResponse(events=items))


@router.post(
    "/{session_id}/plan/tasks",
    response_model=ApiResponse[AgentTaskResponse],
)
async def start_plan_task(
    session_id: UUID,
    service: SessionService = Depends(build_session_service),
    queue: RedisAgentTaskQueue = Depends(get_task_queue),
) -> ApiResponse[AgentTaskResponse]:
    await service.get_session(session_id)
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
    return ApiResponse(data=to_agent_task_response(_require_task(task)))


@router.post(
    "/tasks/{task_id}/cancel",
    response_model=ApiResponse[AgentTaskResponse],
)
async def cancel_agent_task(
    task_id: str,
    request: Request,
    queue: RedisAgentTaskQueue = Depends(get_task_queue),
) -> ApiResponse[AgentTaskResponse]:
    task = _require_task(await queue.cancel_task(task_id))
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
    return ApiResponse(data=to_agent_task_response(_require_task(task)))


@router.get(
    "/{session_id}/tasks/latest",
    response_model=ApiResponse[AgentTaskResponse],
)
async def recover_latest_session_task(
    session_id: UUID,
    queue: RedisAgentTaskQueue = Depends(get_task_queue),
) -> ApiResponse[AgentTaskResponse]:
    task = await queue.recover_session_task(session_id)
    return ApiResponse(data=to_agent_task_response(_require_task(task)))


def _require_task(task):
    if task is None:
        raise AppException(
            message="task not found",
            code=404,
            status_code=404,
        )
    return task
