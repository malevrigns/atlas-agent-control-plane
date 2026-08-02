import json
from collections.abc import AsyncIterator
from typing import Any

import httpx


class AtlasApiError(RuntimeError):
    pass


def unwrap(payload: dict[str, Any]) -> Any:
    if "data" in payload:
        return payload["data"]
    if payload.get("error"):
        error = payload["error"]
        if isinstance(error, dict):
            raise AtlasApiError(str(error.get("message") or error))
        raise AtlasApiError(str(error))
    return payload


class AtlasApiClient:
    def __init__(self, base_url: str, timeout: float = 10.0, api_key: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = {"X-Atlas-API-Key": api_key} if api_key else {}

    async def get(self, path: str) -> Any:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}{path}", headers=self.headers)
            response.raise_for_status()
            return unwrap(response.json())

    async def post(self, path: str, payload: dict[str, Any]) -> Any:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}{path}",
                json=payload,
                headers=self.headers,
            )
            response.raise_for_status()
            return unwrap(response.json())

    async def status(self) -> dict[str, Any]:
        return await self.get("/api/status")

    async def sessions(self) -> list[dict[str, Any]]:
        data = await self.get("/api/sessions")
        return list(data.get("items", []))

    async def tasks(self, project_id: str = "default") -> list[dict[str, Any]]:
        data = await self.get(f"/api/control-plane/tasks?project_id={project_id}")
        return list(data.get("items", []))

    async def checkpoints(self, task_id: str) -> list[dict[str, Any]]:
        data = await self.get(f"/api/control-plane/tasks/{task_id}/checkpoints")
        return list(data.get("items", []))

    async def tool_invocations(self, project_id: str = "default") -> list[dict[str, Any]]:
        data = await self.get(f"/api/control-plane/tool-invocations?project_id={project_id}&limit=50")
        return list(data.get("items", []))

    async def create_session(self, title: str) -> dict[str, Any]:
        return await self.post("/api/sessions", {"title": title})

    async def stream_message(
        self,
        session_id: str,
        content: str,
    ) -> AsyncIterator[dict[str, Any]]:
        url = f"{self.base_url}/api/sessions/{session_id}/messages/stream"
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                url,
                json={"content": content},
                headers=self.headers,
            ) as response:
                response.raise_for_status()
                event_name = "message"
                async for line in response.aiter_lines():
                    if line.startswith("event:"):
                        event_name = line.removeprefix("event:").strip()
                    elif line.startswith("data:"):
                        raw = line.removeprefix("data:").strip()
                        try:
                            data = json.loads(raw)
                        except json.JSONDecodeError:
                            data = {"raw": raw}
                        yield {"event": event_name, "data": data}
                        event_name = "message"
