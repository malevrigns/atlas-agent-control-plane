from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SkillCreateRequest(BaseModel):
    skill_key: str = Field(min_length=3, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    description: str = ""
    instructions: str = Field(min_length=1)
    version: str = Field(default="1.0.0", max_length=32)
    definition: dict[str, object] = Field(default_factory=dict)
    risk_level: str = "low"
    tags: list[str] = Field(default_factory=list, max_length=16)
    created_by: str = Field(default="operator", max_length=128)


class SkillUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    instructions: str | None = None
    definition: dict[str, object] | None = None
    risk_level: str | None = None
    tags: list[str] | None = Field(default=None, max_length=16)


class SkillEnableRequest(BaseModel):
    enabled: bool


class SkillNewVersionRequest(BaseModel):
    version: str | None = Field(default=None, max_length=32)
    created_by: str = Field(default="operator", max_length=128)


class SkillTestRecordRequest(BaseModel):
    test_record: dict[str, object]


class SkillResponse(BaseModel):
    id: UUID
    skill_key: str
    version: str
    name: str
    description: str
    instructions: str
    definition: dict[str, object]
    risk_level: str
    status: str
    enabled: bool
    tags: list[str]
    test_record: dict[str, object]
    created_by: str
    created_at: datetime | None
    updated_at: datetime | None
    published_at: datetime | None


class SkillListResponse(BaseModel):
    items: list[SkillResponse]


class SkillContextItemResponse(BaseModel):
    id: UUID
    skill_key: str
    version: str
    name: str
    instructions: str
    risk_level: str
    relevance_score: float
    matched_terms: list[str]


class SkillContextResponse(BaseModel):
    query: str
    items: list[SkillContextItemResponse]
    candidate_count: int
    omitted_count: int
    total_chars: int
    rendered: str
