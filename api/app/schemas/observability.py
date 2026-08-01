from pydantic import BaseModel


class ObservabilityCheckResponse(BaseModel):
    key: str
    name: str
    category: str
    description: str
    command: str
    expected: str


class ObservabilityCheckListResponse(BaseModel):
    items: list[ObservabilityCheckResponse]
