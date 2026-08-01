from fastapi import APIRouter, Depends, Query

from app.core.config import settings
from app.infrastructure.sandbox.manager import DockerSandboxManager, SandboxInstance
from app.schemas.common import ApiResponse
from app.schemas.sandbox import (
    SandboxFileReadResponse,
    SandboxFileWriteRequest,
    SandboxFileWriteResponse,
    SandboxInstanceResponse,
    SandboxShellRunRequest,
    SandboxShellRunResponse,
    SandboxWaitRequest,
)

router = APIRouter(prefix="/sandboxes", tags=["sandboxes"])


def build_sandbox_manager() -> DockerSandboxManager:
    # 每次请求创建一个轻量 manager。真正跨请求的状态仍在 Sandbox 服务中。
    return DockerSandboxManager(settings=settings)


def to_instance_response(instance: SandboxInstance) -> SandboxInstanceResponse:
    # 路由层只暴露 Pydantic 响应模型，不直接返回 dataclass。
    return SandboxInstanceResponse(
        id=instance.id,
        name=instance.name,
        base_url=instance.base_url,
        status=instance.status,
        message=instance.message,
    )


@router.get("/current", response_model=ApiResponse[SandboxInstanceResponse])
async def get_current_sandbox(
    manager: DockerSandboxManager = Depends(build_sandbox_manager),
) -> ApiResponse[SandboxInstanceResponse]:
    # 前端工作台首次加载时调用，用来显示当前任务沙箱是否 ready。
    return ApiResponse(data=to_instance_response(manager.get_current()))


@router.post("/current/ensure", response_model=ApiResponse[SandboxInstanceResponse])
async def ensure_current_sandbox(
    manager: DockerSandboxManager = Depends(build_sandbox_manager),
) -> ApiResponse[SandboxInstanceResponse]:
    # 当前阶段 ensure 只做健康检查；后续可在 manager 内替换成真实创建容器。
    return ApiResponse(data=to_instance_response(manager.ensure_current()))


@router.post("/current/wait", response_model=ApiResponse[SandboxInstanceResponse])
async def wait_current_sandbox(
    payload: SandboxWaitRequest,
    manager: DockerSandboxManager = Depends(build_sandbox_manager),
) -> ApiResponse[SandboxInstanceResponse]:
    # 前端点击刷新时调用，给刚启动的 Sandbox 一段变健康的时间。
    return ApiResponse(
        data=to_instance_response(
            manager.wait_until_ready(
                retries=payload.retries,
                interval_seconds=payload.interval_seconds,
            )
        )
    )


@router.delete("/current", response_model=ApiResponse[SandboxInstanceResponse])
async def release_current_sandbox(
    manager: DockerSandboxManager = Depends(build_sandbox_manager),
) -> ApiResponse[SandboxInstanceResponse]:
    # 本章只释放引用，不停止 Compose 管理的共享 sandbox 容器。
    return ApiResponse(data=to_instance_response(manager.release_current()))


@router.get("/current/files/read", response_model=ApiResponse[SandboxFileReadResponse])
async def read_sandbox_file(
    path: str = Query(min_length=1),
    manager: DockerSandboxManager = Depends(build_sandbox_manager),
) -> ApiResponse[SandboxFileReadResponse]:
    # 通过 manager 代理到 Sandbox File API，路径越界仍由 Sandbox 服务拦截。
    return ApiResponse(data=SandboxFileReadResponse(**manager.read_file(path)))


@router.post(
    "/current/files/write",
    response_model=ApiResponse[SandboxFileWriteResponse],
)
async def write_sandbox_file(
    payload: SandboxFileWriteRequest,
    manager: DockerSandboxManager = Depends(build_sandbox_manager),
) -> ApiResponse[SandboxFileWriteResponse]:
    # 主 API 不直接写文件，只转发到当前 Sandbox。
    return ApiResponse(
        data=SandboxFileWriteResponse(
            **manager.write_file(
                path=payload.path,
                content=payload.content,
                create_parent=payload.create_parent,
            )
        )
    )


@router.post(
    "/current/shell/run",
    response_model=ApiResponse[SandboxShellRunResponse],
)
async def run_sandbox_shell(
    payload: SandboxShellRunRequest,
    manager: DockerSandboxManager = Depends(build_sandbox_manager),
) -> ApiResponse[SandboxShellRunResponse]:
    # Shell 命令仍在 Sandbox 中执行，主 API 只负责代理和等待。
    return ApiResponse(
        data=SandboxShellRunResponse(
            **manager.run_shell(
                command=payload.command,
                cwd=payload.cwd,
                timeout_seconds=payload.timeout_seconds,
            )
        )
    )
