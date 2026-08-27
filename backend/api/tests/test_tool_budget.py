"""工具调用预算控制（Budget）单元测试。

覆盖：token 估算、构造校验、三个预算维度（步骤总次数 / 单工具次数 /
token 估算上限）的判定与记账、超预算结构化结果（JSON + audit 标记）、
审计快照，以及 StepAgentLoop 接线（超预算时不执行工具直接返回
budget_exceeded 结果；依赖批次规划）。
"""

import json
import unittest

from app.application.agent_loop import StepAgentLoop, ToolCallRequest
from app.application.tool_runtime import ToolExecutionContext
from app.domain.agent_core.tool_budget import ToolBudget, estimate_tokens
from app.domain.agent_core.tools import ToolRegistry, agent_tool


@agent_tool(
    name="budget_echo",
    description="预算测试用回显工具",
    parameter_descriptions={"text": "文本"},
    required_permissions=("text:read",),
    idempotent=True,
)
def budget_echo(text: str) -> str:
    """简单回显。"""
    return text


class EstimateTokensTest(unittest.TestCase):
    def test_empty_and_short_texts(self) -> None:
        """空文本为 0；非空最少 1 个 token。"""
        self.assertEqual(estimate_tokens(""), 0)
        self.assertEqual(estimate_tokens("a"), 1)

    def test_long_text_ceil(self) -> None:
        """约 2 字符 1 token，向上取整。"""
        self.assertEqual(estimate_tokens("a" * 10), 5)
        self.assertEqual(estimate_tokens("a" * 11), 6)


class ToolBudgetTest(unittest.TestCase):
    def test_constructor_rejects_non_positive_limits(self) -> None:
        """三个上限必须为正数。"""
        with self.assertRaises(ValueError):
            ToolBudget(max_calls_per_step=0)
        with self.assertRaises(ValueError):
            ToolBudget(max_calls_per_tool=0)
        with self.assertRaises(ValueError):
            ToolBudget(max_token_estimate=0)

    def test_step_call_limit(self) -> None:
        """步骤总次数用尽后拒绝，reason=step_call_limit。"""
        budget = ToolBudget(max_calls_per_step=2, max_calls_per_tool=10)
        for _ in range(2):
            self.assertTrue(budget.check_call("a").allowed)
            budget.record_call("a", "x")
        check = budget.check_call("b")
        self.assertFalse(check.allowed)
        self.assertEqual(check.reason, "step_call_limit")

    def test_per_tool_limit(self) -> None:
        """单工具次数用尽后只拒绝该工具，其他工具仍可调用。"""
        budget = ToolBudget(max_calls_per_step=10, max_calls_per_tool=2)
        budget.record_call("a", "")
        budget.record_call("a", "")
        check_a = budget.check_call("a")
        self.assertFalse(check_a.allowed)
        self.assertEqual(check_a.reason, "tool_call_limit")
        self.assertTrue(budget.check_call("b").allowed)

    def test_token_estimate_limit(self) -> None:
        """累计 token 估算达上限后拒绝，reason=token_estimate_limit。"""
        budget = ToolBudget(max_calls_per_step=10, max_token_estimate=6)
        budget.record_call("a", "a" * 10)  # 5 tokens
        budget.record_call("a", "a" * 2)  # 再 +1 tokens，共 6
        check = budget.check_call("a")
        self.assertFalse(check.allowed)
        self.assertEqual(check.reason, "token_estimate_limit")

    def test_record_call_counts_failures_too(self) -> None:
        """失败调用同样消耗预算（占用模型轮次）。"""
        budget = ToolBudget(max_calls_per_step=1)
        budget.record_call("a", "failed output")
        self.assertEqual(budget.calls_used, 1)
        self.assertFalse(budget.check_call("a").allowed)

    def test_build_exceeded_result_is_structured_json(self) -> None:
        """超预算结果是结构化 JSON + audit 标记，状态为 failed。"""
        budget = ToolBudget(max_calls_per_step=1)
        budget.record_call("a", "")
        check = budget.check_call("a")
        result = budget.build_exceeded_result("a", check, {"text": "x"})
        self.assertEqual(result.status.value, "failed")
        self.assertFalse(result.cache_hit)
        payload = json.loads(result.output)
        self.assertTrue(payload["budget_exceeded"])
        self.assertEqual(payload["reason"], "step_call_limit")
        self.assertIn("suggestion", payload)
        self.assertEqual((result.audit or {}).get("budget_exceeded"), "step_call_limit")
        self.assertIn("budget", result.audit or {})

    def test_to_audit_snapshot(self) -> None:
        """审计快照包含用量与上限。"""
        budget = ToolBudget(max_calls_per_step=12, max_calls_per_tool=4)
        budget.record_call("a", "a" * 10)
        snapshot = budget.to_audit()
        self.assertEqual(snapshot["calls_used"], 1)
        self.assertEqual(snapshot["calls_by_tool"], {"a": 1})
        self.assertEqual(snapshot["max_calls_per_step"], 12)
        self.assertEqual(snapshot["token_estimate_used"], 5)

    def test_from_settings_reads_tool_budget_config(self) -> None:
        """from_settings 读取 app/core/config.py 的 tool_budget_* 配置。"""
        budget = ToolBudget.from_settings()
        self.assertGreater(budget.max_calls_per_step, 0)
        self.assertGreater(budget.max_calls_per_tool, 0)
        self.assertGreater(budget.max_token_estimate, 0)


