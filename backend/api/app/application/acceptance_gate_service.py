"""验收门禁（Acceptance Gate）应用服务。

编排 domain 层的 AcceptanceGate：
1. 从 plan payload 解析 acceptance 配置（向后兼容：老计划没有该字段则跳过）；
2. 执行验收命令；
3. 把执行与结果写成会话审计事件（acceptance_gate_started /
   acceptance_gate_finished），供事件流回放与排查。
"""

from collections.abc import Mapping
from uuid import UUID

from app.application.agent_execution_types import EventSink
from app.application.unit_of_work import UnitOfWork
from app.domain.acceptance.gate import (
    AcceptanceGateConfig,
    AcceptanceGateProtocol,
    AcceptanceGateResult,
)
from app.domain.sessions.entities import SessionEventType


def gate_config_from_plan(
    plan: Mapping[str, object], default_timeout_seconds: int = 600
) -> AcceptanceGateConfig | None:
    """从 plan payload 读取 acceptance 门禁配置。

    约定格式：
        {"acceptance": {"command": "pytest -q", "timeout_seconds": 600,
                         "working_dir": "", "success_exit_codes": [0]}}

    向后兼容：plan 没有 acceptance 字段（老计划）或 command 缺失/为空时
    返回 None，表示不执行门禁。
    """
    raw = plan.get("acceptance")
    if not isinstance(raw, Mapping):
        return None
    command = raw.get("command")
    if not isinstance(command, str) or not command.strip():
        return None
    timeout = raw.get("timeout_seconds")
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
        timeout = default_timeout_seconds
    working_dir = raw.get("working_dir")
    working = working_dir.strip() if isinstance(working_dir, str) else ""
    success_raw = raw.get("success_exit_codes")
    if isinstance(success_raw, (list, tuple)):
        success_codes = tuple(
            code
            for code in success_raw
            if isinstance(code, int) and not isinstance(code, bool)
        )
    else:
        success_codes = ()
    if not success_codes:
        success_codes = (0,)
    return AcceptanceGateConfig(
        command=command.strip(),
        timeout_seconds=timeout,
        success_exit_codes=success_codes,
        working_dir=working,
    )


class AcceptanceGateService:
    """验收门禁应用服务：执行门禁并写审计事件。

    依赖注入：
    - uow：工作单元（事件写入器缺省取 uow.session_events）；
    - gate：领域门禁（AcceptanceGateProtocol），真正执行验收命令；
    - event_writer：事件写入器（EventSink），缺省回落到 uow.session_events。
    """

    def __init__(
        self,
        uow: UnitOfWork,
        gate: AcceptanceGateProtocol,
        event_writer: EventSink | None = None,
    ) -> None:
        self._uow = uow
        self._gate = gate
        self._event_writer = event_writer or uow.session_events

    async def run_gate(
        self,
        session_id: UUID,
        run_id: UUID,
        plan: Mapping[str, object],
        config: AcceptanceGateConfig | None = None,
    ) -> AcceptanceGateResult:
        """执行验收门禁，并写 acceptance_gate_started/finished 审计事件。

        config 为 None 时从 plan 解析；两者都没有 acceptance 配置则跳过门禁，
        返回"通过"结果（向后兼容：老计划没有 acceptance 字段时不执行门禁）。
        """
        if config is None:
            config = gate_config_from_plan(plan)
        if config is None:
            return AcceptanceGateResult(
                passed=True,
                exit_code=None,
                command="",
                output_digest="",
                duration_ms=0,
                reason="plan 未配置 acceptance，跳过验收门禁",
            )
        identity = self._identity(plan, run_id)
        await self._event_writer.add(
            session_id=session_id,
            event_type=SessionEventType.acceptance_gate_started,
            payload={
                **identity,
                "command": config.command,
                "timeout_seconds": config.timeout_seconds,
                "working_dir": config.working_dir,
            },
        )
        result = await self._gate.verify(config)
        await self._event_writer.add(
            session_id=session_id,
            event_type=SessionEventType.acceptance_gate_finished,
            payload={
                **identity,
                "command": config.command,
                "exit_code": result.exit_code,
                "passed": result.passed,
                "output_digest": result.output_digest,
                "duration_ms": result.duration_ms,
                "reason": result.reason,
            },
        )
        return result

    @staticmethod
    def _identity(plan: Mapping[str, object], run_id: UUID) -> dict[str, object]:
        """事件 payload 的身份字段：plan/run/revision 三元组。"""
        plan_id = plan.get("id") or plan.get("plan_id")
        return {
            "plan_id": str(plan_id) if plan_id is not None else None,
            "run_id": str(run_id),
            "plan_revision": plan.get("plan_revision", 0),
        }
