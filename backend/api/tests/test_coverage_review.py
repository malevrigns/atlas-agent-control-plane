"""覆盖度评审（Coverage Review）domain 模型与应用服务测试。

覆盖：
- prompt 构造：含全部要素（目标/验收标准/改动文件/测试文件/用例名）且长度可控（超长截断）；
- LLM 输出解析：合法 JSON / 围栏 JSON / 前后多余文字 / 垃圾输出抛 ValueError；
- adequacy 硬规则：high gap → inadequate（不采信模型自报）；仅 medium/low → adequate 但保留 gaps；
- 失败开放：LLM 缺失/未配置/调用异常/解析失败/配置关闭 → skipped + adequate=True 不抛异常；
- enforce_coverage 语义：False 时 inadequate 不触发重试；True + inadequate → 触发重试且 reason 列 high gaps；
- coverage_review_finished 审计事件（gaps 按配置截断、事件写入失败不阻断）。
"""

import json
import unittest
from collections.abc import Sequence
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import UUID, uuid4

from app.application.coverage_review_service import (
    CoverageReviewService,
    enforce_coverage_from_plan,
    should_retry,
)
from app.core.config import settings
from app.domain.acceptance.coverage import (
    build_review_prompt,
    collect_test_case_names,
    parse_review,
)
from app.domain.llm.entities import LLMChatResult
from app.domain.sessions.entities import SessionEvent, SessionEventType

_SESSION_ID = uuid4()
_RUN_ID = uuid4()

_GOAL = "实现用户登录接口，支持 token 过期自动刷新"
_CRITERIA = ["登录成功后返回 token", "过期 token 自动刷新且不中断请求"]
_CHANGED = ["app/api/routes/auth.py", "app/services/token_service.py"]
_TESTS = ["tests/test_auth.py", "tests/test_token_service.py"]
_CASES = [
    "tests/test_auth.py::test_login_success",
    "tests/test_token_service.py::test_refresh_expired",
]


def _review_payload(adequate: bool, gaps: Sequence[object], reason: str = "覆盖良好") -> str:
    """构造模拟 LLM 输出的评审 JSON 文本。"""
    return json.dumps(
        {"adequate": adequate, "gaps": gaps, "reason": reason}, ensure_ascii=False
    )


def _make_plan(**extra: object) -> dict[str, object]:
    """构造默认 plan payload（不带 acceptance 字段，向后兼容形态）。"""
    plan: dict[str, object] = {
        "id": "plan-001",
        "plan_revision": 2,
        "goal": _GOAL,
        "acceptance_criteria": list(_CRITERIA),
    }
    plan.update(extra)
    return plan


# ===================== 测试替身 =====================


class FakeLLM:
    """假 LLM：记录收到的 prompt，返回预设内容或抛出预设异常。"""

    def __init__(
        self,
        content: str = "",
        configured: bool = True,
        error: Exception | None = None,
    ) -> None:
        self.content = content
        self._configured = configured
        self._error = error
        self.prompts: list[str] = []

    def is_configured(self) -> bool:
        return self._configured

    async def chat(self, messages, **kwargs) -> LLMChatResult:
        self.prompts = [message.content for message in messages]
        if self._error is not None:
            raise self._error
        return LLMChatResult(provider="test", model="test-model", content=self.content)


class FakeEventSink:
    """假事件写入器：记录所有事件；可预设写入异常。"""

    def __init__(self) -> None:
        self.events: list[tuple[SessionEventType, dict]] = []
        self.error: Exception | None = None

    async def add(
        self,
        *,
        session_id: UUID,
        event_type: SessionEventType,
        payload: dict,
    ) -> SessionEvent:
        if self.error is not None:
            raise self.error
        self.events.append((event_type, payload))
        return SessionEvent(
            id=uuid4(),
            session_id=session_id,
            type=event_type,
            payload=payload,
            created_at=datetime.now(UTC),
        )


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.session_events = FakeEventSink()

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


def _make_service(
    llm: FakeLLM | None,
) -> tuple[CoverageReviewService, FakeEventSink]:
    uow = FakeUnitOfWork()
    return CoverageReviewService(uow, llm), uow.session_events


# ===================== prompt 构造 =====================


