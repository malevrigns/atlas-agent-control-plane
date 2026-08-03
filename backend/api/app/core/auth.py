import secrets
import hashlib

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.config import Settings


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Require a shared API key without logging or reflecting the secret."""

    def __init__(self, app, *, settings: Settings) -> None:
        super().__init__(app)
        self.enabled = settings.api_auth_enabled
        self.expected_key = settings.atlas_api_key.get_secret_value()
        if self.enabled and self.expected_key in {"", "change-me"}:
            raise RuntimeError("ATLAS_API_KEY is required when API_AUTH_ENABLED=true")

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if not self.enabled or request.method == "OPTIONS" or self._is_public(request.url.path):
            return await call_next(request)

        supplied_key = request.headers.get("x-atlas-api-key", "")
        supplied_session = request.cookies.get("atlas_session", "")
        key_matches = bool(supplied_key) and secrets.compare_digest(supplied_key, self.expected_key)
        session_matches = bool(supplied_session) and secrets.compare_digest(
            supplied_session,
            api_session_token(self.expected_key),
        )
        if not key_matches and not session_matches:
            return JSONResponse(
                status_code=401,
                content={
                    "code": 401,
                    "message": "authentication required",
                    "data": None,
                },
                headers={"WWW-Authenticate": "AtlasApiKey"},
            )
        return await call_next(request)

    @staticmethod
    def _is_public(path: str) -> bool:
        return path.rstrip("/") in {"/api/status", "/api/auth/session"}


def api_session_token(api_key: str) -> str:
    return hashlib.sha256(f"atlas-session:{api_key}".encode("utf-8")).hexdigest()
