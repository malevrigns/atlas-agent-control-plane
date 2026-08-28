"""步骤历史上下文预算（Context Budget）单元测试。

覆盖：
- 三段分层（最近 2 条全文 / 中间 digest 摘要 / 最老 title-only）；
- 总预算硬上限（压缩后渲染字符数 ≤ max_history_chars）；
- 确定性（同输入恒同输出）；
- 空历史、单条历史等边界；
- split_history_entry 对 format_step_history 两种形态的解析；
- react_step_executor 集成：超长 fake history 进入模型 prompt 前被压缩，
  原始 step_history（审计线）保持不动。
"""

import unittest
from types import SimpleNamespace
from uuid import uuid4

from app.application.agent_loop import StepAgentLoop
from app.application.react_step_executor import (
    ReActStepExecutor,
    StepExecutionRequest,
)
from app.domain.agent_core.context_budget import (
    ContextBudget,
    ContextBudgetConfig,
    split_history_entry,
)
from app.domain.agent_core.tools import ToolRegistry
from app.domain.llm.entities import LLMChatResult, LLMMessage
from tests.test_agent_execution_machine import (
    FakeEventSink,
    empty_memory_context,
    plan_payload,
)


def _entry(index: int, body: str) -> str:
    """构造一条 format_step_history 形态的条目（有工具结果）。"""
    return f"- 步骤{index}《第{index}步》已完成（stub_tool）：{body}"


class SplitHistoryEntryTest(unittest.TestCase):
    def test_tool_entry_splits_title_and_body(self) -> None:
        """有工具结果的条目：title=《》内文本，body=全角冒号后的摘要。"""
        entry = "- 步骤3《改写配置》已完成（file_write）：落盘成功，共 3 处变更"
        self.assertEqual(split_history_entry(entry), ("改写配置", "落盘成功，共 3 处变更"))

    def test_failed_status_entry_still_splits(self) -> None:
        """失败状态条目同样可解析（状态词不影响 title/body 切分）。"""
        entry = "- 步骤2《执行脚本》⚠️ 失败（shell_run）：exit code 1"
        self.assertEqual(split_history_entry(entry), ("执行脚本", "exit code 1"))

    def test_no_tool_entry_has_empty_body(self) -> None:
        """无工具结果的条目（以「。」结尾）：body 为空串。"""
        self.assertEqual(split_history_entry("- 步骤1《生成报告》已完成。"), ("生成报告", ""))

    def test_unparseable_entry_returns_empty_title(self) -> None:
        """不匹配已知格式的条目：title 为空、body 为原文（触发 fallback）。"""
        self.assertEqual(split_history_entry("随便一行文字"), ("", "随便一行文字"))


class ContextBudgetTierTest(unittest.TestCase):
    """三段分层：最近 2 条全文、中间摘要、最老 title-only。"""

    def setUp(self) -> None:
        self.history = (
            _entry(1, "x" * 500),
            _entry(2, "y" * 500),
            _entry(3, "z" * 500),
            "- 步骤4《生成报告》已完成。",
            _entry(5, "最终结果文本"),
        )
        self.budget = ContextBudget(ContextBudgetConfig())

    def test_three_tiers_layering(self) -> None:
        """5 条历史：第 1 条 title-only、第 2-3 条 digest、第 4-5 条全文。"""
        out = self.budget.compress(self.history)
        self.assertEqual(len(out), 5)
        # 最老：title-only 一行（步骤 N: 标题 → 状态）
        self.assertEqual(out[0], "步骤 1: 第1步 → 已完成")
        # 中间：digest（前 400 字符 + 省略标记，N=被省略的原始字符数）
        for index in (1, 2):
            original = self.history[index]
            self.assertTrue(out[index].startswith(original[:400]), f"digest 应保留前缀: {index}")
            expected_marker = f"…[digest {len(original) - 400} chars]"
            self.assertTrue(out[index].endswith(expected_marker), f"digest 省略标记: {index}")
            self.assertLess(len(out[index]), len(original))
        # 最近 2 条：全文原样保留
        self.assertEqual(out[3], self.history[3])
        self.assertEqual(out[4], self.history[4])

    def test_digest_keeps_prefix_and_marks_omission(self) -> None:
        """digest 层长度 = 400 字符 + 省略标记，标记中的 N 是被省略的字符数。"""
        out = self.budget.compress(self.history)
        for index in (1, 2):
            original = self.history[index]
            marker = f"…[digest {len(original) - 400} chars]"
            self.assertEqual(len(out[index]), 400 + len(marker))
            self.assertTrue(out[index].endswith(marker))

    def test_short_entry_not_marked(self) -> None:
        """digest 层内但本身不超长的条目原样保留，不加标记。"""
        history = (_entry(1, "a" * 500), "- 步骤2《短》已完成。", _entry(3, "c" * 50))
        out = self.budget.compress(history)
        self.assertEqual(out[1], "- 步骤2《短》已完成。")

    def test_title_only_layer_disabled(self) -> None:
        """oldest_steps_title_only=False 时没有 title-only 层，最老条目走 digest。"""
        budget = ContextBudget(
            ContextBudgetConfig(oldest_steps_title_only=False)
        )
        out = budget.compress(self.history)
        self.assertNotIn("→", out[0])
        self.assertTrue(out[0].startswith("- 步骤1《第1步》"))


