import unittest

from app.application.tool_selection_service import ModelToolSelectionService
from app.domain.agent_core.tools import AgentTool, ToolDefinition, ToolParameter, ToolRegistry
from app.domain.llm.entities import LLMChatResult


class FakeLLMService:
    """为工具选择测试返回固定模型输出，不访问真实模型服务。"""

    def __init__(self, content: str | Exception) -> None:
        self.content = content
        self.messages = []

    async def chat(self, messages, **kwargs):
        self.messages = messages
        if isinstance(self.content, Exception):
            raise self.content
        return LLMChatResult(
            provider="fake",
            model="fake-tool-selector",
            content=self.content,
            usage=None,
        )


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="search_web",
                description="搜索互联网公开网页。",
                parameters=[
                    ToolParameter(
                        name="query",
                        type="string",
                        description="搜索关键词。",
                    ),
                    ToolParameter(
                        name="count",
                        type="integer",
                        description="结果数量。",
                        required=False,
                    ),
                ],
            ),
            handler=lambda query, count=5: f"搜索：{query}，数量：{count}",
        )
    )
    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="summarize_text",
                description="总结文本。",
                parameters=[
                    ToolParameter(
                        name="text",
                        type="string",
                        description="要总结的文本。",
                    )
                ],
            ),
            handler=lambda text: f"摘要：{text}",
        )
    )
    return registry


class ModelToolSelectionServiceTest(unittest.IsolatedAsyncioTestCase):
    # ===================== 第1步：模型返回合法 tool call 时优先使用模型选择 =====================
    async def test_selects_tool_from_model_json(self) -> None:
        service = ModelToolSelectionService(
            registry=build_registry(),
            llm_service=FakeLLMService(
                '{"tool_name":"search_web","arguments":{"query":"AI Agent news","count":3}}'
            ),
        )

        result = await service.call_tool_for_step(
            plan={"goal": "搜索 AI Agent 新闻"},
            step={"title": "搜索资料", "description": "搜索 AI Agent news"},
            index=1,
            agent_context="长期记忆：用户偏好中文解释",
        )

        self.assertEqual(result.tool_name, "search_web")
        self.assertEqual(result.arguments["query"], "AI Agent news")
        self.assertEqual(result.arguments["count"], 3)

    # ===================== 第2步：模型输出不可解析时回退到确定性规则 =====================
    async def test_falls_back_to_rule_when_model_output_is_invalid(self) -> None:
        service = ModelToolSelectionService(
            registry=build_registry(),
            llm_service=FakeLLMService("这不是 JSON"),
        )

        result = await service.call_tool_for_step(
            plan={"goal": "请搜索 FastAPI 资料"},
            step={"title": "搜索资料", "description": "查找 FastAPI 最新资料"},
            index=1,
            agent_context="",
        )

        self.assertEqual(result.tool_name, "search_web")
        self.assertIn("FastAPI", result.arguments["query"])

    # ===================== 第3步：模型缺少必填参数时尝试从当前步骤修复 =====================
    async def test_repairs_missing_required_argument_before_calling_tool(self) -> None:
        service = ModelToolSelectionService(
            registry=build_registry(),
            llm_service=FakeLLMService('{"tool_name":"search_web","arguments":{}}'),
        )

        result = await service.call_tool_for_step(
            plan={"goal": "搜索 PostgreSQL 索引优化"},
            step={"title": "搜索资料", "description": "检索 PostgreSQL 索引优化"},
            index=1,
            agent_context="",
        )

        self.assertEqual(result.tool_name, "search_web")
        self.assertIn("PostgreSQL", result.arguments["query"])


if __name__ == "__main__":
    unittest.main()
