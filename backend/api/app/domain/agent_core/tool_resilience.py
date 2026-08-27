"""工具调用重试与降级（Retry & Fallback）。

提供三层能力：
- is_retryable_error / is_retryable_error_text：错误可重试性判定。
  只对超时 / 网络类错误重试；参数类错误（4xx AppException、ValueError 等）
  重试也不会成功，直接失败。
- execute_with_resilience / with_resilience：指数退避重试执行器。
  每次重试记录 RetryEvent（延迟、错误摘要），供 ToolRuntime 写入审计。
- RetryPolicy：可注入的重试策略（由 app/core/config.py 的 tool_* 配置驱动）。

降级（fallback）：重试耗尽后若提供 fallback 可调用对象，则调用它产出
降级结果并标记 fell_back；未提供则抛出最后一个错误，由上层决定
是否切换到 AgentTool.fallback_tool 声明的替代工具。
"""

import asyncio
import functools
import inspect
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar
from time import sleep as sync_sleep

from app.core.exceptions import AppException, ErrorType

T = TypeVar("T")

# 错误文本里出现这些关键词时按网络/超时类错误处理（可重试）。
_RETRYABLE_ERROR_KEYWORDS = (
    "timeout",
    "timed out",
    "connection",
    "connect",
    "network",
    "unreachable",
    "bad gateway",
    "service unavailable",
    "502",
    "503",
    "ssl",
)


def is_retryable_error_text(text: str | None) -> bool:
    """按错误文本判断是否为超时/网络类错误（纯函数，便于测试）。"""

    lowered = (text or "").lower()
    return any(keyword in lowered for keyword in _RETRYABLE_ERROR_KEYWORDS)


def is_retryable_error(error: BaseException) -> bool:
    """判断一次工具执行错误是否值得重试。

    规则：
    - AppException：timeout 类或 5xx / 408 / 429 可重试；4xx 参数类不重试；
    - ValueError / KeyError / TypeError：参数类错误，永不重试；
    - TimeoutError / ConnectionError / socket.timeout：可重试；
    - 其余异常按错误文本关键词兜底判断。
    """

    if isinstance(error, AppException):
        if error.error_type == ErrorType.timeout:
            return True
        if error.status_code in (408, 429) or error.status_code >= 500:
            return True
        return False
    if isinstance(error, (ValueError, KeyError, TypeError)):
        return False
    if isinstance(error, (TimeoutError, ConnectionError, socket.timeout)):
        return True
    return is_retryable_error_text(str(error))


def retry_delay(attempt: int, *, base_backoff: float, factor: float) -> float:
    """第 attempt 次重试（从 1 计）前的退避秒数：base * factor^(attempt-1)。"""

    return base_backoff * (factor ** max(0, attempt - 1))


@dataclass(slots=True)
class RetryEvent:
    """一次重试的审计记录。"""

    attempt: int
    delay_seconds: float
    error: str


@dataclass(slots=True)
class ResilienceOutcome:
    """弹性执行的统一结果。

    value 是操作返回值或 fallback 返回值；
    fell_back 为 True 表示最终结果来自降级路径。
    """

    value: Any
    attempts: int
    retry_events: list[RetryEvent] = field(default_factory=list)
    fell_back: bool = False
    last_error: str | None = None


@dataclass(slots=True)
class RetryPolicy:
    """重试策略（由配置注入，默认值与 app/core/config.py 对齐）。"""

    enabled: bool = True
    max_retries: int = 2
    base_backoff_seconds: float = 1.5
    backoff_factor: float = 2.0


def _as_audit_text(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}"


def _fire_on_retry(on_retry: Callable[[RetryEvent], Any] | None, event: RetryEvent) -> Any:
    if on_retry is None:
        return None
    fired = on_retry(event)
    # on_retry 允许是协程函数；同步回调直接返回值。
    return fired


