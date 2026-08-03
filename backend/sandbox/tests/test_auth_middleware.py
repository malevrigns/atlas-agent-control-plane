import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.auth import SandboxApiKeyMiddleware
from app.core.config import Settings


class SandboxApiKeyMiddlewareTest(unittest.TestCase):
    def test_shell_route_requires_key_but_health_is_public(self) -> None:
        app = FastAPI()
        app.add_middleware(
            SandboxApiKeyMiddleware,
            settings=Settings(sandbox_auth_enabled=True, atlas_api_key="sandbox-secret"),
        )

        @app.get("/api/status")
        async def status() -> dict:
            return {"ok": True}

        @app.post("/api/shell/sessions")
        async def shell() -> dict:
            return {"ok": True}

        client = TestClient(app)
        self.assertEqual(client.get("/api/status").status_code, 200)
        self.assertEqual(client.post("/api/shell/sessions").status_code, 401)
        self.assertEqual(
            client.post(
                "/api/shell/sessions",
                headers={"X-Atlas-API-Key": "sandbox-secret"},
            ).status_code,
            200,
        )


if __name__ == "__main__":
    unittest.main()
