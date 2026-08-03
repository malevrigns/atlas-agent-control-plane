from pydantic import BaseModel


class StatusData(BaseModel):
    service: str
    environment: str
    status: str
    version: str


class DatabaseStatusData(BaseModel):
    status: str
