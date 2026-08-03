from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import AppException


class SandboxFileClient:
    """主 API 访问 Sandbox 文件接口的同步客户端。"""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
    ) -> None:
        # base_url 指向 Sandbox 内部 API，例如 http://sandbox:8100/api。
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.headers = self._auth_headers()

    # ===================== 第1步：封装文件列表 =====================
    def list_files(self, path: str = ".") -> dict[str, Any]:
        return self._request("GET", "/files", params={"path": path})

    # ===================== 第2步：封装文件读取 =====================
    def read_file(self, path: str) -> dict[str, Any]:
        return self._request("GET", "/files/read", params={"path": path})

    # ===================== 第3步：封装文件写入 =====================
    def write_file(
        self,
        path: str,
        content: str,
        create_parent: bool = True,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/files/write",
            json={
                "path": path,
                "content": content,
                "create_parent": create_parent,
            },
        )

    # ===================== 第4步：封装文本替换 =====================
    def replace_text(
        self,
        path: str,
        old_text: str,
        new_text: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/files/replace",
            json={
                "path": path,
                "old_text": old_text,
                "new_text": new_text,
            },
        )

    # ===================== 第5步：封装文件删除 =====================
    def delete_path(self, path: str) -> dict[str, Any]:
        return self._request("DELETE", "/files", params={"path": path})

    # ===================== 第6步：统一处理 Sandbox 响应 =====================
    def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            # Sandbox 是 Docker Compose 内部服务，必须直连服务名 sandbox。
            # trust_env=False 可以避免代理环境变量把内部请求错误转发到外部代理。
            with httpx.Client(timeout=self.timeout_seconds, trust_env=False) as client:
                response = client.request(method, url, headers=self.headers, **kwargs)
        except httpx.HTTPError as error:
            raise AppException(
                message=f"sandbox request failed: {error}",
                code=502,
                status_code=502,
            ) from error

        try:
            payload = response.json()
        except ValueError as error:
            raise AppException(
                message="sandbox returned non-json response",
                code=502,
                status_code=502,
            ) from error

        if response.status_code >= 400 or payload.get("code") != 200:
            raise AppException(
                message=str(payload.get("message") or "sandbox request failed"),
                code=int(payload.get("code") or response.status_code),
                status_code=response.status_code,
            )

        data = payload.get("data")
        if not isinstance(data, dict):
            raise AppException(
                message="sandbox returned invalid data",
                code=502,
                status_code=502,
            )
        return data

    @staticmethod
    def _auth_headers() -> dict[str, str]:
        key = settings.atlas_api_key.get_secret_value()
        return {"X-Atlas-API-Key": key} if key else {}
