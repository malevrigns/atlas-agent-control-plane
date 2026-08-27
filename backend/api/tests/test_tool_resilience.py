"""工具调用重试与降级（Retry & Fallback）单元测试。

覆盖：退避延迟计算、可重试错误判定（文本 + 异常类型）、
成功前重试（含审计事件）、不可重试错误不重试、重试耗尽抛出/降级、
策略禁用、on_retry 回调、同步版本与装饰器。
所有测试使用极小 backoff（0.001s）保证快速。
"""

import unittest

from app.core.exceptions import AppException, ErrorType
from app.domain.agent_core.tool_resilience import (
    ResilienceOutcome,
    RetryEvent,
    RetryPolicy,
    execute_with_resilience,
    execute_with_resilience_sync,
    is_retryable_error,
    is_retryable_error_text,
    retry_delay,
    with_resilience,
)

# 测试统一使用的小退避策略，避免真实 sleep 拖慢测试。
FAST_POLICY = RetryPolicy(
    enabled=True,
    max_retries=2,
    base_backoff_seconds=0.001,
    backoff_factor=2.0,
)


class RetryDelayTest(unittest.TestCase):
    def test_exponential_growth(self) -> None:
        """延迟按 base * factor^(attempt-1) 递增。"""
        self.assertAlmostEqual(retry_delay(1, base_backoff=1.5, factor=2.0), 1.5)
        self.assertAlmostEqual(retry_delay(2, base_backoff=1.5, factor=2.0), 3.0)
        self.assertAlmostEqual(retry_delay(3, base_backoff=1.5, factor=2.0), 6.0)

    def test_attempt_below_one_clamped(self) -> None:
        """attempt < 1 时按 1 处理（延迟等于 base）。"""
        self.assertAlmostEqual(retry_delay(0, base_backoff=1.5, factor=2.0), 1.5)


class RetryableErrorTextTest(unittest.TestCase):
    def test_network_timeout_keywords_are_retryable(self) -> None:
        """超时/网络类错误文本判定为可重试。"""
        self.assertTrue(is_retryable_error_text("Request timed out after 30s"))
        self.assertTrue(is_retryable_error_text("Connection refused by peer"))
        self.assertTrue(is_retryable_error_text("HTTP 503 Service Unavailable"))
        self.assertTrue(is_retryable_error_text("SSL handshake failed"))

    def test_parameter_errors_are_not_retryable(self) -> None:
        """参数类错误文本不可重试；None 也返回 False。"""
        self.assertFalse(is_retryable_error_text("invalid parameter 'q'"))
        self.assertFalse(is_retryable_error_text("404 Not Found"))
        self.assertFalse(is_retryable_error_text(None))


class RetryableErrorTest(unittest.TestCase):
    def test_exception_types(self) -> None:
        """按异常类型：Timeout/Connection 可重试，参数类不可重试。"""
        self.assertTrue(is_retryable_error(TimeoutError("timed out")))
        self.assertTrue(is_retryable_error(ConnectionError("reset")))
        self.assertFalse(is_retryable_error(ValueError("bad arg")))
        self.assertFalse(is_retryable_error(KeyError("missing")))

    def test_app_exception_by_status(self) -> None:
        """AppException：timeout 类与 5xx/408/429 可重试，4xx 参数类不可重试。"""
        timeout_error = AppException(
            message="tool timeout", code=408, status_code=408,
            error_type=ErrorType.timeout,
        )
        self.assertTrue(is_retryable_error(timeout_error))
        server_error = AppException(
            message="upstream down", code=503, status_code=503,
            error_type=ErrorType.internal,
        )
        self.assertTrue(is_retryable_error(server_error))
        param_error = AppException(
            message="bad param", code=400, status_code=400,
            error_type=ErrorType.validation,
        )
        self.assertFalse(is_retryable_error(param_error))

    def test_generic_exception_falls_back_to_text(self) -> None:
        """未知异常按错误文本关键词兜底判断。"""
        self.assertTrue(is_retryable_error(RuntimeError("network unreachable")))
        self.assertFalse(is_retryable_error(RuntimeError("invalid config")))


class FlakyOperation:
    """前 fail_times 次抛 TimeoutError，之后返回成功值。"""

    def __init__(self, fail_times: int, success_value: str = "ok") -> None:
        self.fail_times = fail_times
        self.success_value = success_value
        self.call_count = 0

    async def __call__(self) -> str:
        self.call_count += 1
        if self.call_count <= self.fail_times:
            raise TimeoutError(f"request timed out (try {self.call_count})")
        return self.success_value


