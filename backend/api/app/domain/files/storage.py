from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(slots=True)
class StoredFile:
    stored_name: str
    storage_path: str


class FileStorage(Protocol):
    def save(self, clean_name: str, content: bytes) -> StoredFile:
        raise NotImplementedError

    def delete(self, storage_path: str) -> None:
        raise NotImplementedError

    def exists(self, storage_path: str) -> bool:
        raise NotImplementedError

    def read_bytes(self, storage_path: str, max_size: int | None = None) -> bytes:
        raise NotImplementedError

    def get_local_path(self, storage_path: str) -> Path:
        raise NotImplementedError
