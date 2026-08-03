from dataclasses import dataclass


@dataclass(slots=True)
class ProductAcceptanceItem:
    """一条最终产品体验验收项。"""

    key: str
    title: str
    category: str
    status: str
    evidence: str
    verify_steps: list[str]
    related_routes: list[str]


@dataclass(slots=True)
class ProductAcceptanceSummary:
    """最终验收清单的数量汇总。"""

    total: int
    ready: int
    needs_manual_check: int


@dataclass(slots=True)
class ProductAcceptanceChecklist:
    """最终产品体验验收清单。"""

    summary: ProductAcceptanceSummary
    items: list[ProductAcceptanceItem]
