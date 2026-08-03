from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse as DownloadFileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.file_service import FileService
from app.application.unit_of_work import UnitOfWork
from app.domain.files.entities import FileObject
from app.infrastructure.database.session import get_db_session
from app.schemas.common import ApiResponse
from app.schemas.file import FilePreviewResponse, FileReferenceResponse, FileResponse

router = APIRouter(prefix="/files", tags=["files"])


def build_file_service(
    db_session: AsyncSession = Depends(get_db_session),
) -> FileService:
    return FileService(UnitOfWork(db_session))


def to_file_response(file_object: FileObject) -> FileResponse:
    return FileResponse(
        id=file_object.id,
        original_name=file_object.original_name,
        content_type=file_object.content_type,
        size=file_object.size,
        download_url=f"/api/files/{file_object.id}/download",
        created_at=file_object.created_at,
    )


@router.post("", response_model=ApiResponse[FileResponse])
async def upload_file(
    upload: UploadFile = File(...),
    service: FileService = Depends(build_file_service),
) -> ApiResponse[FileResponse]:
    content = await upload.read()
    file_object = await service.save_upload(
        original_name=upload.filename or "",
        content_type=upload.content_type,
        content=content,
    )
    return ApiResponse(data=to_file_response(file_object))


@router.get("/{file_id}", response_model=ApiResponse[FileResponse])
async def get_file(
    file_id: UUID,
    service: FileService = Depends(build_file_service),
) -> ApiResponse[FileResponse]:
    file_object = await service.get_file(file_id)
    return ApiResponse(data=to_file_response(file_object))


@router.get("/{file_id}/download")
async def download_file(
    file_id: UUID,
    service: FileService = Depends(build_file_service),
) -> DownloadFileResponse:
    file_object, path = await service.get_download_path(file_id)
    return DownloadFileResponse(
        path=path,
        media_type=file_object.content_type,
        filename=file_object.original_name,
    )


@router.get("/{file_id}/preview", response_model=ApiResponse[FilePreviewResponse])
async def preview_file(
    file_id: UUID,
    service: FileService = Depends(build_file_service),
) -> ApiResponse[FilePreviewResponse]:
    preview = await service.preview_file(file_id)
    return ApiResponse(
        data=FilePreviewResponse(
            file=to_file_response(preview.file),
            content=preview.content,
            file_type=preview.file_type,
            language=preview.language,
            line_count=preview.line_count,
            parse_status=preview.parse_status,
            parse_message=preview.parse_message,
            references=[
                FileReferenceResponse(
                    label=reference.label,
                    excerpt=reference.excerpt,
                    start_line=reference.start_line,
                    end_line=reference.end_line,
                )
                for reference in preview.references
            ],
            summary=preview.summary,
            truncated=preview.truncated,
        )
    )
