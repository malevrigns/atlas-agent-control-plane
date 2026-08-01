from enum import StrEnum
from socket import timeout as SocketTimeout
from uuid import UUID


class ErrorType(StrEnum):
    validation = "validation_error"
    business = "business_error"
    not_found = "not_found"
    timeout = "timeout"
    dependency = "dependency_error"
    tool = "tool_error"
    internal = "internal_error"


class ErrorSource(StrEnum):
    api = "api"
    agent = "agent"
    dependency = "dependency"
    tool = "tool"
    llm = "llm"
    sandbox = "sandbox"
    mcp = "mcp"
    a2a = "a2a"


class AppException(Exception):
    def __init__(
        self,
        message: str,
        code: int = 400,
        status_code: int = 400,
        *,
        error_type: str | ErrorType | None = None,
        source: str | ErrorSource = ErrorSource.api,
        suggestion: str | None = None,
        details: dict | None = None,
    ) -> None:
        self.message = message
        self.code = code
        self.status_code = status_code
        self.error_type = str(error_type or self._infer_error_type(status_code))
        self.source = str(source)
        self.suggestion = suggestion
        self.details = details or {}
        super().__init__(message)

    @staticmethod
    def _infer_error_type(status_code: int) -> ErrorType:
        if status_code == 404:
            return ErrorType.not_found
        if status_code == 422:
            return ErrorType.validation
        if status_code >= 500:
            return ErrorType.internal
        return ErrorType.business


def classify_exception(error: Exception) -> dict:
    """把 Python 异常转换成前端和日志都能理解的错误摘要。"""

    if isinstance(error, AppException):
        return {
            "error_type": error.error_type,
            "source": error.source,
            "message": error.message,
            "user_message": error.message,
            "suggestion": error.suggestion or build_error_suggestion(error.error_type),
            "retryable": error.status_code >= 500 or error.error_type == ErrorType.timeout,
            "details": error.details,
        }

    error_name = error.__class__.__name__
    error_text = str(error) or error_name
    lowered = error_text.lower()
    if (
        isinstance(error, (TimeoutError, SocketTimeout))
        or "timeout" in lowered
        or "timed out" in lowered
    ):
        error_type = ErrorType.timeout
        source = ErrorSource.dependency
        retryable = True
    elif any(
        keyword in lowered
        for keyword in ["connection", "connect", "502", "bad gateway", "ssl"]
    ):
        error_type = ErrorType.dependency
        source = ErrorSource.dependency
        retryable = True
    elif isinstance(error, ValueError):
        error_type = ErrorType.validation
        source = ErrorSource.api
        retryable = False
    else:
        error_type = ErrorType.internal
        source = ErrorSource.agent
        retryable = False

    return {
        "error_type": str(error_type),
        "source": str(source),
        "message": error_text,
        "user_message": build_user_message(str(error_type), error_text),
        "suggestion": build_error_suggestion(str(error_type)),
        "retryable": retryable,
        "details": {"exception": error_name},
    }


def build_task_error_payload(
    error: Exception,
    *,
    session_id: UUID,
    plan_id: str | None,
    task_id: str | None = None,
    step: dict | None = None,
    step_index: int | None = None,
) -> dict:
    """生成 task_error 事件 payload。

    事件里保留 message，是为了兼容旧前端；同时补充 user_message、
    suggestion、source、retryable 等字段，让新前端可以展示更友好的错误卡片。
    """

    summary = classify_exception(error)
    payload = {
        "kind": "task_error",
        "session_id": str(session_id),
        "task_id": task_id,
        "plan_id": plan_id,
        "message": summary["message"],
        "user_message": summary["user_message"],
        "suggestion": summary["suggestion"],
        "error_type": summary["error_type"],
        "source": summary["source"],
        "retryable": summary["retryable"],
        "details": summary["details"],
    }
    if step is not None:
        payload.update(
            {
                "step_id": step.get("id"),
                "index": step_index,
                "title": step.get("title", ""),
            }
        )
    return payload


def build_user_message(error_type: str, message: str) -> str:
    if error_type == ErrorType.timeout:
        return "外部服务响应超时，本轮任务没有完成。"
    if error_type == ErrorType.dependency:
        return "外部依赖暂时不可用，本轮任务没有完成。"
    if error_type == ErrorType.validation:
        return "请求参数或任务输入不符合要求。"
    return message or "任务执行时发生未知错误。"


def build_error_suggestion(error_type: str) -> str:
    if error_type == ErrorType.timeout:
        return "可以稍后重试，或检查 Sandbox、浏览器、搜索服务和网络连接。"
    if error_type == ErrorType.dependency:
        return "请检查 Nginx、Sandbox、LLM、MCP/A2A 地址和网络连通性。"
    if error_type == ErrorType.validation:
        return "请检查请求参数、会话 ID、文件 ID 或任务内容是否正确。"
    if error_type == ErrorType.not_found:
        return "请确认资源是否存在，或刷新页面后重新选择会话。"
    return "请复制 request_id 或 task_id 查看后端日志，必要时重新执行任务。"
