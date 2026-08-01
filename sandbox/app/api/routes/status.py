from fastapi import APIRouter

from app.core.config import settings
from app.schemas.common import ApiResponse
from app.schemas.status import SandboxStatusResponse

router = APIRouter(prefix="/status", tags=["status"])


@router.get("", response_model=ApiResponse[SandboxStatusResponse])
async def get_status() -> ApiResponse[SandboxStatusResponse]:
    # 状态接口只读取配置，不访问文件系统或外部进程，适合作为最小健康检查。
    return ApiResponse(
        data=SandboxStatusResponse(
            service=settings.sandbox_app_name,
            environment=settings.sandbox_env,
            status="ok",
            version=settings.sandbox_version,
            workspace_dir=settings.workspace_dir,
        )
    )
