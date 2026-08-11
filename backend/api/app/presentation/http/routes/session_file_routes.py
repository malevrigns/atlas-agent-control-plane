from uuid import UUID

from fastapi import APIRouter, Depends, File, Response, UploadFile

from app.application.file_service import FileService
from app.application.session_service import SessionService
from app.presentation.http.routes.session_route_dependencies import (
    build_file_service,
    build_session_service,
)
from app.presentation.http.routes.session_route_responses import (
    to_session_file_response,
)
from app.schemas.common import ApiResponse
from app.schemas.file import SessionFileListResponse, SessionFileResponse

router = APIRouter()


@router.post(
    "/{session_id}/files",
    response_model=ApiResponse[SessionFileResponse],
)
async def upload_session_file(
    session_id: UUID,
    upload: UploadFile = File(...),
    service: FileService = Depends(build_file_service),
) -> ApiResponse[SessionFileResponse]:
    content = await upload.read()
    session_file = await service.save_session_upload(
        session_id=session_id,
        original_name=upload.filename or "",
        content_type=upload.content_type,
        content=content,
    )
    return ApiResponse(data=to_session_file_response(session_file))


@router.get(
    "/{session_id}/files",
    response_model=ApiResponse[SessionFileListResponse],
)
async def list_session_files(
    session_id: UUID,
    service: FileService = Depends(build_file_service),
) -> ApiResponse[SessionFileListResponse]:
    files = await service.list_session_files(session_id)
    items = [to_session_file_response(file) for file in files]
    return ApiResponse(data=SessionFileListResponse(items=items))


@router.delete("/{session_id}", status_code=204)
async def delete_session(
    session_id: UUID,
    service: SessionService = Depends(build_session_service),
) -> Response:
    await service.delete_session(session_id)
    return Response(status_code=204)
