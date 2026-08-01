import logging
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIdMiddleware(BaseHTTPMiddleware):
    """为每个 HTTP 请求补充可追踪的 request id。

    调试线上问题时，用户通常只知道“页面报错了”。请求 ID 可以把浏览器响应、
    Nginx 日志、API 日志和后端异常串起来，减少排查时的猜测成本。
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # ===================== 第1步：读取调用方传入的请求 ID，或生成一个新的 =====================
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid4())
        request.state.request_id = request_id

        # ===================== 第2步：继续处理请求 =====================
        response = await call_next(request)

        # ===================== 第3步：把请求 ID 放回响应头，方便前端和 curl 排查 =====================
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.debug(
            "request completed: method=%s path=%s request_id=%s status=%s",
            request.method,
            request.url.path,
            request_id,
            response.status_code,
        )
        return response
