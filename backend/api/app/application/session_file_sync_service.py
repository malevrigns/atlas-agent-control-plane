from pathlib import Path
from typing import Protocol
from uuid import UUID

from app.application.unit_of_work import UnitOfWork


SYNCABLE_CONTENT_TYPES = {
    "application/json",
    "application/xml",
    "application/yaml",
}
SYNCABLE_SUFFIXES = {
    ".css",
    ".csv",
    ".html",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".py",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}


class FileStorage(Protocol):
    def read_bytes(self, storage_path: str, max_size: int) -> bytes: ...


class SandboxFiles(Protocol):
    def write_file(self, *, path: str, content: str, create_parent: bool) -> object: ...


class SessionFileSyncService:
    def __init__(
        self,
        uow: UnitOfWork,
        *,
        storage: FileStorage,
        sandbox_files: SandboxFiles,
        max_file_size: int,
    ) -> None:
        self._uow = uow
        self._storage = storage
        self._sandbox_files = sandbox_files
        self._max_file_size = max_file_size

    async def sync(self, session_id: UUID) -> None:
        session_files = await self._uow.session_files.list_by_session(session_id)
        for session_file in session_files:
            file_object = session_file.file
            if not self.is_syncable(
                file_object.content_type,
                file_object.original_name,
            ):
                continue
            raw_content = self._storage.read_bytes(
                file_object.storage_path,
                max_size=self._max_file_size,
            )
            content = raw_content.decode("utf-8", errors="replace")
            safe_name = Path(file_object.original_name).name
            for path in {safe_name, f"attachments/{safe_name}"}:
                self._sandbox_files.write_file(
                    path=path,
                    content=content,
                    create_parent=True,
                )

    @staticmethod
    def is_syncable(content_type: str, filename: str) -> bool:
        clean_type = content_type.split(";")[0].lower()
        if clean_type.startswith("text/") or clean_type in SYNCABLE_CONTENT_TYPES:
            return True
        return Path(filename).suffix.lower() in SYNCABLE_SUFFIXES
