import json
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.control_plane_service import ControlPlaneService
from app.application.unit_of_work import UnitOfWork
from app.infrastructure.database.session import get_db_session
from app.schemas.common import ApiResponse
from app.schemas.control_plane import (
    ArtifactResponse,
    CheckpointCreateRequest,
    CheckpointListResponse,
    CheckpointResponse,
    EnvironmentSnapshotRequest,
    EnvironmentSnapshotResponse,
    TaskStateCreateRequest,
    TaskStateListResponse,
    TaskStateResponse,
    TaskStateUpdateRequest,
    ToolInvocationListResponse,
    ToolInvocationResponse,
)

router = APIRouter(prefix="/control-plane", tags=["control-plane"])


def build_service(db_session: AsyncSession = Depends(get_db_session)) -> ControlPlaneService:
    return ControlPlaneService(UnitOfWork(db_session))


@router.post("/tasks", response_model=ApiResponse[TaskStateResponse])
async def create_task(
    payload: TaskStateCreateRequest,
    service: ControlPlaneService = Depends(build_service),
) -> ApiResponse[TaskStateResponse]:
    task = await service.create_task(payload.model_dump())
    return ApiResponse(data=TaskStateResponse.model_validate(task))


@router.get("/tasks", response_model=ApiResponse[TaskStateListResponse])
async def list_tasks(
    project_id: str = Query(default="default"),
    limit: int = Query(default=100, ge=1, le=500),
    service: ControlPlaneService = Depends(build_service),
) -> ApiResponse[TaskStateListResponse]:
    tasks = await service.list_tasks(project_id, limit)
    return ApiResponse(data=TaskStateListResponse(items=[TaskStateResponse.model_validate(item) for item in tasks]))


@router.get("/tasks/{task_id}", response_model=ApiResponse[TaskStateResponse])
async def get_task(
    task_id: UUID,
    service: ControlPlaneService = Depends(build_service),
) -> ApiResponse[TaskStateResponse]:
    return ApiResponse(data=TaskStateResponse.model_validate(await service.get_task(task_id)))


@router.patch("/tasks/{task_id}", response_model=ApiResponse[TaskStateResponse])
async def update_task(
    task_id: UUID,
    payload: TaskStateUpdateRequest,
    service: ControlPlaneService = Depends(build_service),
) -> ApiResponse[TaskStateResponse]:
    values = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
    task = await service.update_task(task_id, expected_version=payload.expected_version, patch=values)
    return ApiResponse(data=TaskStateResponse.model_validate(task))


@router.post("/tasks/{task_id}/checkpoints", response_model=ApiResponse[CheckpointResponse])
async def create_checkpoint(
    task_id: UUID,
    payload: CheckpointCreateRequest,
    service: ControlPlaneService = Depends(build_service),
) -> ApiResponse[CheckpointResponse]:
    checkpoint = await service.create_checkpoint(task_id, **payload.model_dump())
    return ApiResponse(data=CheckpointResponse.model_validate(checkpoint))


@router.get("/tasks/{task_id}/checkpoints", response_model=ApiResponse[CheckpointListResponse])
async def list_checkpoints(
    task_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    service: ControlPlaneService = Depends(build_service),
) -> ApiResponse[CheckpointListResponse]:
    items = await service.list_checkpoints(task_id, limit)
    return ApiResponse(data=CheckpointListResponse(items=[CheckpointResponse.model_validate(item) for item in items]))


@router.post("/artifacts", response_model=ApiResponse[ArtifactResponse])
async def create_artifact(
    upload: UploadFile = File(...),
    kind: str = Form(default="file"),
    project_id: str = Form(default="default"),
    task_id: UUID | None = Form(default=None),
    source_event_id: UUID | None = Form(default=None),
    sensitivity: str = Form(default="internal"),
    metadata_json: str = Form(default="{}"),
    service: ControlPlaneService = Depends(build_service),
) -> ApiResponse[ArtifactResponse]:
    content = await upload.read()
    metadata = json.loads(metadata_json)
    artifact = await service.persist_artifact(
        content,
        kind=kind,
        media_type=upload.content_type or "application/octet-stream",
        project_id=project_id,
        task_id=task_id,
        source_event_id=source_event_id,
        metadata=metadata,
        sensitivity=sensitivity,
    )
    public = {key: value for key, value in artifact.items() if key != "storage_path"}
    return ApiResponse(data=ArtifactResponse.model_validate(public))


@router.post("/environment", response_model=ApiResponse[EnvironmentSnapshotResponse])
async def capture_environment(
    payload: EnvironmentSnapshotRequest,
    service: ControlPlaneService = Depends(build_service),
) -> ApiResponse[EnvironmentSnapshotResponse]:
    result = await service.capture_environment(**payload.model_dump())
    return ApiResponse(data=EnvironmentSnapshotResponse.model_validate(result))


@router.get("/tool-invocations", response_model=ApiResponse[ToolInvocationListResponse])
async def list_tool_invocations(
    project_id: str = Query(default="default"),
    task_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db_session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[ToolInvocationListResponse]:
    items = await UnitOfWork(db_session).control_plane.list_tool_invocations(
        project_id=project_id,
        task_id=task_id,
        limit=limit,
    )
    return ApiResponse(data=ToolInvocationListResponse(
        items=[ToolInvocationResponse.model_validate(item) for item in items]
    ))
