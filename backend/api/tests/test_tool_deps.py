"""工具依赖图与并行批次规划单元测试。

语义说明（见 tool_deps.py 模块 docstring）：
- 依赖通过能力标签（provides / requires）表达，而非工具名；
- 一轮请求内，requires 的标签只要没有任何调用 provides，
  视为外部已满足（如浏览器状态由上一步留下），不构成排序约束；
- 批次内保持输入顺序；发现循环依赖抛出 ToolDependencyError。
"""

import unittest

from app.domain.agent_core.tool_deps import (
    ToolCall,
    ToolDependencyError,
    plan_parallel_batches,
    tool_call_from_definition,
)
from app.domain.agent_core.tools import ToolDefinition


def _batch_names(batches: list[list[ToolCall]]) -> list[list[str]]:
    """把批次转换为名字列表，便于直观断言。"""
    return [[call.name for call in batch] for batch in batches]


class PlanParallelBatchesTest(unittest.TestCase):
    def test_empty_list_returns_no_batches(self) -> None:
        """空请求列表返回空计划。"""
        self.assertEqual(plan_parallel_batches([]), [])

    def test_no_dependencies_single_batch_keeps_order(self) -> None:
        """全部无依赖时归为一批，且保持输入顺序。"""
        calls = [
            ToolCall(name="b", arguments={}),
            ToolCall(name="a", arguments={}),
            ToolCall(name="c", arguments={}),
        ]
        self.assertEqual(_batch_names(plan_parallel_batches(calls)), [["b", "a", "c"]])

    def test_linear_dependency_two_batches(self) -> None:
        """b 需要 a 提供的标签：a 先执行，b 后执行。"""
        calls = [
            ToolCall(name="b", arguments={}, requires=("page_html",)),
            ToolCall(name="a", arguments={}, provides=("page_html",)),
        ]
        self.assertEqual(_batch_names(plan_parallel_batches(calls)), [["a"], ["b"]])

    def test_diamond_dependency_three_batches(self) -> None:
        """菱形依赖：a -> (b, c) -> d，b/c 无相互依赖可同批并行。"""
        calls = [
            ToolCall(name="a", arguments={}, provides=("ctx",)),
            ToolCall(name="b", arguments={}, requires=("ctx",), provides=("b_out",)),
            ToolCall(name="c", arguments={}, requires=("ctx",), provides=("c_out",)),
            ToolCall(name="d", arguments={}, requires=("b_out", "c_out")),
        ]
        self.assertEqual(
            _batch_names(plan_parallel_batches(calls)), [["a"], ["b", "c"], ["d"]]
        )

    def test_two_node_cycle_raises(self) -> None:
        """a/b 互相需要对方提供的标签：抛出 ToolDependencyError。"""
        calls = [
            ToolCall(name="a", arguments={}, provides=("t1",), requires=("t2",)),
            ToolCall(name="b", arguments={}, provides=("t2",), requires=("t1",)),
        ]
        with self.assertRaises(ToolDependencyError) as ctx:
            plan_parallel_batches(calls)
        # 错误信息携带环路径（工具名序列，首尾同名）。
        self.assertIn("a", str(ctx.exception))
        self.assertIn("b", str(ctx.exception))

    def test_external_tag_is_not_a_constraint(self) -> None:
        """requires 的标签没有任何调用提供时视为外部已满足，不阻塞。"""
        calls = [
            ToolCall(name="a", arguments={}, requires=("page_opened",)),
            ToolCall(name="b", arguments={}),
        ]
        self.assertEqual(_batch_names(plan_parallel_batches(calls)), [["a", "b"]])

    def test_self_provided_self_required_tag_no_cycle(self) -> None:
        """同一调用既 provides 又 requires 同一标签不构成自环。"""
        calls = [ToolCall(name="a", arguments={}, provides=("t",), requires=("t",))]
        self.assertEqual(_batch_names(plan_parallel_batches(calls)), [["a"]])

    def test_batches_cover_every_call_exactly_once(self) -> None:
        """所有调用恰好出现在一个批次中（不重不漏）。"""
        calls = [
            ToolCall(name="c", arguments={}, requires=("b_out",)),
            ToolCall(name="a", arguments={}, provides=("a_out",)),
            ToolCall(name="b", arguments={}, requires=("a_out",), provides=("b_out",)),
            ToolCall(name="d", arguments={}),
        ]
        batches = plan_parallel_batches(calls)
        flat = [call.name for batch in batches for call in batch]
        self.assertEqual(sorted(flat), ["a", "b", "c", "d"])
        # 层级正确：a 在第 0 批，b 在第 1 批，c/d 在第 2 批。
        self.assertEqual(_batch_names(batches), [["a", "d"], ["b"], ["c"]])


class ToolCallFromDefinitionTest(unittest.TestCase):
    def test_provides_requires_are_copied(self) -> None:
        """definition 的 provides/requires 透传到 ToolCall，arguments 深拷贝。"""
        definition = ToolDefinition(
            name="fetch_page",
            description="抓取页面",
            parameters=[],
            provides=("page_html",),
            requires=("page_opened",),
        )
        source_arguments = {"url": "https://example.com"}
        call = tool_call_from_definition(definition, source_arguments)
        self.assertEqual(call.name, "fetch_page")
        self.assertEqual(call.provides, ("page_html",))
        self.assertEqual(call.requires, ("page_opened",))
        self.assertEqual(call.arguments, source_arguments)
        self.assertIsNot(call.arguments, source_arguments)

    def test_call_id_passthrough(self) -> None:
        """显式 call_id 原样透传；缺省为 None。"""
        definition = ToolDefinition(name="t", description="d", parameters=[])
        self.assertIsNone(tool_call_from_definition(definition, {}).call_id)
        self.assertEqual(
            tool_call_from_definition(definition, {}, call_id="call_1").call_id, "call_1"
        )


if __name__ == "__main__":
    unittest.main()
