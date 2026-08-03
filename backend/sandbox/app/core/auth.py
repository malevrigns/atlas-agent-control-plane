import secrets
import hashlib

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.config import Settings


class SandboxApiKeyMiddleware(BaseHTTPMiddleware):
    """Protect every stateful Sandbox endpoint with the control-plane key."""

    def __init__(self, app, *, settings: Settings) -> None:
        super().__init__(app)
        self.enabled = settings.sandbox_auth_enabled
        self.expected_key = settings.atlas_api_key.get_secret_value()
        if self.enabled and self.expected_key in {"", "change-me"}:
            raise RuntimeError("ATLAS_API_KEY is required when SANDBOX_AUTH_ENABLED=true")

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if not self.enabled or request.method == "OPTIONS" or self._is_public(request.url.path):
            return await call_next(request)
        supplied_key = request.headers.get("x-atlas-api-key", "")
        supplied_session = request.cookies.get("atlas_session", "")
        expected_session = hashlib.sha256(
            f"atlas-session:{self.expected_key}".encode("utf-8")
        ).hexdigest()
        key_matches = bool(supplied_key) and secrets.compare_digest(supplied_key, self.expected_key)
        session_matches = bool(supplied_session) and secrets.compare_digest(
            supplied_session,
            expected_session,
        )
        if not key_matches and not session_matches:
            return JSONResponse(
                status_code=401,
                content={"code": 401, "message": "authentication required", "data": None},
                headers={"WWW-Authenticate": "AtlasApiKey"},
            )
        return await call_next(request)

    @staticmethod
    def _is_public(path: str) -> bool:
        return path.rstrip("/") == "/api/status"
