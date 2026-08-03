from typing import Generic, TypeVar

from pydantic import BaseModel

DataT = TypeVar("DataT")


class ApiError(BaseModel):
    type: str
    source: str
    user_message: str
    suggestion: str
    request_id: str | None = None
    details: dict | None = None


class ApiResponse(BaseModel, Generic[DataT]):
    code: int = 200
    message: str = "success"
    data: DataT | None = None
    error: ApiError | None = None
