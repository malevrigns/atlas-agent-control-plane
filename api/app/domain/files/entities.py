from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(slots=True)
class FileObject:
    id: UUID
    original_name: str
    stored_name: str
    content_type: str
    size: int
    storage_path: str
    created_at: datetime


@dataclass(slots=True)
class SessionFile:
    id: UUID
    session_id: UUID
    file: FileObject
    created_at: datetime
