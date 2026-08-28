"""T4 规划粒度治理（Plan Granularity）测试。

覆盖：
- ``GranularityPolicy.assess``：短任务→light、中长→standard、长文本/多信号→heavy（≥10 下限）；
- ``clamp_steps``：超 max 截断+警告、低于 min 不强扩+警告、区间内无警告；
- ``PlannerService``：prompt 含动态步数数字；payload 记录 granularity 审计字段。
"""

import json
import unittest
from typing import Any

from app.application.planner_service import PlannerService
from app.domain.agent_core.plan_granularity import (
    ComplexitySignals,
    GranularityPolicy,
    clamp_steps,
)
from app.domain.agent_core.planner import create_plan_step


def as_dict(value: dict[str, object] | None) -> dict[str, Any]:
    """断言非空并收窄为 dict[str, Any]，便于测试里访问已知形状的字段。"""
    assert value is not None
    return value


# ===================== 第1步：assess 分级规则 =====================


class AssessTest(unittest.TestCase):
    """assess 的分级规则测试：写死规则、可解释、结果稳定。"""

    def test_short_task_is_light(self) -> None:
        policy = GranularityPolicy.assess("把 README 里错的版本号改成 1.2.0")

        self.assertEqual(policy.complexity, "light")
        self.assertEqual(policy.min_steps, 2)
        self.assertEqual(policy.max_steps, 4)
        self.assertTrue(policy.quality_hints)

    def test_short_task_with_heavy_signal_is_not_light(self) -> None:
        # 短但带重度信号（"实现"）→ 不能判 light。
        policy = GranularityPolicy.assess("实现一个登录接口")

        self.assertNotEqual(policy.complexity, "light")

    def test_medium_task_is_standard(self) -> None:
        policy = GranularityPolicy.assess("给订单模块实现输入校验，并在订单页面展示校验提示。" * 2)

        self.assertEqual(policy.complexity, "standard")
        self.assertEqual(policy.min_steps, 4)
        self.assertEqual(policy.max_steps, 8)

    def test_one_or_two_keyword_hits_is_standard(self) -> None:
        # 1-2 个重度关键词（实现、重构）→ standard，而不是 heavy。
        policy = GranularityPolicy.assess(
            "实现一个缓存层，并重构订单查询，让它更快一些，注意保持接口不变。"
        )

        self.assertEqual(policy.complexity, "standard")

    def test_long_task_is_heavy_with_min_ten_steps(self) -> None:
        long_task = "把整个订单链路从旧框架迁移到新框架，包括下单、支付、退款、对账、通知。" * 10

        policy = GranularityPolicy.assess(long_task)

        self.assertEqual(policy.complexity, "heavy")
        self.assertGreaterEqual(policy.min_steps, 10)
        self.assertEqual(policy.max_steps, 15)

    def test_three_keyword_hits_is_heavy(self) -> None:
        policy = GranularityPolicy.assess("实现支付网关，重构订单服务，迁移数据库到新的实例")

        self.assertEqual(policy.complexity, "heavy")
        self.assertGreaterEqual(policy.min_steps, 10)

    def test_tests_and_files_together_is_heavy(self) -> None:
        policy = GranularityPolicy.assess("为文件解析模块编写测试并跑通全部测试")

        self.assertEqual(policy.complexity, "heavy")

    def test_explicit_signals_override_task_text(self) -> None:
        # 显式传入 signals 时直接按 signals 判定，不再解析任务文本。
        policy = GranularityPolicy.assess(
            "hello",
            signals=ComplexitySignals(
                keyword_hits=0,
                task_char_len=500,
                mentions_tests=False,
                mentions_files=False,
                mentions_multi_component=False,
            ),
        )

        self.assertEqual(policy.complexity, "heavy")

    def test_heavy_policy_carries_anti_padding_hint(self) -> None:
        # heavy 必须带"禁止为凑数拆垃圾步骤"的提示（反互博设计）。
        policy = GranularityPolicy.assess("实现支付链路：下单、支付、退款、对账、通知。" * 15)

        self.assertEqual(policy.complexity, "heavy")
        self.assertTrue(
            any("合并相近步骤" in hint or "填充步骤" in hint for hint in policy.quality_hints)
        )


# ===================== 第2步：clamp_steps 宽进严出 =====================


def build_steps(count: int) -> list:
    return [
        create_plan_step(
            title=f"步骤 {i + 1}",
            description="说明",
            expected_output="输出",
        )
        for i in range(count)
    ]


class ClampStepsTest(unittest.TestCase):
    """clamp_steps：超 max 截断+警告；低于 min 不强扩+警告；区间内原样通过。"""

    def test_over_max_is_truncated_with_warning(self) -> None:
        policy = GranularityPolicy(
            min_steps=2, max_steps=4, complexity="light", quality_hints=[]
        )

        clamped, warnings = clamp_steps(build_steps(7), policy)

        self.assertEqual(len(clamped), 4)
        self.assertEqual(clamped[0].title, "步骤 1")
        self.assertEqual(len(warnings), 1)
        self.assertIn("超过上限", warnings[0])

    def test_under_min_is_not_padded_but_warned(self) -> None:
        # 宽进严出：低于 min 不强行扩充，只给"粒度不足"警告留给评审。
        policy = GranularityPolicy(
            min_steps=10, max_steps=15, complexity="heavy", quality_hints=[]
        )

        steps = build_steps(3)
        clamped, warnings = clamp_steps(steps, policy)

        self.assertEqual(clamped, steps)
        self.assertEqual(len(warnings), 1)
        self.assertIn("低于下限", warnings[0])

    def test_within_range_passes_through_without_warning(self) -> None:
        policy = GranularityPolicy(
            min_steps=10, max_steps=15, complexity="heavy", quality_hints=[]
        )

        clamped, warnings = clamp_steps(build_steps(12), policy)

        self.assertEqual(len(clamped), 12)
        self.assertEqual(warnings, [])


