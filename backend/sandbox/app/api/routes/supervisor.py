from fastapi import APIRouter, Depends

from app.schemas.common import ApiResponse
from app.schemas.supervisor import SupervisorStatusResponse
from app.services.supervisor_service import SupervisorService

router = APIRouter(prefix="/supervisor", tags=["supervisor"])


def build_supervisor_service() -> SupervisorService:
    # 这里先直接创建 service；后续如果接入缓存或外部客户端，可以在这里统一替换。
    return SupervisorService()


@router.get(
    "/services",
    response_model=ApiResponse[SupervisorStatusResponse],
)
async def list_supervisor_services(
    service: SupervisorService = Depends(build_supervisor_service),
) -> ApiResponse[SupervisorStatusResponse]:
    # 返回统一响应，方便主 API 或前端用同一种格式消费沙箱状态。
    return ApiResponse(data=service.list_services())