class ContextBudgetHardCapTest(unittest.TestCase):
    """总预算硬上限：压缩后渲染字符数 ≤ max_history_chars。"""

    def test_total_within_hard_cap(self) -> None:
        """小预算 + 长条目：强制逐层收紧后仍不超预算。"""
        history = tuple(_entry(i, str(i) * 800) for i in range(1, 9))
        budget = ContextBudget(
            ContextBudgetConfig(
                max_history_chars=200,
                recent_steps_full=2,
                older_steps_digest_chars=400,
            )
        )
        out = budget.compress(history)
        total = budget.estimate_chars(out)
        self.assertLessEqual(total, 200)
        # 预算收紧到连 full 层都放下时，最老条目应已是 title-only
        self.assertTrue(out[0].startswith("步骤 1: "))

    def test_hard_cap_at_all_title_only_fits(self) -> None:
        """极端小预算：全部条目都退化为 title-only 后也应达标。"""
        history = tuple(_entry(i, str(i) * 2000) for i in range(1, 6))
        budget = ContextBudget(
            ContextBudgetConfig(
                max_history_chars=400,
                recent_steps_full=2,
                older_steps_digest_chars=400,
            )
        )
        out = budget.compress(history)
        self.assertLessEqual(budget.estimate_chars(out), 400)

    def test_config_validation(self) -> None:
        """非法配置拒绝构造。"""
        with self.assertRaises(ValueError):
            ContextBudgetConfig(max_history_chars=0)
        with self.assertRaises(ValueError):
            ContextBudgetConfig(recent_steps_full=-1)
        with self.assertRaises(ValueError):
            ContextBudgetConfig(older_steps_digest_chars=0)

    def test_estimate_chars_counts_newline_separators(self) -> None:
        """估算 = 各条目长度和 + 换行分隔符（每条 1 字符）。"""
        budget = ContextBudget()
        self.assertEqual(budget.estimate_chars(()), 0)
        self.assertEqual(budget.estimate_chars(("ab", "cde")), 2 + 3 + 1)


class ContextBudgetDeterminismTest(unittest.TestCase):
    """确定性：同输入恒同输出。"""

    def test_same_input_same_output(self) -> None:
        """同一实例两次压缩、以及不同实例压缩，输出完全一致。"""
        history = tuple(_entry(i, f"输出{i}" + "k" * (100 + i * 37)) for i in range(1, 12))
        budget = ContextBudget(ContextBudgetConfig(max_history_chars=3000))
        first = budget.compress(history)
        second = budget.compress(history)
        other = ContextBudget(ContextBudgetConfig(max_history_chars=3000))
        self.assertEqual(first, second)
        self.assertEqual(first, other.compress(history))

    def test_compress_does_not_mutate_input(self) -> None:
        """压缩不修改入参（元组本身不可变，且返回的是新元组）。"""
        history = (_entry(1, "a" * 500), _entry(2, "b" * 500), _entry(3, "c" * 50))
        out = ContextBudget().compress(history)
        self.assertEqual(history, (_entry(1, "a" * 500), _entry(2, "b" * 500), _entry(3, "c" * 50)))
        self.assertIsNot(out, history)


class ContextBudgetEdgeTest(unittest.TestCase):
    """空历史、单条历史等边界。"""

    def test_empty_history_returns_empty(self) -> None:
        self.assertEqual(ContextBudget().compress(()), ())

    def test_single_history_is_full(self) -> None:
        entry = _entry(1, "唯一一条历史")
        self.assertEqual(ContextBudget().compress((entry,)), (entry,))

    def test_two_entries_both_full(self) -> None:
        history = (_entry(1, "aa"), _entry(2, "bb"))
        self.assertEqual(ContextBudget().compress(history), history)

    def test_titles_fallback_for_unparseable_entry(self) -> None:
        """条目解析不出标题时按位置使用外部 titles。"""
        history = ("非标准条目甲", "非标准条目乙", _entry(3, "c" * 50), _entry(4, "d" * 50))
        out = ContextBudget().compress(history, titles=("步骤甲", "步骤乙", "第3步", "第4步"))
        self.assertEqual(out[0], "步骤 1: 步骤甲 → 未知")

    def test_from_settings_reads_context_budget_config(self) -> None:
        """from_settings 读取 context_budget_* 三项配置（注入假 settings）。"""
        fake = SimpleNamespace(
            context_budget_max_history_chars=1111,
            context_budget_recent_steps_full=3,
            context_budget_digest_chars=55,
        )
        budget = ContextBudget.from_settings(fake)
        self.assertEqual(budget.config.max_history_chars, 1111)
        self.assertEqual(budget.config.recent_steps_full, 3)
        self.assertEqual(budget.config.older_steps_digest_chars, 55)
        self.assertTrue(budget.config.oldest_steps_title_only)  # 保持默认


