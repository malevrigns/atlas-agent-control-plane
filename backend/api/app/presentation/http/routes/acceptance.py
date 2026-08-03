from fastapi import APIRouter, Depends

from app.application.product_acceptance_service import ProductAcceptanceService
from app.domain.acceptance.entities import (
    ProductAcceptanceChecklist,
    ProductAcceptanceItem,
)
from app.schemas.acceptance import (
    ProductAcceptanceChecklistResponse,
    ProductAcceptanceItemResponse,
    ProductAcceptanceSummaryResponse,
)
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/acceptance", tags=["acceptance"])


def build_product_acceptance_service() -> ProductAcceptanceService:
    return ProductAcceptanceService()


def to_item_response(item: ProductAcceptanceItem) -> ProductAcceptanceItemResponse:
    return ProductAcceptanceItemResponse(
        key=item.key,
        title=item.title,
        category=item.category,
        status=item.status,
        evidence=item.evidence,
        verify_steps=item.verify_steps,
        related_routes=item.related_routes,
    )


def to_checklist_response(
    checklist: ProductAcceptanceChecklist,
) -> ProductAcceptanceChecklistResponse:
    return ProductAcceptanceChecklistResponse(
        summary=ProductAcceptanceSummaryResponse(
            total=checklist.summary.total,
            ready=checklist.summary.ready,
            needs_manual_check=checklist.summary.needs_manual_check,
        ),
        items=[to_item_response(item) for item in checklist.items],
    )


@router.get("/checks", response_model=ApiResponse[ProductAcceptanceChecklistResponse])
async def get_product_acceptance_checks(
    service: ProductAcceptanceService = Depends(build_product_acceptance_service),
) -> ApiResponse[ProductAcceptanceChecklistResponse]:
    # ===================== 第1步：读取最终产品体验验收清单 =====================
    checklist = service.get_checklist()

    # ===================== 第2步：转换为前端可以直接渲染的响应结构 =====================
    return ApiResponse(data=to_checklist_response(checklist))
