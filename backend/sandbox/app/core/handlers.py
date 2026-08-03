import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.core.exceptions import SandboxException
from app.schemas.common import ApiResponse

logger = logging.getLogger(__name__)


def build_error_response(code: int, message: str, status_code: int) -> JSONResponse:
    payload = ApiResponse[None](code=code, message=message, data=None)
    return JSONResponse(status_code=status_code, content=payload.model_dump())


async def sandbox_exception_handler(
    request: Request,
    exc: SandboxException,
) -> JSONResponse:
    logger.warning("sandbox business error: %s %s", request.url.path, exc.message)
    return build_error_response(
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
    )


async def http_exception_handler(
    request: Request,
    exc: HTTPException,
) -> JSONResponse:
    logger.warning("sandbox http error: %s %s", request.url.path, exc.detail)
    return build_error_response(
        code=exc.status_code,
        message=str(exc.detail),
        status_code=exc.status_code,
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    logger.warning("sandbox validation error: %s %s", request.url.path, exc.errors())
    return build_error_response(
        code=422,
        message="request validation failed",
        status_code=422,
    )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.exception("sandbox unhandled error: %s", request.url.path)
    return build_error_response(
        code=500,
        message="internal server error",
        status_code=500,
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(SandboxException, sandbox_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