class BuildReviewPromptTests(unittest.TestCase):
    """prompt 构造：要素齐全且总长度可控。"""

    def test_prompt_contains_all_elements(self) -> None:
        prompt = build_review_prompt(_GOAL, _CRITERIA, _CHANGED, _TESTS, _CASES)
        for expected in (
            _GOAL,
            _CRITERIA[0],
            _CRITERIA[1],
            *_CHANGED,
            *_TESTS,
            *_CASES,
            "任务目标",
            "验收标准",
            "改动文件",
            "测试文件",
            "测试用例名",
            '"gaps"',
            "high",
            "medium",
            "low",
        ):
            self.assertIn(expected, prompt)

    def test_prompt_stays_bounded_with_huge_inputs(self) -> None:
        prompt = build_review_prompt(
            "长" * 10_000,
            [f"标准 {i}：" + "细" * 500 for i in range(200)],
            [f"src/module_{i:03d}/file.py" for i in range(100)],
            [f"tests/test_module_{i:03d}.py" for i in range(100)],
            [f"tests/test_module_{i:03d}.py::test_case_{i}" for i in range(500)],
        )
        # 总长度有界：不随输入规模线性增长。
        self.assertLess(len(prompt), 30_000)
        # 超长条目被截断、超量条目被省略。
        self.assertIn("…", prompt)
        self.assertIn("已省略", prompt)

    def test_prompt_truncates_single_overlong_item(self) -> None:
        long_path = "src/" + "deep/" * 80 + "file.py"  # 超过单条截断上限
        prompt = build_review_prompt(_GOAL, [], [long_path], [], [])
        self.assertNotIn(long_path, prompt)
        self.assertIn("…", prompt)


# ===================== LLM 输出解析 =====================


class ParseReviewTests(unittest.TestCase):
    """LLM 输出解析：合法 / 围栏 / 垃圾，以及 adequacy 硬规则。"""

    def test_parse_plain_json(self) -> None:
        content = _review_payload(
            True,
            [
                {"area": "并发场景", "severity": "medium", "suggestion": "补充并发刷新测试"},
                {"area": "日志断言", "severity": "low", "suggestion": "可补充日志断言"},
            ],
            "总体覆盖良好",
        )
        result = parse_review(content)
        self.assertTrue(result.adequate)
        self.assertEqual(result.reviewer, "llm")
        self.assertEqual(result.reason, "总体覆盖良好")
        self.assertEqual(len(result.gaps), 2)
        self.assertEqual(result.gaps[0].area, "并发场景")
        self.assertEqual(result.gaps[0].severity, "medium")
        self.assertEqual(result.gaps[0].suggestion, "补充并发刷新测试")

    def test_parse_fenced_json(self) -> None:
        inner = _review_payload(
            False, [{"area": "超时路径", "severity": "high", "suggestion": "补充超时用例"}]
        )
        result = parse_review(f"```json\n{inner}\n```")
        self.assertFalse(result.adequate)
        self.assertEqual(result.gaps[0].area, "超时路径")

    def test_parse_json_with_surrounding_text(self) -> None:
        inner = _review_payload(True, [])
        result = parse_review(f"以下是评审结论：{inner} 评审完毕。")
        self.assertTrue(result.adequate)
        self.assertEqual(result.gaps, [])

    def test_parse_garbage_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            parse_review("我无法评估这个任务的覆盖度。")
        with self.assertRaises(ValueError):
            parse_review("```json\n{这不是 JSON\n```")

    def test_high_gap_forces_inadequate_despite_model_self_report(self) -> None:
        # 模型自报 adequate=true 但 gaps 含 high：硬规则判 inadequate（防互博）。
        content = _review_payload(
            True, [{"area": "超时路径", "severity": "high", "suggestion": "补充超时用例"}]
        )
        result = parse_review(content)
        self.assertFalse(result.adequate)

    def test_medium_only_gaps_keep_adequate(self) -> None:
        # 仅 medium/low：adequate=True，但 gaps 保留（写入审计供人看）。
        content = _review_payload(
            False,
            [
                {"area": "边界值", "severity": "medium", "suggestion": "补充边界用例"},
                {"area": "日志", "severity": "low", "suggestion": "补充日志断言"},
            ],
        )
        result = parse_review(content)
        self.assertTrue(result.adequate)
        self.assertEqual(len(result.gaps), 2)

    def test_severity_normalized_and_invalid_gaps_dropped(self) -> None:
        content = _review_payload(
            True,
            [
                {"area": "超时", "severity": "HIGH", "suggestion": "s"},  # 大小写归一
                {"area": "边界", "severity": "urgent", "suggestion": "s"},  # 非法值 → medium
                {"severity": "high", "suggestion": "s"},  # 缺 area → 丢弃
                "not a dict",  # 非 dict → 丢弃
            ],
        )
        result = parse_review(content)
        self.assertEqual([gap.severity for gap in result.gaps], ["high", "medium"])
        self.assertFalse(result.adequate)  # 归一后存在 high


