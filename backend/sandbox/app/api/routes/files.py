from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse

from app.core.config import settings
from app.schemas.common import ApiResponse
from app.schemas.files import (
    FileDeleteResponse,
    FileListResponse,
    FileReadResponse,
    FileReplaceRequest,
    FileReplaceResponse,
    FileUploadResponse,
    FileWriteRequest,
    FileWriteResponse,
)
from app.services.file_service import SandboxFileService

router = APIRouter(prefix="/files", tags=["files"])


def build_file_service() -> SandboxFileService:
    # 文件服务只依赖配置，后续如果接入权限或审计，可以从这里统一扩展。
    return SandboxFileService(settings=settings)


@router.get("", response_model=ApiResponse[FileListResponse])
async def list_files(
    path: str = Query(default="."),
    workspace: str = Query(default=""),
    full_access: bool = Query(default=False),
    service: SandboxFileService = Depends(build_file_service),
) -> ApiResponse[FileListResponse]:
    return ApiResponse(data=service.list_files(path, workspace, full_access))


@router.get("/read", response_model=ApiResponse[FileReadResponse])
async def read_file(
    path: str = Query(min_length=1),
    workspace: str = Query(default=""),
    full_access: bool = Query(default=False),
    service: SandboxFileService = Depends(build_file_service),
) -> ApiResponse[FileReadResponse]:
    return ApiResponse(data=service.read_file(path, workspace, full_access))


@router.post("/write", response_model=ApiResponse[FileWriteResponse])
async def write_file(
    payload: FileWriteRequest,
    workspace: str = Query(default=""),
    full_access: bool = Query(default=False),
    service: SandboxFileService = Depends(build_file_service),
) -> ApiResponse[FileWriteResponse]:
    return ApiResponse(
        data=service.write_file(
            path=payload.path,
            content=payload.content,
            create_parent=payload.create_parent,
            workspace=workspace,
            full_access=full_access,
        )
    )


@router.post("/replace", response_model=ApiResponse[FileReplaceResponse])
async def replace_text(
    payload: FileReplaceRequest,
    workspace: str = Query(default=""),
    full_access: bool = Query(default=False),
    service: SandboxFileService = Depends(build_file_service),
) -> ApiResponse[FileReplaceResponse]:
    return ApiResponse(
        data=service.replace_text(
            path=payload.path,
            old_text=payload.old_text,
            new_text=payload.new_text,
            workspace=workspace,
            full_access=full_access,
        )
    )


@router.delete("", response_model=ApiResponse[FileDeleteResponse])
async def delete_path(
    path: str = Query(min_length=1),
    workspace: str = Query(default=""),
    full_access: bool = Query(default=False),
    service: SandboxFileService = Depends(build_file_service),
) -> ApiResponse[FileDeleteResponse]:
    return ApiResponse(data=service.delete_path(path, workspace, full_access))


@router.post("/upload", response_model=ApiResponse[FileUploadResponse])
async def upload_file(
    path: str = Query(default="."),
    upload: UploadFile = File(...),
    service: SandboxFileService = Depends(build_file_service),
) -> ApiResponse[FileUploadResponse]:
    return ApiResponse(data=await service.save_upload(path, upload))


@router.get("/download")
async def download_file(
    path: str = Query(min_length=1),
    workspace: str = Query(default=""),
    full_access: bool = Query(default=False),
    service: SandboxFileService = Depends(build_file_service),
) -> FileResponse:
    target = service.get_download_path(path, workspace, full_access)
    return FileResponse(path=target, filename=target.name)
