import secrets

from fastapi import APIRouter, Header, Response

from app.core.auth import api_session_token
from app.core.config import settings
from app.core.exceptions import AppException
from app.schemas.common import ApiResponse


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/session", response_model=ApiResponse[dict[str, bool]])
async def create_auth_session(
    response: Response,
    x_atlas_api_key: str = Header(default=""),
) -> ApiResponse[dict[str, bool]]:
    """Exchange the operator key for an HttpOnly, same-site browser session."""

    expected = settings.atlas_api_key.get_secret_value()
    if settings.api_auth_enabled and (
        not expected or not secrets.compare_digest(x_atlas_api_key, expected)
    ):
        raise AppException(message="invalid API key", code=401, status_code=401)
    if settings.api_auth_enabled:
        response.set_cookie(
            key="atlas_session",
            value=api_session_token(expected),
            httponly=True,
            secure=settings.api_env == "production",
            samesite="strict",
            max_age=8 * 60 * 60,
            path="/",
        )
    return ApiResponse(data={"authenticated": True})


@router.delete("/session", response_model=ApiResponse[dict[str, bool]])
async def delete_auth_session(response: Response) -> ApiResponse[dict[str, bool]]:
    response.delete_cookie("atlas_session", path="/")
    return ApiResponse(data={"authenticated": False})


@router.get("/check", status_code=204, response_class=Response)
async def check_auth_session() -> Response:
    """Nginx auth_request target for WebSocket and static proxy locations."""

    return Response(status_code=204)