class _FakeLLMService:
    """假 LLM 服务：捕获每次 chat 的 messages，直接给出最终文本回答。"""

    def __init__(self) -> None:
        self.captured: list[list[LLMMessage]] = []

    def is_configured(self) -> bool:
        return True

    async def chat(self, messages: list[LLMMessage], **kwargs: object) -> LLMChatResult:
        self.captured.append(list(messages))
        return LLMChatResult(provider="fake", model="fake", content="done")


class ReactStepExecutorIntegrationTest(unittest.IsolatedAsyncioTestCase):
    """集成：超长 step_history 进入模型 prompt 前被压缩，原始历史不动。"""

    def _make_executor(
        self,
        fake_llm: _FakeLLMService,
        budget: ContextBudget,
    ) -> ReActStepExecutor:
        loop = StepAgentLoop(registry=ToolRegistry(), llm_service=fake_llm)
        return ReActStepExecutor(
            uow=SimpleNamespace(session_events=FakeEventSink([])),
            step_loop=loop,
            context_budget=budget,
        )

    def _make_request(self, history: tuple[str, ...]) -> StepExecutionRequest:
        plan = plan_payload(1)
        return StepExecutionRequest(
            session_id=uuid4(),
            run_id=uuid4(),
            plan_revision=0,
            plan=plan,
            step=plan["steps"][0],
            step_index=0,
            attempt=1,
            memory_context=empty_memory_context(),
            agent_context="",
            step_history=history,
        )

    async def test_long_history_compressed_before_llm_message(self) -> None:
        """fake llm 捕获的消息里：老步骤被压缩、新步骤保留全文、原文不进 prompt。"""
        # 6 条历史，每条 body 各不相同（约 300+ 字符），小预算迫使分层压缩。
        history = tuple(
            _entry(i, f"第{i}步独特输出 " + str(i) * 300) for i in range(1, 7)
        )
        fake_llm = _FakeLLMService()
        budget = ContextBudget(
            ContextBudgetConfig(
                max_history_chars=1200,
                recent_steps_full=2,
                older_steps_digest_chars=60,
            )
        )
        executor = self._make_executor(fake_llm, budget)
        request = self._make_request(history)
        await executor.execute(request)

        self.assertEqual(len(fake_llm.captured), 1)
        messages = fake_llm.captured[0]
        # 初始消息：system + user（step task 携带压缩后的历史）。
        user_content = messages[1].content
        self.assertIn("…[digest", user_content, "老步骤应被 digest 压缩")
        # 最老的完整 body 不应进入 prompt；最近的（全文层）body 应保留。
        self.assertNotIn(history[0], user_content)
        self.assertNotIn(history[3], user_content)
        self.assertIn(history[4], user_content)
        self.assertIn(history[5], user_content)
        # 渲染后的历史总长受预算约束（含 heading 外的历史部分）。
        self.assertLess(
            budget.estimate_chars(budget.compress(history)),
            1200,
        )

    async def test_original_history_stays_intact_for_audit(self) -> None:
        """压缩只发生在喂给模型的地方：原始 step_history 保持全文不动。"""
        history = tuple(_entry(i, str(i) * 800) for i in range(1, 9))
        fake_llm = _FakeLLMService()
        budget = ContextBudget(
            ContextBudgetConfig(max_history_chars=200, recent_steps_full=2)
        )
        executor = self._make_executor(fake_llm, budget)
        request = self._make_request(history)
        await executor.execute(request)
        # 原始历史（审计线）未被压缩覆盖。
        self.assertEqual(request.step_history, history)

    async def test_render_agent_context_uses_compressed_copy(self) -> None:
        """_render_agent_context 直接断言：渲染结果是压缩后的副本。"""
        history = tuple(_entry(i, str(i) * 800) for i in range(1, 9))
        budget = ContextBudget(
            ContextBudgetConfig(max_history_chars=200, recent_steps_full=2)
        )
        executor = ReActStepExecutor(
            uow=SimpleNamespace(session_events=FakeEventSink([])),
            context_budget=budget,
        )
        request = self._make_request(history)
        rendered = executor._render_agent_context(request)
        self.assertIn("本轮已完成步骤的结果", rendered)
        # 预算收紧到 title-only：不应出现任何长 body。
        for body in (str(i) * 800 for i in range(1, 9)):
            self.assertNotIn(body, rendered)
        self.assertLess(len(rendered), budget.config.max_history_chars + 40)


if __name__ == "__main__":
    unittest.main()
