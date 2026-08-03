from pydantic import BaseModel


class SecurityCheckResponse(BaseModel):
    key: str
    name: str
    category: str
    severity: str
    risk: str
    recommendation: str
    verify_command: str


class SecurityCheckListResponse(BaseModel):
    items: list[SecurityCheckResponse]
