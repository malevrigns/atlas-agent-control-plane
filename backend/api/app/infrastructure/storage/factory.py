from app.core.config import settings
from app.core.exceptions import AppException
from app.domain.files.storage import FileStorage
from app.infrastructure.storage.local import LocalFileStorage


def build_file_storage() -> FileStorage:
    if settings.file_storage_backend == "local":
        return LocalFileStorage(settings.upload_dir)

    # 这里先明确失败，避免配置了未实现的对象存储后静默写入本地目录。
    raise AppException(
        message=f"unsupported file storage backend: {settings.file_storage_backend}",
        code=500,
        status_code=500,
    )
