from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class FileResponse(BaseModel):
    id: UUID
    original_name: str
    content_type: str
    size: int
    download_url: str
    created_at: datetime


class SessionFileResponse(BaseModel):
    id: UUID
    session_id: UUID
    file: FileResponse
    created_at: datetime


class SessionFileListResponse(BaseModel):
    items: list[SessionFileResponse]


class FileReferenceResponse(BaseModel):
    label: str
    excerpt: str
    start_line: int | None = None
    end_line: int | None = None


class FilePreviewResponse(BaseModel):
    file: FileResponse
    content: str
    file_type: str
    language: str | None
    line_count: int
    parse_status: str
    parse_message: str
    references: list[FileReferenceResponse]
    summary: str
    truncated: bool