# ===================== 测试用例名收集 =====================


class CollectTestCaseNamesTests(unittest.TestCase):
    """collect_test_case_names：同步/异步用例、去重、顺序。"""

    def test_collect_sync_and_async_defs(self) -> None:
        content = """
import pytest


class TestAuth:
    def test_login_success(self):
        assert True

    async def test_refresh_expired(self):
        assert True

    def helper_not_a_test(self):
        pass

    def test_login_success(self):
        pass
"""
        result = collect_test_case_names(
            {"tests/test_auth.py": content, "tests/empty.py": ""}
        )
        self.assertEqual(
            result["tests/test_auth.py"],
            ["test_login_success", "test_refresh_expired"],
        )
        self.assertEqual(result["tests/empty.py"], [])


# ===================== enforce_coverage 解析 =====================


class EnforceCoverageTests(unittest.TestCase):
    """enforce_coverage_from_plan：防御性解析 plan 的 acceptance 开关。"""

    def test_enforce_flag_parsing(self) -> None:
        self.assertTrue(
            enforce_coverage_from_plan({"acceptance": {"enforce_coverage": True}})
        )
        self.assertFalse(enforce_coverage_from_plan(_make_plan()))
        self.assertFalse(
            enforce_coverage_from_plan({"acceptance": {"enforce_coverage": "true"}})
        )
        self.assertFalse(
            enforce_coverage_from_plan({"acceptance": {"enforce_coverage": False}})
        )
        self.assertFalse(enforce_coverage_from_plan({"acceptance": "pytest -q"}))


# ===================== 应用服务 =====================


