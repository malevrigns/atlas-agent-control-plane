from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import AppException


class SandboxShellClient:
    """主 API 访问 Sandbox Shell 接口的同步客户端。"""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
    ) -> None:
        # base_url 指向 Sandbox 服务地址，例如 http://sandbox:8100/api。
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.headers = self._auth_headers()

    # ===================== 第1步：启动 Shell 会话 =====================
    def execute(
        self,
        command: str,
        cwd: str = ".",
        workspace: str = "",
        full_access: bool = False,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/shell/sessions",
            params={"workspace": workspace, "full_access": "true" if full_access else "false"},
            json={"command": command, "cwd": cwd},
        )

    # ===================== 第2步：等待 Shell 会话完成 =====================
    def wait(
        self,
        session_id: str,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/shell/sessions/{session_id}/wait",
            json={"timeout_seconds": timeout_seconds},
        )

    # ===================== 第3步：查询和控制 Shell 会话 =====================
    def get(self, session_id: str) -> dict[str, Any]:
        return self._request("GET", f"/shell/sessions/{session_id}")

    def write(self, session_id: str, value: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/shell/sessions/{session_id}/write",
            json={"input": value},
        )

    def terminate(self, session_id: str) -> dict[str, Any]:
        return self._request("POST", f"/shell/sessions/{session_id}/terminate")

    # ===================== 第4步：统一处理 Sandbox 响应 =====================
    def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            # Shell 工具需要访问 Docker 网络内的 sandbox 服务，不能走宿主机代理。
            with httpx.Client(timeout=self.timeout_seconds, trust_env=False) as client:
                response = client.request(method, url, headers=self.headers, **kwargs)
        except httpx.HTTPError as error:
            raise AppException(
                message=f"sandbox shell request failed: {error}",
                code=502,
                status_code=502,
            ) from error

        try:
            payload = response.json()
        except ValueError as error:
            raise AppException(
                message="sandbox shell returned non-json response",
                code=502,
                status_code=502,
            ) from error

        if response.status_code >= 400 or payload.get("code") != 200:
            raise AppException(
                message=str(payload.get("message") or "sandbox shell request failed"),
                code=int(payload.get("code") or response.status_code),
                status_code=response.status_code,
            )

        data = payload.get("data")
        if not isinstance(data, dict):
            raise AppException(
                message="sandbox shell returned invalid data",
                code=502,
                status_code=502,
            )
        return data

    @staticmethod
    def _auth_headers() -> dict[str, str]:
        key = settings.atlas_api_key.get_secret_value()
        return {"X-Atlas-API-Key": key} if key else {}