async def execute_with_resilience(
    operation: Callable[[], T] | Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy | None = None,
    retryable: Callable[[BaseException], bool] = is_retryable_error,
    on_retry: Callable[[RetryEvent], Any] | None = None,
    fallback: Callable[[], T] | Callable[[], Awaitable[T]] | None = None,
) -> ResilienceOutcome:
    """带指数退避重试执行零参操作（同步或异步均可）。

    - 只有 retryable(error) 为真的错误会重试；参数类错误立即抛出；
    - 重试耗尽后：提供 fallback 时调用 fallback() 产出降级结果
      （fell_back=True）；未提供则重新抛出最后一个错误；
    - 每次重试前回调 on_retry(RetryEvent)，并记录进 retry_events 供审计。
    """

    effective_policy = policy or RetryPolicy()
    max_attempts = 1 + max(0, effective_policy.max_retries) if effective_policy.enabled else 1
    retry_events: list[RetryEvent] = []
    last_error: BaseException | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            value = operation()
            if inspect.isawaitable(value):
                value = await value
            return ResilienceOutcome(value=value, attempts=attempt, retry_events=retry_events)
        except Exception as error:  # noqa: BLE001 - 统一兜底，按类型决定是否重试
            last_error = error
            if attempt >= max_attempts or not retryable(error):
                break
            delay = retry_delay(
                attempt,
                base_backoff=effective_policy.base_backoff_seconds,
                factor=effective_policy.backoff_factor,
            )
            event = RetryEvent(attempt=attempt, delay_seconds=delay, error=_as_audit_text(error))
            retry_events.append(event)
            hook_result = _fire_on_retry(on_retry, event)
            if inspect.isawaitable(hook_result):
                await hook_result
            await asyncio.sleep(delay)

    # 重试耗尽：降级或抛出。
    if fallback is not None:
        value = fallback()
        if inspect.isawaitable(value):
            value = await value
        return ResilienceOutcome(
            value=value,
            attempts=max_attempts,
            retry_events=retry_events,
            fell_back=True,
            last_error=_as_audit_text(last_error) if last_error is not None else None,
        )
    assert last_error is not None
    raise last_error


def execute_with_resilience_sync(
    operation: Callable[[], T],
    *,
    policy: RetryPolicy | None = None,
    retryable: Callable[[BaseException], bool] = is_retryable_error,
    on_retry: Callable[[RetryEvent], Any] | None = None,
    fallback: Callable[[], T] | None = None,
) -> ResilienceOutcome:
    """execute_with_resilience 的同步版本（退避用 time.sleep）。"""

    effective_policy = policy or RetryPolicy()
    max_attempts = 1 + max(0, effective_policy.max_retries) if effective_policy.enabled else 1
    retry_events: list[RetryEvent] = []
    last_error: BaseException | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            return ResilienceOutcome(value=operation(), attempts=attempt, retry_events=retry_events)
        except Exception as error:  # noqa: BLE001 - 同异步版本的统一兜底
            last_error = error
            if attempt >= max_attempts or not retryable(error):
                break
            delay = retry_delay(
                attempt,
                base_backoff=effective_policy.base_backoff_seconds,
                factor=effective_policy.backoff_factor,
            )
            event = RetryEvent(attempt=attempt, delay_seconds=delay, error=_as_audit_text(error))
            retry_events.append(event)
            _fire_on_retry(on_retry, event)
            sync_sleep(delay)

    if fallback is not None:
        return ResilienceOutcome(
            value=fallback(),
            attempts=max_attempts,
            retry_events=retry_events,
            fell_back=True,
            last_error=_as_audit_text(last_error) if last_error is not None else None,
        )
    assert last_error is not None
    raise last_error


def with_resilience(
    retries: int = 2,
    backoff: float = 1.5,
    factor: float = 2.0,
    *,
    fallback: Callable[..., Any] | None = None,
    on_retry: Callable[[RetryEvent], Any] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """装饰器：给同步/异步函数加上指数退避重试与降级能力。

    用法::

        @with_resilience(retries=2, backoff=1.5, fallback=lambda: "降级结果")
        async def call_remote(query: str) -> str: ...

    - backoff 是首次重试前的基础延迟（秒），之后按 factor 指数放大；
    - fallback 是零参可调用对象（通常用 lambda 捕获所需上下文），
      重试耗尽后调用并返回其结果；
    - 参数类错误（ValueError 等）不重试，直接抛出。
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        policy = RetryPolicy(
            max_retries=retries,
            base_backoff_seconds=backoff,
            backoff_factor=factor,
        )

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                outcome = await execute_with_resilience(
                    lambda: func(*args, **kwargs),
                    policy=policy,
                    on_retry=on_retry,
                    fallback=fallback,
                )
                return outcome.value

            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            outcome = execute_with_resilience_sync(
                lambda: func(*args, **kwargs),
                policy=policy,
                on_retry=on_retry,
                fallback=fallback,
            )
            return outcome.value

        return sync_wrapper

    return decorator
