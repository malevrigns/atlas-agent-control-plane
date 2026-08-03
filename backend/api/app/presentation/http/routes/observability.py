from fastapi import APIRouter, Depends

from app.application.observability_service import ObservabilityService
from app.domain.observability.entities import ObservabilityCheck
from app.schemas.common import ApiResponse
from app.schemas.observability import (
    ObservabilityCheckListResponse,
    ObservabilityCheckResponse,
)

router = APIRouter(prefix="/observability", tags=["observability"])


def build_observability_service() -> ObservabilityService:
    return ObservabilityService()


def to_check_response(check: ObservabilityCheck) -> ObservabilityCheckResponse:
    return ObservabilityCheckResponse(
        key=check.key,
        name=check.name,
        category=check.category,
        description=check.description,
        command=check.command,
        expected=check.expected,
    )


@router.get("/checks", response_model=ApiResponse[ObservabilityCheckListResponse])
async def list_observability_checks(
    service: ObservabilityService = Depends(build_observability_service),
) -> ApiResponse[ObservabilityCheckListResponse]:
    # ===================== 第1步：读取可执行诊断清单 =====================
    checks = service.list_checks()

    # ===================== 第2步：转换成统一响应结构 =====================
    return ApiResponse(
        data=ObservabilityCheckListResponse(
            items=[to_check_response(check) for check in checks],
        )
    )
