import re
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from app.domain.memories.entities import (
    MemoryAuthority,
    MemoryCandidate,
    MemoryKind,
    MemoryScope,
    MemorySensitivity,
    MemoryStatus,
    MemoryWriteDecision,
)


class MemoryWriteGate:
    """把模型提案与可持久、可检索的长期事实隔离开。

    门禁只保存可观察的判定依据，不保存模型隐藏推理。所有通过为
    ``verified`` 的记忆都必须有来源，并满足类型对应的验证规则。
    """

    _SECRET_PATTERNS = (
        re.compile(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*[^\s,;]+"),
        re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    )

    def evaluate(
        self,
        candidate: MemoryCandidate,
        *,
        requested_status: MemoryStatus = MemoryStatus.candidate,
        now: datetime | None = None,
    ) -> MemoryWriteDecision:
        current_time = now or datetime.now(UTC)
        clean_content, redactions = self._redact(candidate.content)
        normalized = replace(candidate, content=clean_content.strip())
        reasons: list[str] = []

        if not normalized.content:
            reasons.append("正文为空或仅包含被拒绝的敏感信息。")
        if normalized.sensitivity is MemorySensitivity.secret:
            reasons.append("secret 级信息禁止进入长期记忆。")
        scope_bound = self._scope_is_bound(normalized)
        if not scope_bound:
            reasons.append("作用域缺少对应的 session/task/project/user 标识。")

        target_status = MemoryStatus.candidate
        if requested_status is MemoryStatus.verified:
            reasons.extend(self._verification_failures(normalized))
            if not reasons:
                target_status = MemoryStatus.verified

        if normalized.kind is MemoryKind.environment:
            if normalized.ttl_seconds is None:
                normalized.ttl_seconds = 3600
            if normalized.valid_to is None:
                normalized.valid_to = current_time + timedelta(
                    seconds=normalized.ttl_seconds
                )

        normalized.status = target_status
        normalized.valid_from = normalized.valid_from or current_time
        accepted = (
            bool(normalized.content)
            and normalized.sensitivity is not MemorySensitivity.secret
            and scope_bound
        )
        if accepted and target_status is MemoryStatus.candidate and requested_status is MemoryStatus.verified:
            reasons.append("验证条件不足，已降级为 candidate。")
        if redactions:
            reasons.append(f"持久化前已脱敏 {redactions} 处。")
        if accepted and not reasons:
            reasons.append("来源、作用域、有效期与验证规则均通过。")

        return MemoryWriteDecision(
            candidate=normalized,
            accepted=accepted,
            target_status=target_status,
            reasons=reasons,
            redactions=redactions,
        )

    @staticmethod
    def _scope_is_bound(candidate: MemoryCandidate) -> bool:
        if candidate.scope is MemoryScope.session:
            return candidate.source_session_id is not None
        if candidate.scope is MemoryScope.task:
            return candidate.task_id is not None or candidate.source_session_id is not None
        if candidate.scope is MemoryScope.project:
            return bool(candidate.project_id) or candidate.source_session_id is not None
        if candidate.scope is MemoryScope.user:
            return bool(candidate.user_id) or candidate.authority is MemoryAuthority.explicit_user
        return bool(candidate.metadata.get("organization_id"))

    @staticmethod
    def _verification_failures(candidate: MemoryCandidate) -> list[str]:
        failures: list[str] = []
        if not candidate.provenance:
            failures.append("verified 记忆必须至少引用一个事件或制品。")
        if candidate.authority is MemoryAuthority.agent_inferred:
            failures.append("Agent 推测不能直接晋升为 verified。")
        if candidate.kind is MemoryKind.bug_lesson:
            evidence = candidate.verification.get("evidence", [])
            tests = candidate.verification.get("tests", [])
            if not evidence or not tests:
                failures.append("bug_lesson 必须包含复现/修复证据和通过的测试。")
        if candidate.kind is MemoryKind.code_fact:
            required = {"repo_id", "git_commit_sha", "file_path", "content_hash"}
            if not required.issubset(candidate.verification):
                failures.append("code_fact 缺少稳定代码定位字段。")
        return failures

    @classmethod
    def _redact(cls, content: str) -> tuple[str, int]:
        redacted = content
        count = 0
        for pattern in cls._SECRET_PATTERNS:
            redacted, replacements = pattern.subn("[REDACTED]", redacted)
            count += replacements
        return redacted, count