# ===================== 第3步：planner prompt 与 payload 的粒度治理 =====================


class PlannerGranularityTest(unittest.IsolatedAsyncioTestCase):
    """PlannerService 动态 prompt 数字 + payload granularity 审计字段。"""

    def _service(self) -> PlannerService:
        # 只调用内部方法，uow 不需要真实依赖。
        return PlannerService(uow=None, llm_service=None)  # type: ignore[arg-type]

    def test_prompt_contains_dynamic_step_range_for_light_task(self) -> None:
        service = self._service()

        messages = service._build_planning_messages("把 README 里错的版本号改成 1.2.0", "")

        system_prompt = messages[0].content
        self.assertIn("拆成 2 到 4 个可执行步骤", system_prompt)
        self.assertIn("light", system_prompt)

    def test_prompt_contains_dynamic_step_range_for_heavy_task(self) -> None:
        service = self._service()
        heavy_task = "实现支付链路：下单、支付、退款、对账、通知，并做全链路回归。" * 12

        messages = service._build_planning_messages(heavy_task, "")

        system_prompt = messages[0].content
        self.assertIn("拆成 10 到 15 个可执行步骤", system_prompt)
        self.assertIn("heavy", system_prompt)

    def test_parse_llm_plan_clamps_and_records_granularity(self) -> None:
        service = self._service()
        # light 任务（max=4），但模型返回 6 步 → 截断到 4 步并记录警告。
        content = json.dumps(
            {
                "title": "计划",
                "goal": "改版本号",
                "steps": [
                    {"title": f"步骤 {i + 1}", "description": "说明", "expected_output": "输出"}
                    for i in range(6)
                ],
            }
        )

        plan, granularity = service._parse_llm_plan(
            task="把 README 里错的版本号改成 1.2.0", content=content
        )

        self.assertEqual(len(plan.steps), 4)
        self.assertIsNotNone(granularity)
        granularity = as_dict(granularity)
        self.assertEqual(granularity["complexity"], "light")
        self.assertEqual(granularity["min_steps"], 2)
        self.assertEqual(granularity["max_steps"], 4)
        self.assertEqual(len(granularity["warnings"]), 1)

    def test_parse_llm_plan_under_min_warns_without_padding(self) -> None:
        service = self._service()
        # heavy 任务（min=10），模型只给 3 步 → 不强扩，只记"粒度不足"警告。
        heavy_task = "实现支付链路：下单、支付、退款、对账、通知，并做全链路回归。" * 12
        content = json.dumps(
            {
                "title": "计划",
                "goal": heavy_task,
                "steps": [
                    {"title": f"步骤 {i + 1}", "description": "说明", "expected_output": "输出"}
                    for i in range(3)
                ],
            }
        )

        plan, granularity = service._parse_llm_plan(task=heavy_task, content=content)

        self.assertEqual(len(plan.steps), 3)
        self.assertIsNotNone(granularity)
        granularity = as_dict(granularity)
        self.assertEqual(granularity["complexity"], "heavy")
        self.assertEqual(len(granularity["warnings"]), 1)
        self.assertIn("低于下限", granularity["warnings"][0])

    def test_payload_records_granularity_when_present(self) -> None:
        service = self._service()
        content = json.dumps(
            {
                "title": "计划",
                "goal": "目标",
                "steps": [
                    {"title": f"步骤 {i + 1}", "description": "说明", "expected_output": "输出"}
                    for i in range(6)
                ],
            }
        )

        plan, granularity = service._parse_llm_plan(
            task="把 README 里错的版本号改成 1.2.0", content=content
        )

        payload: dict[str, Any] = service._plan_to_payload(
            plan, memory_ids=[], granularity=granularity
        )

        self.assertIn("granularity", payload)
        self.assertEqual(payload["granularity"]["complexity"], "light")
        self.assertEqual(len(payload["granularity"]["warnings"]), 1)

    def test_payload_omits_granularity_for_fallback(self) -> None:
        service = self._service()
        plan = service._build_fallback_plan("某个任务")

        payload: dict[str, Any] = service._plan_to_payload(plan, memory_ids=[])

        self.assertNotIn("granularity", payload)

    def test_parse_llm_plan_invalid_json_returns_fallback_without_granularity(self) -> None:
        service = self._service()

        plan, granularity = service._parse_llm_plan(task="随便一个任务", content="not json")

        self.assertEqual(plan.source, "fallback")
        self.assertIsNone(granularity)


if __name__ == "__main__":
    unittest.main()