class CoverageReviewServiceTests(unittest.IsolatedAsyncioTestCase):
    """CoverageReviewService：失败开放 + 审计事件 + enforce 语义。"""

    async def test_llm_missing_skips_fail_open(self) -> None:
        service, sink = _make_service(None)
        result = await service.review(
            _SESSION_ID, _RUN_ID, _make_plan(), _CHANGED, _TESTS, _CASES
        )
        self.assertTrue(result.adequate)
        self.assertEqual(result.reviewer, "skipped")
        self.assertEqual(result.reason, "llm unavailable")
        # 降级也要留审计痕迹。
        self.assertEqual(len(sink.events), 1)
        event_type, payload = sink.events[0]
        self.assertIs(event_type, SessionEventType.coverage_review_finished)
        self.assertTrue(payload["adequate"])
        self.assertEqual(payload["reviewer"], "skipped")

    async def test_llm_not_configured_skips(self) -> None:
        service, _ = _make_service(FakeLLM(configured=False))
        result = await service.review(_SESSION_ID, _RUN_ID, _make_plan(), [], [], [])
        self.assertEqual(result.reviewer, "skipped")
        self.assertTrue(result.adequate)

    async def test_llm_exception_skips_fail_open(self) -> None:
        service, _ = _make_service(FakeLLM(error=RuntimeError("network down")))
        result = await service.review(_SESSION_ID, _RUN_ID, _make_plan(), [], [], [])
        self.assertEqual(result.reviewer, "skipped")
        self.assertTrue(result.adequate)
        self.assertEqual(result.reason, "llm unavailable")

    async def test_parse_failure_skips_fail_open(self) -> None:
        service, _ = _make_service(FakeLLM(content="抱歉，我无法输出 JSON。"))
        result = await service.review(_SESSION_ID, _RUN_ID, _make_plan(), [], [], [])
        self.assertEqual(result.reviewer, "skipped")
        self.assertTrue(result.adequate)
        self.assertEqual(result.reason, "llm unavailable")

    async def test_disabled_config_skips_without_llm_call(self) -> None:
        llm = FakeLLM(content=_review_payload(True, []))
        service, sink = _make_service(llm)
        with patch.object(settings, "coverage_review_enabled", False):
            result = await service.review(_SESSION_ID, _RUN_ID, _make_plan(), [], [], [])
        self.assertEqual(result.reviewer, "skipped")
        self.assertTrue(result.adequate)
        self.assertEqual(llm.prompts, [])  # 配置关闭时不调用 LLM
        self.assertEqual(len(sink.events), 1)  # 仍写审计事件

    async def test_prompt_carrying_plan_inputs(self) -> None:
        llm = FakeLLM(content=_review_payload(True, [], "ok"))
        service, _ = _make_service(llm)
        await service.review(_SESSION_ID, _RUN_ID, _make_plan(), _CHANGED, _TESTS, _CASES)
        self.assertEqual(len(llm.prompts), 1)
        prompt = llm.prompts[0]
        self.assertIn(_GOAL, prompt)
        self.assertIn(_CRITERIA[0], prompt)
        self.assertIn(_CHANGED[0], prompt)
        self.assertIn(_TESTS[1], prompt)
        self.assertIn(_CASES[1], prompt)

    async def test_audit_event_truncates_gaps(self) -> None:
        gaps = [
            {"area": f"领域{i}", "severity": "medium", "suggestion": f"建议{i}"}
            for i in range(5)
        ]
        llm = FakeLLM(content=_review_payload(True, gaps, "ok"))
        service, sink = _make_service(llm)
        with patch.object(settings, "coverage_review_max_gaps_in_event", 2):
            result = await service.review(_SESSION_ID, _RUN_ID, _make_plan(), [], [], [])
        self.assertEqual(len(result.gaps), 5)  # 运行期结果保留完整 gaps
        _, payload = sink.events[0]
        self.assertEqual(payload["gap_count"], 5)
        self.assertEqual(len(payload["gaps"]), 2)  # 事件内按配置截断

    async def test_enforce_false_inadequate_does_not_trigger_retry(self) -> None:
        gaps = [{"area": "超时路径", "severity": "high", "suggestion": "补充超时用例"}]
        llm = FakeLLM(content=_review_payload(False, gaps, "覆盖不足"))
        service, sink = _make_service(llm)
        plan = _make_plan()  # 未声明 enforce_coverage
        result = await service.review(_SESSION_ID, _RUN_ID, plan, [], [], [])
        self.assertFalse(result.adequate)
        # 评审只做建议不阻断：不触发与 T1/T2 共用的重试路径。
        self.assertFalse(should_retry(plan, result))
        _, payload = sink.events[0]
        self.assertFalse(payload["enforce_coverage"])

    async def test_enforce_true_inadequate_triggers_retry_with_high_gaps_reason(self) -> None:
        gaps = [
            {"area": "超时路径", "severity": "high", "suggestion": "补充超时用例"},
            {"area": "边界值", "severity": "medium", "suggestion": "补充边界用例"},
        ]
        llm = FakeLLM(content=_review_payload(False, gaps, "覆盖不足"))
        service, sink = _make_service(llm)
        plan = _make_plan(acceptance={"enforce_coverage": True})
        result = await service.review(_SESSION_ID, _RUN_ID, plan, [], [], [])
        self.assertFalse(result.adequate)
        self.assertTrue(should_retry(plan, result))
        # reason 列出 high gaps（供重试路径引用），medium 不列入。
        self.assertIn("超时路径", result.reason)
        self.assertIn("补充超时用例", result.reason)
        self.assertNotIn("边界值", result.reason)
        _, payload = sink.events[0]
        self.assertTrue(payload["enforce_coverage"])

    async def test_event_write_failure_does_not_block(self) -> None:
        llm = FakeLLM(content=_review_payload(True, [], "ok"))
        uow = FakeUnitOfWork()
        uow.session_events.error = RuntimeError("db down")
        service = CoverageReviewService(uow, llm)
        result = await service.review(_SESSION_ID, _RUN_ID, _make_plan(), [], [], [])
        self.assertEqual(result.reviewer, "llm")
        self.assertTrue(result.adequate)


if __name__ == "__main__":
    unittest.main()
