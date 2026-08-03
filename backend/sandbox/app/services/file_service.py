from pathlib import Path
from shutil import rmtree

from fastapi import UploadFile

from app.core.config import Settings
from app.core.exceptions import SandboxException
from app.schemas.files import (
    FileDeleteResponse,
    FileEntryResponse,
    FileListResponse,
    FileReadResponse,
    FileReplaceResponse,
    FileUploadResponse,
    FileWriteResponse,
)


class SandboxFileService:
    """把所有文件操作限制在 workspace 目录内。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.workspace = Path(settings.workspace_dir).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)

    # ===================== 第1步：浏览目录 =====================
    def list_files(self, path: str = ".") -> FileListResponse:
        target = self._resolve_path(path)
        if not target.exists():
            raise SandboxException(message="path not found", code=404, status_code=404)
        if not target.is_dir():
            raise SandboxException(message="path is not a directory")

        items = [self._to_entry(child) for child in sorted(target.iterdir())]
        return FileListResponse(current_path=self._to_relative_path(target), items=items)

    # ===================== 第2步：读取文本文件 =====================
    def read_file(self, path: str) -> FileReadResponse:
        target = self._resolve_existing_file(path)
        raw_content = target.read_bytes()
        truncated = len(raw_content) > self.settings.max_file_read_bytes
        preview = raw_content[: self.settings.max_file_read_bytes]
        content = preview.decode("utf-8", errors="replace")
        return FileReadResponse(
            path=self._to_relative_path(target),
            content=content,
            size=len(raw_content),
            truncated=truncated,
        )

    # ===================== 第3步：写入文本文件 =====================
    def write_file(
        self,
        path: str,
        content: str,
        create_parent: bool,
    ) -> FileWriteResponse:
        encoded = content.encode("utf-8")
        if len(encoded) > self.settings.max_file_write_bytes:
            raise SandboxException(message="file content is too large", code=413, status_code=413)

        target = self._resolve_path(path)
        if target.exists() and target.is_dir():
            raise SandboxException(message="path is a directory")
        if create_parent:
            target.parent.mkdir(parents=True, exist_ok=True)
        elif not target.parent.exists():
            raise SandboxException(message="parent directory not found", code=404, status_code=404)

        target.write_bytes(encoded)
        return FileWriteResponse(path=self._to_relative_path(target), size=len(encoded))

    # ===================== 第4步：替换文本内容 =====================
    def replace_text(
        self,
        path: str,
        old_text: str,
        new_text: str,
    ) -> FileReplaceResponse:
        current = self.read_file(path)
        replacements = current.content.count(old_text)
        next_content = current.content.replace(old_text, new_text)
        self.write_file(path=path, content=next_content, create_parent=False)
        return FileReplaceResponse(
            path=current.path,
            replacements=replacements,
            content=next_content,
        )

    # ===================== 第5步：删除文件或目录 =====================
    def delete_path(self, path: str) -> FileDeleteResponse:
        target = self._resolve_path(path)
        if target == self.workspace:
            raise SandboxException(message="workspace root cannot be deleted")
        if not target.exists():
            raise SandboxException(message="path not found", code=404, status_code=404)
        if target.is_dir():
            rmtree(target)
        else:
            target.unlink()
        return FileDeleteResponse(path=path, deleted=True)

    # ===================== 第6步：保存上传文件 =====================
    async def save_upload(
        self,
        directory: str,
        upload: UploadFile,
    ) -> FileUploadResponse:
        filename = Path(upload.filename or "").name
        if not filename:
            raise SandboxException(message="filename is required")

        target_dir = self._resolve_path(directory)
        target_dir.mkdir(parents=True, exist_ok=True)
        if not target_dir.is_dir():
            raise SandboxException(message="upload target is not a directory")

        content = await upload.read()
        if len(content) > self.settings.max_upload_size:
            raise SandboxException(message="upload file is too large", code=413, status_code=413)

        target = self._resolve_path(str(Path(directory) / filename))
        target.write_bytes(content)
        return FileUploadResponse(
            path=self._to_relative_path(target),
            original_name=filename,
            size=len(content),
        )

    # ===================== 第7步：获取下载路径 =====================
    def get_download_path(self, path: str) -> Path:
        return self._resolve_existing_file(path)

    # ===================== 第8步：路径安全校验 =====================
    def _resolve_path(self, path: str) -> Path:
        clean_path = path.strip() or "."
        if Path(clean_path).is_absolute():
            raise SandboxException(message="absolute path is not allowed")

        target = (self.workspace / clean_path).resolve()
        if target != self.workspace and self.workspace not in target.parents:
            raise SandboxException(message="path escapes workspace")
        return target

    def _resolve_existing_file(self, path: str) -> Path:
        target = self._resolve_path(path)
        if not target.exists():
            raise SandboxException(message="file not found", code=404, status_code=404)
        if not target.is_file():
            raise SandboxException(message="path is not a file")
        return target

    def _to_entry(self, path: Path) -> FileEntryResponse:
        stat = path.stat()
        return FileEntryResponse(
            name=path.name,
            path=self._to_relative_path(path),
            type="directory" if path.is_dir() else "file",
            size=0 if path.is_dir() else stat.st_size,
            modified_at=stat.st_mtime,
        )

    def _to_relative_path(self, path: Path) -> str:
        relative = path.resolve().relative_to(self.workspace)
        return "." if str(relative) == "." else relative.as_posix()
