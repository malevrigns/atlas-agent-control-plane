import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.core.exceptions import (
    AppException,
    ErrorSource,
    ErrorType,
    build_error_suggestion,
)
from app.schemas.common import ApiError, ApiResponse

logger = logging.getLogger(__name__)


def get_request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def build_error_response(
    *,
    code: int,
    message: str,
    status_code: int,
    request: Request,
    error_type: str,
    source: str,
    suggestion: str | None = None,
    details: dict | None = None,
) -> JSONResponse:
    payload = ApiResponse[None](
        code=code,
        message=message,
        data=None,
        error=ApiError(
            type=error_type,
            source=source,
            user_message=message,
            suggestion=suggestion or build_error_suggestion(error_type),
            request_id=get_request_id(request),
            details=details,
        ),
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump())


async def app_exception_handler(
    request: Request,
    exc: AppException,
) -> JSONResponse:
    logger.warning(
        "business error: path=%s request_id=%s type=%s message=%s",
        request.url.path,
        get_request_id(request),
        exc.error_type,
        exc.message,
    )
    return build_error_response(
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        request=request,
        error_type=exc.error_type,
        source=exc.source,
        suggestion=exc.suggestion,
        details=exc.details,
    )


async def http_exception_handler(
    request: Request,
    exc: HTTPException,
) -> JSONResponse:
    logger.warning(
        "http error: path=%s request_id=%s detail=%s",
        request.url.path,
        get_request_id(request),
        exc.detail,
    )
    return build_error_response(
        code=exc.status_code,
        message=str(exc.detail),
        status_code=exc.status_code,
        request=request,
        error_type=str(ErrorType.not_found if exc.status_code == 404 else ErrorType.business),
        source=str(ErrorSource.api),
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    logger.warning(
        "validation error: path=%s request_id=%s errors=%s",
        request.url.path,
        get_request_id(request),
        exc.errors(),
    )
    return build_error_response(
        code=422,
        message="request validation failed",
        status_code=422,
        request=request,
        error_type=str(ErrorType.validation),
        source=str(ErrorSource.api),
        suggestion="请检查请求体、路径参数和查询参数是否符合接口要求。",
        details={"errors": exc.errors()},
    )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.exception(
        "unhandled error: path=%s request_id=%s",
        request.url.path,
        get_request_id(request),
    )
    return build_error_response(
        code=500,
        message="internal server error",
        status_code=500,
        request=request,
        error_type=str(ErrorType.internal),
        source=str(ErrorSource.api),
        suggestion="请复制 request_id 查看后端日志，或稍后重试。",
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
