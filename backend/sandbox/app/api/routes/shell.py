from fastapi import APIRouter, Depends, Query

from app.core.config import settings
from app.schemas.common import ApiResponse
from app.schemas.shell import (
    ShellExecuteRequest,
    ShellSessionListResponse,
    ShellSessionResponse,
    ShellTerminateResponse,
    ShellWaitRequest,
    ShellWriteRequest,
    ShellWriteResponse,
)
from app.services.shell_service import SandboxShellService

router = APIRouter(prefix="/shell", tags=["shell"])

# Shell 会话必须跨请求保存，所以这里使用模块级 service。
shell_service = SandboxShellService(settings=settings)


def get_shell_service() -> SandboxShellService:
    return shell_service


@router.post("/sessions", response_model=ApiResponse[ShellSessionResponse])
async def execute_command(
    payload: ShellExecuteRequest,
    workspace: str = Query(default=""),
    full_access: bool = Query(default=False),
    service: SandboxShellService = Depends(get_shell_service),
) -> ApiResponse[ShellSessionResponse]:
    return ApiResponse(
        data=await service.execute(payload.command, payload.cwd, workspace, full_access)
    )


@router.get("/sessions", response_model=ApiResponse[ShellSessionListResponse])
async def list_sessions(
    service: SandboxShellService = Depends(get_shell_service),
) -> ApiResponse[ShellSessionListResponse]:
    return ApiResponse(data=service.list_sessions())


@router.get("/sessions/{session_id}", response_model=ApiResponse[ShellSessionResponse])
async def get_session(
    session_id: str,
    service: SandboxShellService = Depends(get_shell_service),
) -> ApiResponse[ShellSessionResponse]:
    return ApiResponse(data=service.get(session_id))


@router.post(
    "/sessions/{session_id}/wait",
    response_model=ApiResponse[ShellSessionResponse],
)
async def wait_session(
    session_id: str,
    payload: ShellWaitRequest,
    service: SandboxShellService = Depends(get_shell_service),
) -> ApiResponse[ShellSessionResponse]:
    return ApiResponse(data=await service.wait(session_id, payload.timeout_seconds))


@router.post(
    "/sessions/{session_id}/write",
    response_model=ApiResponse[ShellWriteResponse],
)
async def write_session(
    session_id: str,
    payload: ShellWriteRequest,
    service: SandboxShellService = Depends(get_shell_service),
) -> ApiResponse[ShellWriteResponse]:
    return ApiResponse(data=await service.write(session_id, payload.input))


@router.post(
    "/sessions/{session_id}/terminate",
    response_model=ApiResponse[ShellTerminateResponse],
)
async def terminate_session(
    session_id: str,
    service: SandboxShellService = Depends(get_shell_service),
) -> ApiResponse[ShellTerminateResponse]:
    return ApiResponse(data=await service.terminate(session_id))
