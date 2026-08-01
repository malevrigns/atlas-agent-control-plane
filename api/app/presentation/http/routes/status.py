from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.infrastructure.database.health import check_database
from app.infrastructure.database.session import get_db_session
from app.schemas.common import ApiResponse
from app.schemas.status import DatabaseStatusData, StatusData

router = APIRouter(prefix="/status", tags=["status"])


@router.get("", response_model=ApiResponse[StatusData])
async def get_status() -> ApiResponse[StatusData]:
    return ApiResponse(
        data=StatusData(
            service=settings.api_app_name,
            environment=settings.api_env,
            status="ok",
            version=settings.api_version,
        )
    )


@router.get("/database", response_model=ApiResponse[DatabaseStatusData])
async def get_database_status(
    db_session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[DatabaseStatusData]:
    is_ready = await check_database(db_session)
    return ApiResponse(data=DatabaseStatusData(status="ok" if is_ready else "error"))
