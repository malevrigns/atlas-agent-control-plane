"""覆盖度评审（Coverage Review）应用服务。

任务完成的第三个门禁：在任务进入 summarize 之前，让 LLM 对照任务目标
与验收标准，判断测试用例是否完整覆盖了任务要求（"该测的都测了"）。

失败开放约定（与 RAG 重排降级同一哲学）：
覆盖评审是**增强项**，LLM 不可用 / 调用失败 / 输出解析失败一律降级为
``CoverageReviewResult(adequate=True, reviewer="skipped",
reason="llm unavailable")``，绝不抛异常、绝不阻塞主链路。
只有当 plan 显式声明 ``acceptance.enforce_coverage: true`` 时，
adequate=False（由 domain 硬规则判定，即存在 high gap）才会触发
与 T1/T2 验收门禁共用的重试路径（reason 列出 high gaps）。

独立可插拔（与 T1/T4 相同的接入点，由 _summarize_node 前的门禁链调用）：

    machine = AgentExecutionMachine(
        ...,
        acceptance_gate=AcceptanceGateService(...),           # T1
        scope_auditor=ScopeAuditService(...),                 # T4
        coverage_reviewer=CoverageReviewService(uow, llm),    # T3（本服务）
    )

接线说明（_summarize_node 内、真正 summarize 之前调用）：

    reviewer = machine 注入的 CoverageReviewerProtocol
    result = await reviewer.review(
        state.session_id, state.run_id, snapshot.plan,
        changed_files,        # 调用方用 git diff --name-only 收集
        test_files,           # 改动/既有的测试文件路径
        test_case_names,      # collect_test_case_names 展开后的用例名
    )
    if should_retry(snapshot.plan, result):
        # 进入与 T1/T2 共用的重试路径（result.reason 已列出 high gaps）
        ...
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Protocol
from uuid import UUID

from app.application.llm_service import LLMService
from app.application.unit_of_work import UnitOfWork
from app.core.config import settings
from app.domain.acceptance.coverage import (
    LLM_UNAVAILABLE_REASON,
    REVIEWER_SKIPPED,
    CoverageReviewResult,
    build_review_prompt,
    parse_review,
)
from app.domain.llm.entities import LLMMessage
from app.domain.sessions.entities import SessionEventType

logger = logging.getLogger(__name__)


# ===================== 第1步：plan 字段解析（防御性） =====================


def enforce_coverage_from_plan(plan: Mapping[str, object]) -> bool:
    """读取 plan 的 ``acceptance.enforce_coverage`` 开关（防御性解析）。

    约定格式：``{"acceptance": {"enforce_coverage": true}}``（与 T1 的
    acceptance.command 同挂 acceptance 字段下）。
    字段缺失 / 非 Mapping / 值非布尔 true 一律按 False 处理：
    评审默认只做建议不阻断。
    """
    acceptance = plan.get("acceptance")
    if not isinstance(acceptance, Mapping):
        return False
    value = acceptance.get("enforce_coverage")
    return isinstance(value, bool) and value


def should_retry(plan: Mapping[str, object], result: CoverageReviewResult) -> bool:
    """是否进入与 T1/T2 共用的重试路径。

    仅当 plan 声明 enforce_coverage=true **且**评审结论 inadequate
    （domain 硬规则判定，即存在 high gap）时才返回 True；
    否则评审只是建议，不阻断主链路。
    降级结果（reviewer="skipped"）恒为 adequate=True，天然不触发重试。
    """
    return enforce_coverage_from_plan(plan) and not result.adequate


# ===================== 第2步：可插拔协议（门禁链契约） =====================


class CoverageReviewerProtocol(Protocol):
    """可插拔的覆盖度评审接口（状态机 summarize 前门禁链契约）。

    状态机与门禁链依赖本协议，测试可用协议桩替换真实服务。
    """

    async def review(
        self,
        session_id: UUID,
        run_id: UUID,
        plan: Mapping[str, object],
        changed_files: list[str],
        test_files: list[str],
        test_case_names: list[str],
    ) -> CoverageReviewResult: ...


# ===================== 第3步：内部工具 =====================


def _plan_text(plan: Mapping[str, object], key: str) -> str:
    """取 plan 的字符串字段（缺失/非字符串时返回空串）。"""
    value = plan.get(key)
    return str(value).strip() if value is not None else ""


def _plan_criteria(plan: Mapping[str, object]) -> list[str]:
    """取 plan 的验收标准清单（防御性：只接受字符串列表，过滤空项）。"""
    raw = plan.get("acceptance_criteria")
    if not isinstance(raw, (list, tuple)):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def _reason_with_high_gaps(result: CoverageReviewResult) -> str:
    """inadequate 时组装 reason：列出 high gaps（作为重试路径的输入说明）。"""
    high = [gap for gap in result.gaps if gap.severity == "high"]
    detail = "; ".join(
        f"{gap.area}：{gap.suggestion}" if gap.suggestion else gap.area for gap in high
    )
    reason = f"覆盖度不足，高风险缺口：{detail}"
    if result.reason:
        reason += f" | LLM: {result.reason}"
    return reason


# ===================== 第4步：覆盖度评审服务 =====================


class CoverageReviewService:
    """覆盖度评审服务（实现 CoverageReviewerProtocol）。

    构造参数：
    - uow：工作单元（审计事件写入通道取 uow.session_events）；
    - llm_service：LLM 评审通道（None 或未配置密钥 → 降级 skipped）；
    - event_writer：事件写入器，缺省回落到 uow.session_events。
    """

    def __init__(
        self,
        uow: UnitOfWork,
        llm_service: LLMService | None,
        event_writer=None,
    ) -> None:
        self._uow = uow
        self._llm_service = llm_service
        self._event_writer = event_writer or uow.session_events

    async def review(
        self,
        session_id: UUID,
        run_id: UUID,
        plan: Mapping[str, object],
        changed_files: list[str],
        test_files: list[str],
        test_case_names: list[str],
    ) -> CoverageReviewResult:
        """执行覆盖度评审并写 coverage_review_finished 审计事件。

        失败开放：配置关闭 / LLM 不可用 / 调用失败 / 解析失败一律降级为
        skipped + adequate=True，本方法不抛异常，不阻塞 summarize 主链路。
        """
        if not settings.coverage_review_enabled:
            result = self._skip("coverage 评审已关闭")
        else:
            result = await self._run_review(
                plan, changed_files, test_files, test_case_names
            )
        await self._write_finished_event(session_id, run_id, plan, result)
        return result

    # ===================== 评审主流程 =====================

    async def _run_review(
        self,
        plan: Mapping[str, object],
        changed_files: list[str],
        test_files: list[str],
        test_case_names: list[str],
    ) -> CoverageReviewResult:
        """构造 prompt → LLM 评审 → 解析；任何失败都降级为 skipped。"""
        goal = _plan_text(plan, "goal") or _plan_text(plan, "title")
        criteria = _plan_criteria(plan)
        prompt = build_review_prompt(
            goal, criteria, changed_files, test_files, test_case_names
        )

        llm = self._llm_service
        if llm is None or not llm.is_configured():
            return self._skip(LLM_UNAVAILABLE_REASON)
        try:
            chat_result = await llm.chat(
                [LLMMessage(role="user", content=prompt)], temperature=0
            )
        except Exception:
            logger.exception("覆盖度评审 LLM 调用失败，降级 skipped（失败开放）")
            return self._skip(LLM_UNAVAILABLE_REASON)

        try:
            result = parse_review(chat_result.content)
        except ValueError as exc:
            logger.warning("覆盖度评审输出解析失败，降级 skipped（失败开放）：%s", exc)
            return self._skip(LLM_UNAVAILABLE_REASON)

        # inadequate 时把 reason 重写为 high gaps 清单（重试路径直接引用）。
        if not result.adequate:
            result.reason = _reason_with_high_gaps(result)
        return result

    @staticmethod
    def _skip(reason: str) -> CoverageReviewResult:
        """降级结果：失败开放，adequate=True，永不阻断主链路。"""
        return CoverageReviewResult(
            adequate=True, gaps=[], reviewer=REVIEWER_SKIPPED, reason=reason
        )

    # ===================== 审计事件 =====================

    async def _write_finished_event(
        self,
        session_id: UUID,
        run_id: UUID,
        plan: Mapping[str, object],
        result: CoverageReviewResult,
    ) -> None:
        """把评审结果落库为 coverage_review_finished 审计事件。

        事件写入失败不阻断任务（评审是增强项而非主流程），仅记录日志。
        payload 中 gaps 按 settings.coverage_review_max_gaps_in_event 截断，
        防止审计事件膨胀（完整 gaps 仍在运行期结果对象中）。
        """
        plan_id = plan.get("id") or plan.get("plan_id")
        payload: dict[str, object] = {
            "plan_id": str(plan_id) if plan_id is not None else None,
            "run_id": str(run_id),
            "plan_revision": plan.get("plan_revision", 0),
            "adequate": result.adequate,
            "reviewer": result.reviewer,
            "reason": result.reason,
            "enforce_coverage": enforce_coverage_from_plan(plan),
            "gap_count": len(result.gaps),
            "gaps": [
                {"area": gap.area, "severity": gap.severity, "suggestion": gap.suggestion}
                for gap in result.gaps[: settings.coverage_review_max_gaps_in_event]
            ],
        }
        try:
            await self._event_writer.add(
                session_id=session_id,
                event_type=SessionEventType.coverage_review_finished,
                payload=payload,
            )
        except Exception:
            logger.exception("覆盖度评审事件写入失败（不阻断任务）")
