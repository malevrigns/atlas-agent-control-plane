from typing import Protocol
from uuid import UUID

from app.domain.files.entities import FileObject, SessionFile


class FileRepository(Protocol):
    async def add(
        self,
        original_name: str,
        stored_name: str,
        content_type: str,
        size: int,
        storage_path: str,
    ) -> FileObject:
        raise NotImplementedError

    async def get(self, file_id: UUID) -> FileObject | None:
        raise NotImplementedError

    async def delete(self, file_object: FileObject) -> None:
        raise NotImplementedError


class SessionFileRepository(Protocol):
    async def add(self, session_id: UUID, file_id: UUID) -> SessionFile:
        raise NotImplementedError

    async def get(self, session_file_id: UUID) -> SessionFile | None:
        raise NotImplementedError

    async def list_by_session(self, session_id: UUID) -> list[SessionFile]:
        raise NotImplementedError

    async def delete(self, session_file: SessionFile) -> None:
        raise NotImplementedError