class StepAgentLoopBudgetWiringTest(unittest.IsolatedAsyncioTestCase):
    async def test_budget_exceeded_returns_without_executing(self) -> None:
        """超预算时不执行工具，直接返回 budget_exceeded 结果。"""
        registry = ToolRegistry()
        registry.register(budget_echo)
        loop = StepAgentLoop(registry=registry)
        budget = ToolBudget(max_calls_per_step=10, max_calls_per_tool=1)
        budget.record_call("budget_echo", "")  # 用尽单工具额度

        request = ToolCallRequest(id=None, name="budget_echo", arguments={"text": "x"})
        call_id, result = await loop._execute_with_budget(
            request, ToolExecutionContext(), turn=1, offset=0, budget=budget
        )
        self.assertEqual(call_id, "call_1_0")
        self.assertEqual(budget.calls_used, 1)  # 没有新增调用
        self.assertEqual((result.audit or {}).get("budget_exceeded"), "tool_call_limit")
        payload = json.loads(result.output)
        self.assertTrue(payload["budget_exceeded"])

    async def test_plan_batches_orders_by_capability_tags(self) -> None:
        """_plan_batches 按能力标签把依赖调用排到后续批次。"""
        registry = ToolRegistry()
        registry.register(budget_echo)
        loop = StepAgentLoop(registry=registry)
        requests = [
            ToolCallRequest(id=None, name="unknown_tool_b", arguments={}),
            ToolCallRequest(id=None, name="unknown_tool_a", arguments={}),
        ]
        # 注册表里没有 unknown_tool_*（模拟未注册工具）：视为无依赖，单批保持顺序。
        batches = loop._plan_batches(requests)
        names = [[request.name for _, request in batch] for batch in batches]
        self.assertEqual(names, [["unknown_tool_b", "unknown_tool_a"]])

    async def test_plan_batches_with_registered_dependency(self) -> None:
        """已注册工具的 provides/requires 参与批次规划。"""
        from app.domain.agent_core.tools import (
            ToolDefinition,
            ToolParameter,
        )

        registry = ToolRegistry()
        registry.register(budget_echo)

        async def fetch_fn(url: str) -> str:
            return url

        async def parse_fn(html: str) -> str:
            return html

        # 手动构造带能力标签的工具定义并包装为 AgentTool 注册。
        from app.domain.agent_core.tools import AgentTool

        fetch_tool = AgentTool(
            definition=ToolDefinition(
                name="fetch",
                description="抓取",
                parameters=[ToolParameter(name="url", type="string", description="地址")],
                provides=("page_html",),
            ),
            handler=fetch_fn,
        )
        parse_tool = AgentTool(
            definition=ToolDefinition(
                name="parse",
                description="解析",
                parameters=[ToolParameter(name="html", type="string", description="页面")],
                requires=("page_html",),
            ),
            handler=parse_fn,
        )
        registry.register(fetch_tool)
        registry.register(parse_tool)

        loop = StepAgentLoop(registry=registry)
        requests = [
            ToolCallRequest(id=None, name="parse", arguments={"html": ""}),
            ToolCallRequest(id=None, name="fetch", arguments={"url": "https://x"}),
        ]
        batches = loop._plan_batches(requests)
        names = [[request.name for _, request in batch] for batch in batches]
        self.assertEqual(names, [["fetch"], ["parse"]])


if __name__ == "__main__":
    unittest.main()
