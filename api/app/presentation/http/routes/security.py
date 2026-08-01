from fastapi import APIRouter, Depends

from app.application.security_audit_service import SecurityAuditService
from app.domain.security.entities import SecurityCheck
from app.schemas.common import ApiResponse
from app.schemas.security import SecurityCheckListResponse, SecurityCheckResponse

router = APIRouter(prefix="/security", tags=["security"])


def build_security_audit_service() -> SecurityAuditService:
    return SecurityAuditService()


def to_security_check_response(check: SecurityCheck) -> SecurityCheckResponse:
    return SecurityCheckResponse(
        key=check.key,
        name=check.name,
        category=check.category,
        severity=check.severity,
        risk=check.risk,
        recommendation=check.recommendation,
        verify_command=check.verify_command,
    )


@router.get("/checks", response_model=ApiResponse[SecurityCheckListResponse])
async def list_security_checks(
    service: SecurityAuditService = Depends(build_security_audit_service),
) -> ApiResponse[SecurityCheckListResponse]:
    # ===================== 第1步：读取安全边界检查清单 =====================
    checks = service.list_checks()

    # ===================== 第2步：转换成统一响应结构，交给前端和 curl 使用 =====================
    return ApiResponse(
        data=SecurityCheckListResponse(
            items=[to_security_check_response(check) for check in checks],
        )
    )
