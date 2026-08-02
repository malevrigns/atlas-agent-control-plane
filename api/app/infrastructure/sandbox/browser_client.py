from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import AppException


class SandboxBrowserClient:
    """主 API 访问 Sandbox Browser API 的同步客户端。

    BrowserTool 不直接依赖 Playwright，只通过这个 client 调用 Sandbox。
    这样浏览器进程仍然被限制在隔离容器里。
    """

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.headers = self._auth_headers()

    # ===================== 第1步：浏览器会话状态和生命周期 =====================
    def status(self) -> dict[str, Any]:
        return self._request("GET", "/browser/status")

    def start(self) -> dict[str, Any]:
        return self._request("POST", "/browser/session")

    def close(self) -> dict[str, Any]:
        return self._request("DELETE", "/browser/session")

    # ===================== 第2步：页面操作 =====================
    def navigate(self, url: str, wait_until: str = "domcontentloaded") -> dict[str, Any]:
        return self._request(
            "POST",
            "/browser/page/navigate",
            json={"url": url, "wait_until": wait_until},
        )

    def page_info(self) -> dict[str, Any]:
        return self._request("GET", "/browser/page")

    def screenshot(self, full_page: bool = True) -> dict[str, Any]:
        return self._request(
            "POST",
            "/browser/page/screenshot",
            json={"full_page": full_page},
        )

    # ===================== 第3步：统一处理 Sandbox 响应 =====================
    def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            # Sandbox 是 Docker Compose 内部服务，必须直连服务名 sandbox。
            # trust_env=False 可以避免本机或容器里的 HTTP_PROXY/ALL_PROXY 影响内部请求。
            with httpx.Client(timeout=self.timeout_seconds, trust_env=False) as client:
                response = client.request(method, url, headers=self.headers, **kwargs)
        except httpx.HTTPError as error:
            raise AppException(
                message=f"sandbox browser request failed: {error}",
                code=502,
                status_code=502,
            ) from error

        try:
            payload = response.json()
        except ValueError as error:
            raise AppException(
                message="sandbox browser returned non-json response",
                code=502,
                status_code=502,
            ) from error

        if response.status_code >= 400 or payload.get("code") != 200:
            raise AppException(
                message=str(payload.get("message") or "sandbox browser request failed"),
                code=int(payload.get("code") or response.status_code),
                status_code=response.status_code,
            )

        data = payload.get("data")
        if not isinstance(data, dict):
            raise AppException(
                message="sandbox browser returned invalid data",
                code=502,
                status_code=502,
            )
        return data

    @staticmethod
    def _auth_headers() -> dict[str, str]:
        key = settings.atlas_api_key.get_secret_value()
        return {"X-Atlas-API-Key": key} if key else {}