class ExecuteWithResilienceTest(unittest.IsolatedAsyncioTestCase):
    async def test_succeeds_after_retries_with_audit_events(self) -> None:
        """重试两次后成功：attempts=3，审计事件记录每次延迟与错误。"""
        operation = FlakyOperation(fail_times=2)
        outcome = await execute_with_resilience(operation, policy=FAST_POLICY)
        self.assertEqual(outcome.value, "ok")
        self.assertEqual(outcome.attempts, 3)
        self.assertEqual(operation.call_count, 3)
        self.assertFalse(outcome.fell_back)
        self.assertEqual(len(outcome.retry_events), 2)
        self.assertEqual(
            [event.attempt for event in outcome.retry_events], [1, 2]
        )
        # 指数退避：0.001 -> 0.002
        self.assertAlmostEqual(outcome.retry_events[0].delay_seconds, 0.001)
        self.assertAlmostEqual(outcome.retry_events[1].delay_seconds, 0.002)
        self.assertIn("TimeoutError", outcome.retry_events[0].error)

    async def test_non_retryable_error_is_not_retried(self) -> None:
        """参数类错误立即停止（不重试）；提供 fallback 时走降级。"""
        calls = 0

        def bad_operation() -> str:
            nonlocal calls
            calls += 1
            raise ValueError("invalid parameter")

        outcome = await execute_with_resilience(
            bad_operation, policy=FAST_POLICY, fallback=lambda: "degraded"
        )
        self.assertEqual(calls, 1)
        self.assertEqual(outcome.retry_events, [])
        self.assertTrue(outcome.fell_back)
        self.assertEqual(outcome.value, "degraded")

    async def test_retry_exhaustion_raises_without_fallback(self) -> None:
        """重试耗尽且无 fallback：抛出最后一个错误。"""
        operation = FlakyOperation(fail_times=99)
        with self.assertRaises(TimeoutError):
            await execute_with_resilience(operation, policy=FAST_POLICY)
        self.assertEqual(operation.call_count, 3)  # 1 次原始 + 2 次重试

    async def test_retry_exhaustion_uses_fallback(self) -> None:
        """重试耗尽且有 fallback：返回降级结果并标记 fell_back。"""
        operation = FlakyOperation(fail_times=99)
        outcome = await execute_with_resilience(
            operation, policy=FAST_POLICY, fallback=lambda: "fallback-result"
        )
        self.assertTrue(outcome.fell_back)
        self.assertEqual(outcome.value, "fallback-result")
        self.assertEqual(operation.call_count, 3)
        self.assertEqual(len(outcome.retry_events), 2)
        self.assertIn("TimeoutError", outcome.last_error or "")

    async def test_disabled_policy_never_retries(self) -> None:
        """策略禁用时只执行一次，失败直接抛出。"""
        operation = FlakyOperation(fail_times=99)
        disabled = RetryPolicy(enabled=False, max_retries=5)
        with self.assertRaises(TimeoutError):
            await execute_with_resilience(operation, policy=disabled)
        self.assertEqual(operation.call_count, 1)

    async def test_on_retry_callback_receives_events(self) -> None:
        """on_retry 回调按次收到 RetryEvent，可同步或异步。"""
        seen: list[RetryEvent] = []

        async def on_retry(event: RetryEvent) -> None:
            seen.append(event)

        operation = FlakyOperation(fail_times=2)
        await execute_with_resilience(
            operation, policy=FAST_POLICY, on_retry=on_retry
        )
        self.assertEqual([event.attempt for event in seen], [1, 2])

    async def test_outcome_dataclass_fields(self) -> None:
        """ResilienceOutcome 字段默认值正确。"""
        outcome = ResilienceOutcome(value="v", attempts=1)
        self.assertEqual(outcome.retry_events, [])
        self.assertFalse(outcome.fell_back)
        self.assertIsNone(outcome.last_error)


class SyncAndDecoratorTest(unittest.TestCase):
    def test_sync_version_retries_and_succeeds(self) -> None:
        """同步版本：失败后重试并成功。"""
        state = {"calls": 0}

        def flaky_sync() -> str:
            state["calls"] += 1
            if state["calls"] < 2:
                raise TimeoutError("timed out")
            return "done"

        outcome = execute_with_resilience_sync(flaky_sync, policy=FAST_POLICY)
        self.assertEqual(outcome.value, "done")
        self.assertEqual(outcome.attempts, 2)
        self.assertEqual(state["calls"], 2)

    def test_decorator_on_async_function(self) -> None:
        """@with_resilience 装饰异步函数：失败一次后成功，只返回 value。"""

        import asyncio

        state = {"calls": 0}

        @with_resilience(retries=2, backoff=0.001, factor=2.0)
        async def flaky_async(query: str) -> str:
            state["calls"] += 1
            if state["calls"] < 2:
                raise TimeoutError("timed out")
            return f"echo:{query}"

        result = asyncio.run(flaky_async("atlas"))
        self.assertEqual(result, "echo:atlas")
        self.assertEqual(state["calls"], 2)

    def test_decorator_fallback_on_exhaustion(self) -> None:
        """@with_resilience 重试耗尽后返回 fallback 值。"""

        import asyncio

        @with_resilience(retries=1, backoff=0.001, fallback=lambda: "降级")
        async def always_fails() -> str:
            raise TimeoutError("timed out")

        self.assertEqual(asyncio.run(always_fails()), "降级")

    def test_decorator_param_error_not_retried(self) -> None:
        """参数类错误不重试，装饰器直接抛出。"""

        import asyncio

        state = {"calls": 0}

        @with_resilience(retries=3, backoff=0.001)
        async def bad_param(x: int) -> str:
            state["calls"] += 1
            raise ValueError("invalid x")

        with self.assertRaises(ValueError):
            asyncio.run(bad_param(1))
        self.assertEqual(state["calls"], 1)


if __name__ == "__main__":
    unittest.main()
