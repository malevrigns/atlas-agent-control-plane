import unittest
from typing import Any

from app.application.tool_runtime import ToolExecutionContext, ToolRuntime
from app.core.exceptions import AppException
from app.domain.agent_core.tools import (
    ToolInvocationStatus,
    ToolRegistry,
    ToolRiskLevel,
    agent_tool,
)


@agent_tool(
    name="safe_echo",
    description="echo",
    parameter_descriptions={"text": "text"},
    required_permissions=("text:read",),
)
def safe_echo(text: str) -> str:
    return text


@agent_tool(
    name="dangerous",
    description="danger",
    parameter_descriptions={"text": "text"},
    risk_level=ToolRiskLevel.high,
    required_permissions=("shell:execute",),
    idempotent=False,
)
def dangerous(text: str) -> str:
    return text


class PersistentInvocationStore:
    def __init__(self, status: ToolInvocationStatus) -> None:
        self.status = status

    async def get_tool_invocation_by_idempotency(
        self,
        tool_name: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return {
            "id": "persisted-invocation",
            "tool_name": tool_name,
            "idempotency_key": idempotency_key,
            "request_hash": "",
            "status": self.status.value,
            "arguments": {"text": "hello"},
            "output_preview": "persisted output",
            "risk_level": ToolRiskLevel.low.value,
            "duration_ms": 12,
            "artifact_id": None,
        }


class PersistentInvocationUnitOfWork:
    def __init__(self, status: ToolInvocationStatus) -> None:
        self.control_plane = PersistentInvocationStore(status)


class ToolRuntimeTest(unittest.IsolatedAsyncioTestCase):
    def build_runtime(self) -> ToolRuntime:
        registry = ToolRegistry()
        registry.register(safe_echo)
        registry.register(dangerous)
        return ToolRuntime(registry)

    async def test_permissions_are_enforced(self) -> None:
        result = await self.build_runtime().execute(
            "safe_echo",
            {"text": "hello"},
            ToolExecutionContext(),
        )
        self.assertEqual(result.status, ToolInvocationStatus.denied)

    async def test_high_risk_requires_approval(self) -> None:
        result = await self.build_runtime().execute(
            "dangerous",
            {"text": "hello"},
            ToolExecutionContext(allowed_permissions={"shell:execute"}),
        )
        self.assertEqual(result.status, ToolInvocationStatus.approval_required)

    async def test_idempotency_deduplicates_success(self) -> None:
        runtime = self.build_runtime()
        context = ToolExecutionContext(
            allowed_permissions={"text:read"},
            idempotency_key="same",
        )
        first = await runtime.execute("safe_echo", {"text": "hello"}, context)
        second = await runtime.execute("safe_echo", {"text": "hello"}, context)
        self.assertEqual(first.status, ToolInvocationStatus.succeeded)
        self.assertEqual(second.status, ToolInvocationStatus.deduplicated)

    async def test_idempotency_key_rejects_different_arguments(self) -> None:
        runtime = self.build_runtime()
        context = ToolExecutionContext(
            allowed_permissions={"text:read"},
            idempotency_key="same",
        )
        await runtime.execute("safe_echo", {"text": "first"}, context)
        with self.assertRaises(AppException) as raised:
            await runtime.execute("safe_echo", {"text": "second"}, context)
        self.assertEqual(raised.exception.status_code, 409)

    async def test_persistent_idempotency_preserves_non_success_status(self) -> None:
        expected_statuses = (
            ToolInvocationStatus.denied,
            ToolInvocationStatus.failed,
            ToolInvocationStatus.timed_out,
            ToolInvocationStatus.approval_required,
        )
        for expected_status in expected_statuses:
            with self.subTest(status=expected_status):
                registry = ToolRegistry()
                registry.register(safe_echo)
                runtime = ToolRuntime(
                    registry,
                    uow=PersistentInvocationUnitOfWork(expected_status),  # type: ignore[arg-type]
                )
                result = await runtime.execute(
                    "safe_echo",
                    {"text": "hello"},
                    ToolExecutionContext(
                        allowed_permissions={"text:read"},
                        idempotency_key="persisted-key",
                    ),
                )
                self.assertEqual(result.status, expected_status)
                self.assertNotEqual(result.status, ToolInvocationStatus.deduplicated)


if __name__ == "__main__":
    unittest.main()
