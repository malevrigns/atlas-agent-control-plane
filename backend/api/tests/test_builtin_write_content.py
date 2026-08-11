import unittest

from app.application.tool_runtime import ToolExecutionContext, ToolRuntime
from app.core.exceptions import AppException
from app.domain.agent_core.tools import ToolInvocationStatus
from app.domain.llm.entities import LLMChatResult
from app.infrastructure.agent_tools.builtin import build_builtin_tool_registry


class FakeContentModel:
    def __init__(
        self,
        error: AppException | None = None,
        *,
        content: str = "injected content",
    ) -> None:
        self.error = error
        self.content = content
        self.calls = []

    async def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        if self.error is not None:
            raise self.error
        return LLMChatResult("test", "test-model", self.content)


class BuiltinWriteContentTest(unittest.IsolatedAsyncioTestCase):
    async def test_write_content_uses_injected_model(self) -> None:
        model = FakeContentModel()
        runtime = ToolRuntime(build_builtin_tool_registry(content_model=model))

        result = await runtime.execute(
            "write_content",
            {"task": "write a report"},
            ToolExecutionContext(),
        )

        self.assertEqual(result.status, ToolInvocationStatus.succeeded)
        self.assertEqual(result.output, "injected content")
        self.assertEqual(len(model.calls), 1)
        self.assertEqual(model.calls[0][0][-1].content, "write a report")

    async def test_model_error_is_recorded_as_failed_tool_result(self) -> None:
        model = FakeContentModel(AppException(message="provider unavailable"))
        runtime = ToolRuntime(build_builtin_tool_registry(content_model=model))

        result = await runtime.execute(
            "write_content",
            {"task": "write a report"},
            ToolExecutionContext(),
        )

        self.assertEqual(result.status, ToolInvocationStatus.failed)
        self.assertIn("provider unavailable", result.output)
        self.assertNotIn("内容生成失败", result.output)

    async def test_empty_model_content_is_recorded_as_failed_tool_result(self) -> None:
        model = FakeContentModel(content="   \n")
        runtime = ToolRuntime(build_builtin_tool_registry(content_model=model))

        result = await runtime.execute(
            "write_content",
            {"task": "write a report"},
            ToolExecutionContext(),
        )

        self.assertEqual(result.status, ToolInvocationStatus.failed)
        self.assertIn("AppException", result.output)
        self.assertIn("LLM returned empty content", result.output)


if __name__ == "__main__":
    unittest.main()
