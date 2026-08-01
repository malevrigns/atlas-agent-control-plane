import re
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.request_id import RequestIdMiddleware


class RequestIdMiddlewareTest(unittest.TestCase):
    # ===================== 第1步：没有传入请求 ID 时，服务端应自动生成一个 =====================
    def test_generates_request_id_response_header(self) -> None:
        app = FastAPI()
        app.add_middleware(RequestIdMiddleware)

        @app.get("/ping")
        async def ping():
            return {"ok": True}

        response = TestClient(app).get("/ping")

        self.assertEqual(response.status_code, 200)
        self.assertRegex(
            response.headers["X-Request-ID"],
            re.compile(r"^[0-9a-f-]{36}$"),
        )

    # ===================== 第2步：调用方传入请求 ID 时，应保持同一个 ID 贯穿响应 =====================
    def test_reuses_incoming_request_id(self) -> None:
        app = FastAPI()
        app.add_middleware(RequestIdMiddleware)

        @app.get("/ping")
        async def ping():
            return {"ok": True}

        response = TestClient(app).get(
            "/ping",
            headers={"X-Request-ID": "debug-request-001"},
        )

        self.assertEqual(response.headers["X-Request-ID"], "debug-request-001")


if __name__ == "__main__":
    unittest.main()
