import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.auth import ApiKeyMiddleware, api_session_token
from app.core.config import Settings


class ApiKeyMiddlewareTest(unittest.TestCase):
    def setUp(self) -> None:
        app = FastAPI()
        app.add_middleware(
            ApiKeyMiddleware,
            settings=Settings(api_auth_enabled=True, atlas_api_key="test-secret"),
        )

        @app.get("/api/status")
        async def status() -> dict:
            return {"ok": True}

        @app.get("/api/private")
        async def private() -> dict:
            return {"ok": True}

        self.client = TestClient(app)

    def test_public_health_does_not_require_key(self) -> None:
        self.assertEqual(self.client.get("/api/status").status_code, 200)

    def test_private_route_rejects_missing_key(self) -> None:
        response = self.client.get("/api/private")
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("test-secret", response.text)

    def test_header_and_http_only_session_token_are_accepted(self) -> None:
        header_response = self.client.get(
            "/api/private",
            headers={"X-Atlas-API-Key": "test-secret"},
        )
        cookie_response = self.client.get(
            "/api/private",
            cookies={"atlas_session": api_session_token("test-secret")},
        )
        self.assertEqual(header_response.status_code, 200)
        self.assertEqual(cookie_response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
