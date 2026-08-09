import asyncio
import unittest

from app.application.tool_runtime import ToolExecutionContext, ToolRuntime
from app.domain.agent_core.tools import (
    AgentTool,
    ToolDefinition,
    ToolInvocationStatus,
    ToolParameter,
    ToolRegistry,
)


def build_runtime() -> ToolRuntime:
    registry = ToolRegistry()

    async def async_echo(text: str) -> str:
        await asyncio.sleep(0)
        return f"async:{text}"

    async def async_slow(text: str) -> str:
        await asyncio.sleep(1.0)
        return text

    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="async_echo",
                description="异步回声工具",
                parameters=[ToolParameter(name="text", type="string", description="")],
            ),
            handler=async_echo,
        )
    )
    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="async_slow",
                description="超时验证工具",
                timeout_seconds=0.1,
                parameters=[ToolParameter(name="text", type="string", description="")],
            ),
            handler=async_slow,
        )
    )
    return ToolRuntime(registry)


class ToolRuntimeAsyncHandlerTests(unittest.TestCase):
    """ToolRuntime 必须原生支持异步 handler（knowledge_search 依赖此能力）。"""

    def test_async_handler_is_awaited_directly(self) -> None:
        runtime = build_runtime()
        result = asyncio.run(
            runtime.execute("async_echo", {"text": "rag"}, ToolExecutionContext())
        )
        self.assertIs(result.status, ToolInvocationStatus.succeeded)
        self.assertEqual(result.output, "async:rag")

    def test_async_handler_respects_timeout(self) -> None:
        runtime = build_runtime()
        result = asyncio.run(
            runtime.execute("async_slow", {"text": "x"}, ToolExecutionContext())
        )
        self.assertIs(result.status, ToolInvocationStatus.timed_out)


if __name__ == "__main__":
    unittest.main()
