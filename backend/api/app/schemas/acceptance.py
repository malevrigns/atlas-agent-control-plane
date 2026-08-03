from pydantic import BaseModel


class ProductAcceptanceItemResponse(BaseModel):
    key: str
    title: str
    category: str
    status: str
    evidence: str
    verify_steps: list[str]
    related_routes: list[str]


class ProductAcceptanceSummaryResponse(BaseModel):
    total: int
    ready: int
    needs_manual_check: int


class ProductAcceptanceChecklistResponse(BaseModel):
    summary: ProductAcceptanceSummaryResponse
    items: list[ProductAcceptanceItemResponse]
