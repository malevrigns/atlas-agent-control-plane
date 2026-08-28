"""范围审计应用服务：两级审计（规则层 + LLM 复核）并持久化审计事件。

- 规则层必跑：ScopePolicy.check 判定文件是否命中 allowed / forbidden；
- LLM 复核在两种条件下触发：plan 的 scope.llm_review 为 true，
  或规则层内存在体积异常的 allowed 文件（单文件变更行数超阈值）；
- LLM 复核失败（调用异常 / 返回非 JSON）时降级为只信规则层结果；
- 审计结果写入 scope_audit_finished 审计事件（审计留痕）。
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Mapping, Protocol
from uuid import UUID

from app.application.llm_service import LLMService
from app.application.unit_of_work import UnitOfWork
from app.core.config import settings
from app.domain.acceptance.scope import (
    FileChange,
    ScopeAuditResult,
    ScopePolicy,
    collect_changes,
)
from app.domain.llm.entities import LLMMessage
from app.domain.sessions.entities import SessionEventType

logger = logging.getLogger(__name__)

# 发给 LLM 的 diff 摘要中，每个文件最多保留的行数。
DIFF_DIGEST_LINES_PER_FILE = 40
# diff 摘要总字符上限，防止上下文爆炸。
DIFF_DIGEST_MAX_CHARS = 12_000

# LLM 复核提示词：要求严格返回 JSON，便于程序化解析。
_SCOPE_AUDIT_SYSTEM_PROMPT = (
    "你是代码改动范围审计员。任务计划声明了允许改动的文件范围（allowed globs）"
    "与禁止改动的范围（forbidden globs）。下面给出本次任务的文件变更统计（numstat）、"
    "规则层已判定的违规文件，以及每个文件的 diff 摘要（每文件最多前 40 行）。\n"
    "请判断改动是否都在计划范围内，并只输出一个 JSON 对象，不要输出任何其他文字：\n"
    '{"in_scope": bool, "violations": [{"path": "...", "reason": "..."}], "reason": "..."}\n'
    "violations 只列越界文件并给出简短原因；in_scope 为 true 时 violations 必须为空数组。"
)


class DiffProvider(Protocol):
    """提供工作区 diff 文本（numstat + 全量 diff）。

    生产实现为 GitDiffProvider（infrastructure 层，子进程调用 git）；
    测试可注入假实现。workspace_dir 为空时回退到实现自身绑定的目录。
    """

    async def diff(self, workspace_dir: str = "") -> str: ...


class ScopeAuditorProtocol(Protocol):
    """可插拔的范围审计接口（状态机 summarize 前审计点 / T1 验收门禁共用契约）。

    状态机与验收门禁都依赖本协议，测试可用协议桩替换真实服务。
    """

    async def audit(
        self,
        session_id: UUID,
        run_id: UUID,
        plan: Mapping[str, object],
        diff_text: str,
    ) -> ScopeAuditResult: ...


def _change_payload(change: FileChange) -> dict[str, object]:
    """FileChange 的事件 payload 表示。"""
    return {
        "path": change.path,
        "change_type": change.change_type,
        "additions": change.additions,
        "deletions": change.deletions,
    }


def _scope_payload(plan: Mapping[str, object]) -> dict[str, object]:
    """取出 plan 的 scope 字段用于 LLM 提示词；缺失时返回空对象。"""
    scope = plan.get("scope")
    if isinstance(scope, Mapping):
        return dict(scope)
    return {}


def _plan_id(plan: Mapping[str, object]) -> str | None:
    value = plan.get("id") or plan.get("plan_id")
    return str(value) if value is not None else None


def _strip_code_fences(text: str) -> str:
    """去掉 LLM 回复外围的 markdown 代码块围栏。"""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines)
    return stripped


def parse_scope_audit_response(text: str) -> dict[str, object] | None:
    """把 LLM 的范围审计回复解析为结构化 dict；解析失败返回 None（调用方降级）。

    容忍代码块包裹与前后多余文本：截取第一个 '{' 到最后一个 '}' 之间的
    子串再解析，并校验 in_scope 必须是布尔、violations 必须是列表。
    """
    cleaned = _strip_code_fences(text)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        parsed = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("in_scope"), bool):
        return None
    raw_violations = parsed.get("violations")
    if not isinstance(raw_violations, list):
        return None
    violations = [
        item
        for item in raw_violations
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    ]
    return {
        "in_scope": parsed["in_scope"],
        "violations": violations,
        "reason": str(parsed.get("reason") or ""),
    }


def build_diff_digest(
    diff_text: str,
    lines_per_file: int = DIFF_DIGEST_LINES_PER_FILE,
    max_chars: int = DIFF_DIGEST_MAX_CHARS,
) -> str:
    """构造发给 LLM 的 diff 摘要：全量 diff 段中每个文件取前 lines_per_file 行。

    输入不含全量 diff（仅 numstat）时，退化为 numstat 行摘要，
    保证模型在退化工况下仍可给出判断。
    """
    sections: list[list[str]] = []
    current: list[str] = []
    for line in diff_text.splitlines():
        if line.startswith("diff --git"):
            if current:
                sections.append(current)
            current = [line]
            continue
        if current:
            current.append(line)
    if current:
        sections.append(current)

    if not sections:
        head = [
            line
            for line in diff_text.splitlines()
            if line.strip() and not line.startswith("diff --git")
        ][: lines_per_file * 4]
        return "\n".join(head)[:max_chars]

    parts: list[str] = []
    total = 0
    for section in sections:
        kept = section[:lines_per_file]
        omitted = len(section) - len(kept)
        part = "\n".join(kept)
        if omitted > 0:
            part += f"\n...（其余 {omitted} 行省略）"
        parts.append(part)
        total += len(part) + 2
        if total >= max_chars:
            break
    return "\n\n".join(parts)[:max_chars]


class ScopeAuditService:
    """两级范围审计服务（实现 ScopeAuditorProtocol）。

    构造参数：
    - uow：审计事件写入通道（uow.session_events）；
    - llm_service：LLM 复核通道；
    - policy_provider：plan -> ScopePolicy | None 的工厂，
      默认 ScopePolicy.from_plan（plan 无 scope 字段返回 None 即跳过审计）；
    - llm_review_threshold：单文件变更行数阈值，None 时读
      settings.scope_audit_llm_review_threshold；
    - write_audit_event：是否由本服务写 scope_audit_finished 事件。
      独立调用时缺省 True；被状态机驱动时（审计事件由状态机统一写入，
      与验收门禁一致）应置为 False，避免重复审计事件。
    """

    def __init__(
        self,
        uow: UnitOfWork,
        llm_service: LLMService,
        policy_provider: Callable[[Mapping[str, object]], ScopePolicy | None] | None = None,
        *,
        llm_review_threshold: int | None = None,
        write_audit_event: bool = True,
    ) -> None:
        self._uow = uow
        self._llm_service = llm_service
        self._policy_provider = policy_provider or ScopePolicy.from_plan
        self._llm_review_threshold = (
            settings.scope_audit_llm_review_threshold
            if llm_review_threshold is None
            else llm_review_threshold
        )
        self._write_audit_event = write_audit_event

    async def audit(
        self,
        session_id: UUID,
        run_id: UUID,
        plan: Mapping[str, object],
        diff_text: str,
    ) -> ScopeAuditResult:
        """执行范围审计并写审计事件，返回审计结果。"""
        policy = self._policy_provider(plan)
        changes = collect_changes(diff_text)
        if policy is None:
            # plan 无 scope 字段：跳过审计（向后兼容旧计划）。
            result = ScopeAuditResult(
                in_scope=True,
                violations=[],
                checked_files=len(changes),
                reviewer="rules",
                reason="计划未声明 scope 字段，跳过范围审计。",
            )
        else:
            result = await self._run_two_tier_audit(plan, policy, changes, diff_text)
        if self._write_audit_event:
            await self._write_scope_event(session_id, run_id, plan, result)
        return result

    # ===================== 两级审计 =====================

    async def _run_two_tier_audit(
        self,
        plan: Mapping[str, object],
        policy: ScopePolicy,
        changes: list[FileChange],
        diff_text: str,
    ) -> ScopeAuditResult:
        """① 规则层必跑；② 触发条件满足时 LLM 复核，失败降级规则层。"""
        rule_violations = policy.check(changes)
        rule_reason = (
            "未检测到越界文件变更。"
            if not rule_violations
            else "越界文件变更: " + ", ".join(v.path for v in rule_violations)
        )
        rule_only = ScopeAuditResult(
            in_scope=not rule_violations,
            violations=rule_violations,
            checked_files=len(changes),
            reviewer="rules",
            reason=rule_reason,
        )
        if not self._needs_llm_review(plan, changes, rule_violations):
            return rule_only

        llm_parsed = await self._llm_review(plan, changes, diff_text, rule_violations)
        if llm_parsed is None:
            # LLM 复核不可用（调用失败或解析失败）：降级为只信规则层。
            rule_only.reason += " | LLM 复核失败或未返回合法 JSON，降级为仅规则层结论。"
            return rule_only

        merged = self._merge_violations(rule_violations, llm_parsed)
        llm_reason = str(llm_parsed.get("reason") or "")
        reason = (
            "未检测到越界文件变更。"
            if not merged
            else "越界文件变更: " + ", ".join(v.path for v in merged)
        )
        if llm_reason:
            reason += f" | LLM: {llm_reason}"
        return ScopeAuditResult(
            in_scope=not merged,
            violations=merged,
            checked_files=len(changes),
            reviewer="rules+llm",
            reason=reason,
        )

    def _needs_llm_review(
        self,
        plan: Mapping[str, object],
        changes: list[FileChange],
        rule_violations: list[FileChange],
    ) -> bool:
        """LLM 复核触发条件：scope.llm_review 为 true，或存在体积异常的 allowed 文件。"""
        scope = plan.get("scope")
        if isinstance(scope, Mapping) and scope.get("llm_review") is True:
            return True
        violated = {v.path for v in rule_violations}
        return any(
            change.path not in violated
            and change.total_lines > self._llm_review_threshold
            for change in changes
        )

    async def _llm_review(
        self,
        plan: Mapping[str, object],
        changes: list[FileChange],
        diff_text: str,
        rule_violations: list[FileChange],
    ) -> dict[str, object] | None:
        """把 diff 摘要发给模型复核；调用失败或解析失败返回 None（由调用方降级）。"""
        digest = build_diff_digest(diff_text)
        user_prompt = (
            "计划范围声明: "
            f"{json.dumps(_scope_payload(plan), ensure_ascii=False)}\n"
            "文件变更统计: "
            f"{json.dumps([_change_payload(c) for c in changes], ensure_ascii=False)}\n"
            "规则层已判定违规: "
            f"{json.dumps([c.path for c in rule_violations], ensure_ascii=False)}\n"
            f"diff 摘要:\n{digest}"
        )
        messages = [
            LLMMessage(role="system", content=_SCOPE_AUDIT_SYSTEM_PROMPT),
            LLMMessage(role="user", content=user_prompt),
        ]
        try:
            chat_result = await self._llm_service.chat(messages, temperature=0)
        except Exception:
            logger.exception("范围审计 LLM 复核调用失败，降级为规则层结论")
            return None
        return parse_scope_audit_response(chat_result.content)

    @staticmethod
    def _merge_violations(
        rule_violations: list[FileChange],
        llm_parsed: Mapping[str, object],
    ) -> list[FileChange]:
        """合并两层违规：规则层违规在前，LLM 额外发现的后补（按 path 去重）。

        LLM 只给出 path 与原因，没有行数统计，统一记为 modified（0/0）。
        """
        merged = list(rule_violations)
        known = {v.path for v in merged}
        for item in llm_parsed.get("violations", []):  # type: ignore[union-attr]
            path = str(item.get("path", "")).strip()
            if not path or path in known:
                continue
            merged.append(
                FileChange(path=path, change_type="modified", additions=0, deletions=0)
            )
            known.add(path)
        return merged

    # ===================== 审计事件 =====================

    async def _write_scope_event(
        self,
        session_id: UUID,
        run_id: UUID,
        plan: Mapping[str, object],
        result: ScopeAuditResult,
    ) -> None:
        """把审计结果落库为 scope_audit_finished 审计事件。

        事件写入失败不阻断任务（审计是护栏而非主流程），仅记录日志。
        """
        payload = {
            "run_id": str(run_id),
            "plan_id": _plan_id(plan),
            "in_scope": result.in_scope,
            "reviewer": result.reviewer,
            "checked_files": result.checked_files,
            "violations": [_change_payload(v) for v in result.violations],
            "reason": result.reason,
        }
        try:
            await self._uow.session_events.add(
                session_id=session_id,
                event_type=SessionEventType.scope_audit_finished,
                payload=payload,
            )
        except Exception:
            logger.exception("范围审计事件写入失败")
