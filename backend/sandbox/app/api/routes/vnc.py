from fastapi import APIRouter, Depends

from app.schemas.common import ApiResponse
from app.schemas.vnc import VncStatusResponse
from app.services.vnc_service import VncService

router = APIRouter(prefix="/vnc", tags=["vnc"])


def build_vnc_service() -> VncService:
    # 第 28 章先直接创建 service；后续多沙箱时可以在这里按会话 ID 选择不同实例。
    return VncService()


@router.get("/status", response_model=ApiResponse[VncStatusResponse])
async def get_vnc_status(
    service: VncService = Depends(build_vnc_service),
) -> ApiResponse[VncStatusResponse]:
    # 前端工作台通过这个接口拿 iframe 地址，不需要硬编码 noVNC 细节。
    return ApiResponse(data=service.status())
