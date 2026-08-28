from collections.abc import AsyncIterator, Mapping
from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

from app.application.acceptance_gate_service import gate_config_from_plan
from app.application.agent_execution_event_writer import (
    add_done_event,
    add_failure_event,
    add_plan_event,
    add_reflected_event,
    add_terminal_event,
    plan_id,
)
from app.application.agent_execution_types import (
    AgentExecutionContext,
    Critic,
    EventSink,
    MachineSnapshot,
    NodeTransition,
    Replanner,
    StepExecutor,
    StreamItem,
    Summarizer,
    plan_revision,
)
from app.application.agent_summary_service import AgentSummaryRequest, AgentSummaryResult
from app.application.coverage_review_service import (
    CoverageReviewerProtocol,
    enforce_coverage_from_plan,
    should_retry,
)
from app.application.react_step_executor import StepExecutionRequest
from app.application.scope_audit_service import DiffProvider, ScopeAuditorProtocol
from app.core.config import settings
from app.core.exceptions import AppException, ErrorSource
from app.domain.acceptance.coverage import CoverageReviewResult, collect_test_case_names
from app.domain.acceptance.gate import (
    AcceptanceGateConfig,
    AcceptanceGateProtocol,
    AcceptanceGateResult,
)
from app.domain.acceptance.scope import ScopeAuditResult, ScopePolicy, collect_changes
from app.domain.agent_runtime.entities import (
    AgentPhase,
    AgentRunState,
    Reflection,
    ReflectionAction,
)
from app.domain.agent_runtime.router import AgentStateRouter
from app.domain.sessions.entities import SessionEvent, SessionEventType


# ===================== 覆盖度评审输入安全上限（防 IO/token 爆炸） =====================

# 覆盖度评审最多读取几个测试文件收集用例名。
_MAX_COVERAGE_TEST_FILES = 20
# 单个测试文件读取内容的字符上限。
_MAX_COVERAGE_TEST_FILE_CHARS = 200_000


def _is_test_path(path: str) -> bool:
    """启发式判断改动文件是否为测试文件（覆盖度评审输入）。

    判据：文件名以 test_ 开头、以常见测试后缀结尾，或路径中间段为
    tests / test（按 / 或 \\ 分段）。
    """
    parts = [part for part in path.replace("\\", "/").split("/") if part]
    name = parts[-1] if parts else ""
    return (
        name.startswith("test_")
        or name.endswith(("_test.py", ".test.ts", ".test.js", ".spec.ts", ".spec.js"))
        or any(part in ("tests", "test") for part in parts[:-1])
    )


class AgentExecutionMachine:
    _TERMINAL_PHASES = {
        AgentPhase.completed,
        AgentPhase.failed,
        AgentPhase.blocked,
    }

    def __init__(
        self,
        *,
        executor: StepExecutor,
        critic: Critic,
        summarizer: Summarizer,
        event_sink: EventSink,
        router: AgentStateRouter,
        replanner: Replanner | None = None,
        acceptance_gate: AcceptanceGateProtocol | None = None,
        acceptance_gate_max_retries: int = 2,
        scope_auditor: ScopeAuditorProtocol | None = None,
        scope_diff_provider: DiffProvider | None = None,
        coverage_reviewer: CoverageReviewerProtocol | None = None,
    ) -> None:
        self._executor = executor
        self._critic = critic
        self._summarizer = summarizer
        self._event_sink = event_sink
        self._replanner = replanner
        self._router = router
        self._acceptance_gate = acceptance_gate
        self._acceptance_gate_max_retries = acceptance_gate_max_retries
        self._scope_auditor = scope_auditor
        self._scope_diff_provider = scope_diff_provider
        self._coverage_reviewer = coverage_reviewer

    async def stream(
        self,
        session_id: UUID,
        plan_payload: Mapping[str, object],
        execution_context: AgentExecutionContext,
        *,
        run_id: UUID | None = None,
        start_step_index: int = 0,
        step_history: tuple[str, ...] = (),
    ) -> AsyncIterator[StreamItem]:
        plan = dict(plan_payload)
        execution_run_id = run_id if run_id is not None else uuid4()
        state = AgentRunState.from_plan(
            session_id,
            plan,
            run_id=execution_run_id,
            plan_revision=plan_revision(plan),
            start_step_index=start_step_index,
        )
        snapshot = MachineSnapshot(state, plan, step_history)
        while snapshot.state.phase not in self._TERMINAL_PHASES:
            transition = None
            async for item in self._dispatch(snapshot, execution_context):
                if isinstance(item, NodeTransition):
                    transition = self._capture_transition(transition, item)
                    continue
                yield item
            if transition is None:
                raise AppException(message="machine node did not return a transition")
            snapshot = transition.snapshot

    @staticmethod
    def _capture_transition(
        current: NodeTransition | None, candidate: NodeTransition
    ) -> NodeTransition:
        if current is not None:
            raise AppException(message="machine node returned two transitions")
        return candidate

    async def _dispatch(
        self, snapshot: MachineSnapshot, context: AgentExecutionContext
    ) -> AsyncIterator[StreamItem | NodeTransition]:
        handlers = {
            AgentPhase.executing: self._execute_node,
            AgentPhase.reflecting: self._reflect_node,
            AgentPhase.replanning: self._replan_node,
            AgentPhase.summarizing: self._summarize_node,
        }
        handler = handlers.get(snapshot.state.phase)
        if handler is None:
            raise AppException(
                message=f"unsupported agent phase: {snapshot.state.phase.value}"
            )
        async for item in handler(snapshot, context):
            yield item

    async def _execute_node(
        self, snapshot: MachineSnapshot, context: AgentExecutionContext
    ) -> AsyncIterator[StreamItem | NodeTransition]:
        request = self._execution_request(snapshot, context)
        outcome = await self._executor.execute(request)
        for event in outcome.events:
            yield event
        next_state = self._router.after_execution(
            snapshot.state, outcome.observation
        )
        history = self._executor.format_step_history(
            step_index=request.step_index,
            step=request.step,
            events=outcome.events,
        )
        events = snapshot.events + outcome.events
        if next_state.phase is AgentPhase.blocked:
            terminal_snapshot = MachineSnapshot(
                next_state, snapshot.plan, snapshot.step_history, events
            )
            blocked = await add_terminal_event(
                self._event_sink,
                terminal_snapshot,
                event_type=SessionEventType.step_blocked,
                reason=None,
            )
            events += (blocked,)
            yield blocked
        yield NodeTransition(
            MachineSnapshot(
                next_state,
                snapshot.plan,
                snapshot.step_history + (history,),
                events,
            )
        )
    async def _reflect_node(
        self, snapshot: MachineSnapshot, context: AgentExecutionContext
    ) -> AsyncIterator[StreamItem | NodeTransition]:
        del context
        state = snapshot.state
        if state.observation is None:
            raise AppException(message="reflecting state has no observation")
        reflection = await self._critic.evaluate(
            state.plan.steps[state.step_index], state.observation
        )
        reflected = await add_reflected_event(self._event_sink, snapshot, reflection)
        next_state = self._router.after_reflection(state, reflection)
        events = snapshot.events + (reflected,)
        terminal = await self._reflection_events(snapshot, next_state, reflection)
        yield reflected
        for event in terminal:
            events += (event,)
            yield event
        yield NodeTransition(
            MachineSnapshot(next_state, snapshot.plan, snapshot.step_history, events)
        )

    async def _replan_node(
        self, snapshot: MachineSnapshot, context: AgentExecutionContext
    ) -> AsyncIterator[StreamItem | NodeTransition]:
        del context
        if self._replanner is None:
            raise AppException(
                message="replanner is not configured",
                source=ErrorSource.agent,
            )
        replacement = dict(await self._replanner.replan(snapshot.state))
        replacement_revision = snapshot.state.plan_revision + 1
        replacement["plan_revision"] = replacement_revision
        replacement["run_id"] = str(snapshot.state.run_id)
        state = AgentRunState.from_plan(
            snapshot.state.session_id,
            replacement,
            run_id=snapshot.state.run_id,
            plan_revision=replacement_revision,
        )
        plan_event = await add_plan_event(
            self._event_sink,
            session_id=state.session_id,
            plan=replacement,
        )
        yield plan_event
        yield NodeTransition(
            MachineSnapshot(
                state,
                replacement,
                (),
                snapshot.events + (plan_event,),
            )
        )

    async def _summarize_node(
        self, snapshot: MachineSnapshot, context: AgentExecutionContext
    ) -> AsyncIterator[StreamItem | NodeTransition]:
        """summarize 节点：进入 summarize 前先按顺序跑完 summarize 前验收链。

        链顺序（DESIGN.md：先便宜后贵、先确定后概率）：
          1. acceptance gate —— 确定性命令验证，最便宜；
          2. scope audit —— 规则层 + LLM 复核；
          3. coverage review —— 纯 LLM，最贵；默认只建议不阻断（fail-open），
             仅当 plan 声明 acceptance.enforce_coverage=true 时，覆盖度不足
             才阻断并复用重试路径，与前两级共用同一重试额度。

        任一 stage 失败即短路整条链：不进入 summarize，复用现有 retry 路径
        回到 executing，重试额度用完后 → failed。全部 stage 跑完后，若实际执行了
        ≥2 个 stage，写一条 acceptance_chain_finished 汇总事件（仅单 stage 执行时
        其 finished 事件本身就是汇总，不再额外写，避免事件噪音）。
        """
        scope_policy = (
            ScopePolicy.from_plan(snapshot.plan)
            if self._scope_auditor is not None
            else None
        )
        chain_stages: dict[str, dict[str, object]] = {}

        # 工作区 diff 每个 cycle 只取一次：范围审计与覆盖度评审共用（避免重复 git 调用）
        diff_text = ""
        needs_diff = scope_policy is not None or self._coverage_reviewer is not None
        if needs_diff and self._scope_diff_provider is not None:
            diff_text = await self._scope_diff_provider.diff(context.workspace_dir)

        # ---- Stage 1：验收门禁（确定性、最便宜）----
        if self._acceptance_gate is not None:
            gate_config = gate_config_from_plan(snapshot.plan)
            if gate_config is not None:
                gate_transition: NodeTransition | None = None
                gate_events: list[SessionEvent] = []
                async for item in self._gate_cycle(snapshot, gate_config):
                    if isinstance(item, NodeTransition):
                        gate_transition = item
                        continue
                    if isinstance(item, SessionEvent):
                        gate_events.append(item)
                    yield item
                if gate_transition is not None:
                    # 门禁未通过：链短路，转入重试/failed，不进入 summarize
                    yield gate_transition
                    return
                # 门禁通过：把审计事件并入事件流，供范围审计/summarize 使用
                snapshot = MachineSnapshot(
                    snapshot.state,
                    snapshot.plan,
                    snapshot.step_history,
                    snapshot.events + tuple(gate_events),
                )
                chain_stages["acceptance_gate"] = self._gate_stage_summary(gate_events)
            else:
                chain_stages["acceptance_gate"] = {
                    "status": "skipped",
                    "detail": "plan 未声明 acceptance 配置",
                }
        else:
            chain_stages["acceptance_gate"] = {
                "status": "skipped",
                "detail": "未注入验收门禁",
            }

        # ---- Stage 2：范围审计（规则层 + LLM 复核）----
        if scope_policy is not None:
            scope_transition: NodeTransition | None = None
            scope_events: list[SessionEvent] = []
            async for item in self._scope_cycle(snapshot, diff_text):
                if isinstance(item, NodeTransition):
                    scope_transition = item
                    continue
                if isinstance(item, SessionEvent):
                    scope_events.append(item)
                yield item
            if scope_transition is not None:
                # 范围审计未通过：链短路，转入重试/failed，不进入 summarize
                yield scope_transition
                return
            snapshot = MachineSnapshot(
                snapshot.state,
                snapshot.plan,
                snapshot.step_history,
                snapshot.events + tuple(scope_events),
            )
            chain_stages["scope_audit"] = self._scope_stage_summary(scope_events)
        else:
            chain_stages["scope_audit"] = {
                "status": "skipped",
                "detail": "plan 未声明 scope 或未注入范围审计器",
            }

        # ---- Stage 3：覆盖度评审（纯 LLM、最贵；默认只建议、fail-open）----
        if self._coverage_reviewer is not None:
            coverage_transition: NodeTransition | None = None
            coverage_events: list[SessionEvent] = []
            async for item in self._coverage_cycle(snapshot, context, diff_text):
                if isinstance(item, NodeTransition):
                    coverage_transition = item
                    continue
                if isinstance(item, SessionEvent):
                    coverage_events.append(item)
                yield item
            if coverage_transition is not None:
                # 覆盖度不足且 enforce_coverage=true：链短路，转入重试/failed
                yield coverage_transition
                return
            snapshot = MachineSnapshot(
                snapshot.state,
                snapshot.plan,
                snapshot.step_history,
                snapshot.events + tuple(coverage_events),
            )
            chain_stages["coverage_review"] = self._coverage_stage_summary(coverage_events)
        else:
            chain_stages["coverage_review"] = {
                "status": "skipped",
                "detail": "未注入覆盖度评审器",
            }

        # ---- 验收链汇总事件（仅当实际执行了 ≥2 个 stage 时写入）----
        chain_event = await self._chain_finished_event(snapshot, chain_stages)
        if chain_event is not None:
            yield chain_event
            snapshot = MachineSnapshot(
                snapshot.state,
                snapshot.plan,
                snapshot.step_history,
                snapshot.events + (chain_event,),
            )

        request = AgentSummaryRequest(
            snapshot.state.session_id,
            snapshot.plan,
            snapshot.events,
            context.memory_context,
        )
        result = None
        async for item in self._summarizer.stream(request):
            if isinstance(item, AgentSummaryResult):
                if result is not None:
                    raise AppException(message="summarizer returned two results")
                result = item
            else:
                yield item
        if result is None:
            raise AppException(message="summarizer did not return a result")
        done = await add_done_event(
            self._event_sink,
            snapshot,
            result=result,
            context=context,
        )
        yield result.message_event
        yield done
        state = self._router.after_summary(snapshot.state, result.final_answer)
        events = snapshot.events + (result.message_event, done)
        yield NodeTransition(
            MachineSnapshot(state, snapshot.plan, snapshot.step_history, events)
        )

    async def _gate_cycle(
        self, snapshot: MachineSnapshot, gate_config: AcceptanceGateConfig
    ) -> AsyncIterator[StreamItem | NodeTransition]:
        """执行一次验收门禁：写 started/finished 审计事件；不通过则产出重试/failed 转移。"""
        assert self._acceptance_gate is not None, "gate_cycle requires an injected gate"
        state = snapshot.state
        started = await self._event_sink.add(
            session_id=state.session_id,
            event_type=SessionEventType.acceptance_gate_started,
            payload=self._gate_payload(snapshot, gate_config),
        )
        yield started
        result = await self._acceptance_gate.verify(gate_config)
        finished = await self._event_sink.add(
            session_id=state.session_id,
            event_type=SessionEventType.acceptance_gate_finished,
            payload={
                **self._gate_payload(snapshot, gate_config),
                "exit_code": result.exit_code,
                "passed": result.passed,
                "output_digest": result.output_digest,
                "duration_ms": result.duration_ms,
                "reason": result.reason,
            },
        )
        yield finished
        if result.passed:
            return
        async for item in self._gate_failed_transition(
            snapshot, (started, finished), result
        ):
            yield item

    async def _gate_failed_transition(
        self,
        snapshot: MachineSnapshot,
        gate_events: tuple[SessionEvent, ...],
        result: AcceptanceGateResult,
    ) -> AsyncIterator[StreamItem | NodeTransition]:
        """门禁不通过：构造 retry/fail Reflection，复用现有 retry 路径（reflecting → router）。

        重试额度未用完且 plan 允许重试 → 回到 executing 重跑当前验收步骤；
        否则 → failed，并写 step_failed + task_error 终态事件。
        """
        state = snapshot.state
        reason = f"acceptance gate failed: exit_code={result.exit_code}"
        failed_attempts = self._count_gate_failures(snapshot, result.command)
        can_retry = (
            self._gate_allow_retry(snapshot)
            and failed_attempts < self._acceptance_gate_max_retries
        )
        reflection = Reflection(
            ReflectionAction.retry if can_retry else ReflectionAction.fail,
            reason,
        )
        # 复用现有 retry 路径：先切到 reflecting，再交给路由器决定下一状态（路由器无需修改）
        reflecting_state = replace(state, phase=AgentPhase.reflecting)
        reflecting_snapshot = MachineSnapshot(
            reflecting_state,
            snapshot.plan,
            snapshot.step_history,
            snapshot.events + gate_events,
        )
        next_state = self._router.after_reflection(reflecting_state, reflection)
        reflected = await add_reflected_event(
            self._event_sink, reflecting_snapshot, reflection
        )
        yield reflected
        events = snapshot.events + gate_events + (reflected,)
        terminal = await self._reflection_events(
            reflecting_snapshot, next_state, reflection
        )
        for event in terminal:
            events += (event,)
            yield event
        yield NodeTransition(
            MachineSnapshot(next_state, snapshot.plan, snapshot.step_history, events)
        )

    def _count_gate_failures(
        self, snapshot: MachineSnapshot, command: str
    ) -> int:
        """统计当前运行中同一验收命令已经失败的次数（基于事件流，天然跨重试累积）。"""
        return sum(
            1
            for event in snapshot.events
            if event.type is SessionEventType.acceptance_gate_finished
            and event.payload.get("passed") is False
            and event.payload.get("command") == command
        )

    @staticmethod
    def _gate_allow_retry(snapshot: MachineSnapshot) -> bool:
        """plan 的 acceptance 配置是否允许重试（缺省 True，向后兼容）。"""
        raw = snapshot.plan.get("acceptance")
        if not isinstance(raw, Mapping):
            return True
        value = raw.get("allow_retry", True)
        return value is True

    def _gate_payload(
        self, snapshot: MachineSnapshot, gate_config: AcceptanceGateConfig
    ) -> dict[str, object]:
        """门禁审计事件的身份与配置字段。"""
        state = snapshot.state
        return {
            "plan_id": plan_id(snapshot.plan),
            "plan_revision": state.plan_revision,
            "run_id": str(state.run_id),
            "command": gate_config.command,
            "timeout_seconds": gate_config.timeout_seconds,
            "working_dir": gate_config.working_dir,
        }

    async def _scope_cycle(
        self,
        snapshot: MachineSnapshot,
        diff_text: str,
    ) -> AsyncIterator[StreamItem | NodeTransition]:
        """执行一次范围审计：工作区 diff 由 _summarize_node 统一获取（与覆盖度评审共用，
        避免重复 git 调用），调审计器，写 scope_audit_finished 事件；
        违规时产出重试/failed 转移（与验收门禁同一接入点，保持一致）。
        """
        assert self._scope_auditor is not None, "scope_cycle requires an injected auditor"
        state = snapshot.state
        result = await self._scope_auditor.audit(
            state.session_id, state.run_id, snapshot.plan, diff_text
        )
        # 审计事件由状态机统一写入（与验收门禁一致）；若注入的审计器
        # 自带事件写入（ScopeAuditService 缺省行为），组装时应将其关闭。
        finished = await self._event_sink.add(
            session_id=state.session_id,
            event_type=SessionEventType.scope_audit_finished,
            payload={
                **self._scope_event_payload(snapshot),
                "in_scope": result.in_scope,
                "reviewer": result.reviewer,
                "checked_files": result.checked_files,
                "violations": [
                    {
                        "path": v.path,
                        "change_type": v.change_type,
                        "additions": v.additions,
                        "deletions": v.deletions,
                    }
                    for v in result.violations
                ],
                "reason": result.reason,
            },
        )
        yield finished
        if result.in_scope:
            return
        async for item in self._scope_failed_transition(snapshot, (finished,), result):
            yield item

    async def _scope_failed_transition(
        self,
        snapshot: MachineSnapshot,
        scope_events: tuple[SessionEvent, ...],
        result: ScopeAuditResult,
    ) -> AsyncIterator[StreamItem | NodeTransition]:
        """范围审计违规：构造 retry/fail Reflection，复用现有 retry 路径（reflecting → 路由器）。

        重试额度与验收门禁共用：门禁失败与范围审计违规合并计数后与
        acceptance_gate_max_retries 比较；未用完 → 回到 executing 重跑当前步骤，
        用完 → failed，并写 step_failed + task_error 终态事件。
        """
        state = snapshot.state
        violation_paths = ", ".join(v.path for v in result.violations)
        reason = f"scope audit failed: 越界文件 [{violation_paths}]（{result.reason}）"
        failed_attempts = self._count_audit_failures(snapshot)
        can_retry = (
            self._scope_allow_retry(snapshot)
            and failed_attempts < self._acceptance_gate_max_retries
        )
        reflection = Reflection(
            ReflectionAction.retry if can_retry else ReflectionAction.fail,
            reason,
        )
        # 与验收门禁一致：先切到 reflecting，再交给路由器决定下一状态（路由器无需修改）
        reflecting_state = replace(state, phase=AgentPhase.reflecting)
        reflecting_snapshot = MachineSnapshot(
            reflecting_state,
            snapshot.plan,
            snapshot.step_history,
            snapshot.events + scope_events,
        )
        next_state = self._router.after_reflection(reflecting_state, reflection)
        reflected = await add_reflected_event(
            self._event_sink, reflecting_snapshot, reflection
        )
        yield reflected
        events = snapshot.events + scope_events + (reflected,)
        terminal = await self._reflection_events(reflecting_snapshot, next_state, reflection)
        for event in terminal:
            events += (event,)
            yield event
        yield NodeTransition(
            MachineSnapshot(next_state, snapshot.plan, snapshot.step_history, events)
        )

    def _count_audit_failures(self, snapshot: MachineSnapshot) -> int:
        """共用重试额度的失败计数：验收门禁失败 + 范围审计违规 + 覆盖度评审不足
        （仅 enforce_coverage=true 时计额度；只建议不阻断的评审失败不消耗额度）。

        基于事件流统计，天然跨重试累积。当前正在处理的那次失败事件尚未并入
        snapshot.events，与验收门禁计数口径一致。
        """
        return sum(
            1
            for event in snapshot.events
            if (
                event.type is SessionEventType.acceptance_gate_finished
                and event.payload.get("passed") is False
            )
            or (
                event.type is SessionEventType.scope_audit_finished
                and event.payload.get("in_scope") is False
            )
            or (
                event.type is SessionEventType.coverage_review_finished
                and event.payload.get("enforce_coverage") is True
                and event.payload.get("adequate") is False
            )
        )

    @staticmethod
    def _scope_allow_retry(snapshot: MachineSnapshot) -> bool:
        """plan 的 scope 配置是否允许重试（缺省 True，向后兼容）。"""
        raw = snapshot.plan.get("scope")
        if not isinstance(raw, Mapping):
            return True
        value = raw.get("allow_retry", True)
        return value is True

    @staticmethod
    def _scope_event_payload(snapshot: MachineSnapshot) -> dict[str, object]:
        """范围审计事件的身份字段（与验收门禁 payload 同构）。"""
        state = snapshot.state
        return {
            "plan_id": plan_id(snapshot.plan),
            "plan_revision": state.plan_revision,
            "run_id": str(state.run_id),
        }

    # ===================== Stage 3：覆盖度评审（纯 LLM、默认只建议） =====================

    async def _coverage_cycle(
        self,
        snapshot: MachineSnapshot,
        context: AgentExecutionContext,
        diff_text: str,
    ) -> AsyncIterator[StreamItem | NodeTransition]:
        """执行一次覆盖度评审：调评审器，状态机统一写 coverage_review_finished 审计事件
        （组装时应关闭评审器自带的事件写入——如注入 no-op event_writer——避免重复事件，
        与范围审计的 write_audit_event=False 同理）。

        覆盖度不足且 plan 声明 enforce_coverage=true → 产出重试/failed 转移
        （与验收门禁、范围审计共用同一重试额度）；
        否则（只建议 / fail-open 降级）→ 不阻断，返回主流程。
        """
        assert self._coverage_reviewer is not None, "coverage_cycle requires an injected reviewer"
        state = snapshot.state
        changed_files = [change.path for change in collect_changes(diff_text)]
        test_files = [path for path in changed_files if _is_test_path(path)]
        test_case_names = self._read_test_case_names(context.workspace_dir, test_files)
        result = await self._coverage_reviewer.review(
            state.session_id,
            state.run_id,
            snapshot.plan,
            changed_files,
            test_files,
            test_case_names,
        )
        finished = await self._event_sink.add(
            session_id=state.session_id,
            event_type=SessionEventType.coverage_review_finished,
            payload={
                **self._scope_event_payload(snapshot),
                "adequate": result.adequate,
                "reviewer": result.reviewer,
                "reason": result.reason,
                "enforce_coverage": enforce_coverage_from_plan(snapshot.plan),
                "gap_count": len(result.gaps),
                "gaps": [
                    {
                        "area": gap.area,
                        "severity": gap.severity,
                        "suggestion": gap.suggestion,
                    }
                    for gap in result.gaps[: settings.coverage_review_max_gaps_in_event]
                ],
            },
        )
        yield finished
        if should_retry(snapshot.plan, result):
            async for item in self._coverage_failed_transition(snapshot, (finished,), result):
                yield item

    async def _coverage_failed_transition(
        self,
        snapshot: MachineSnapshot,
        coverage_events: tuple[SessionEvent, ...],
        result: CoverageReviewResult,
    ) -> AsyncIterator[StreamItem | NodeTransition]:
        """覆盖度评审不足（enforce_coverage=true）：构造 retry/fail Reflection，复用现有重试路径。

        重试额度与验收门禁、范围审计共用：三类失败合并计数后与
        acceptance_gate_max_retries 比较；未用完 → 回到 executing 重跑当前步骤，
        用完 → failed，并写 step_failed + task_error 终态事件。
        """
        state = snapshot.state
        high_gaps = [gap for gap in result.gaps if gap.severity == "high"]
        detail = "; ".join(
            f"{gap.area}：{gap.suggestion}" if gap.suggestion else gap.area
            for gap in high_gaps
        )
        reason = f"覆盖度评审不足：{detail or result.reason or '存在高风险覆盖缺口'}"
        failed_attempts = self._count_audit_failures(snapshot)
        can_retry = (
            self._gate_allow_retry(snapshot)
            and failed_attempts < self._acceptance_gate_max_retries
        )
        reflection = Reflection(
            ReflectionAction.retry if can_retry else ReflectionAction.fail,
            reason,
        )
        # 与验收门禁/范围审计一致：先切到 reflecting，再交给路由器决定下一状态（路由器无需修改）
        reflecting_state = replace(state, phase=AgentPhase.reflecting)
        reflecting_snapshot = MachineSnapshot(
            reflecting_state,
            snapshot.plan,
            snapshot.step_history,
            snapshot.events + coverage_events,
        )
        next_state = self._router.after_reflection(reflecting_state, reflection)
        reflected = await add_reflected_event(
            self._event_sink, reflecting_snapshot, reflection
        )
        yield reflected
        events = snapshot.events + coverage_events + (reflected,)
        terminal = await self._reflection_events(reflecting_snapshot, next_state, reflection)
        for event in terminal:
            events += (event,)
            yield event
        yield NodeTransition(
            MachineSnapshot(next_state, snapshot.plan, snapshot.step_history, events)
        )

    @staticmethod
    def _read_test_case_names(workspace_dir: str, test_files: list[str]) -> list[str]:
        """从工作区读取测试文件内容并收集测试用例名（与覆盖度评审服务共用纯函数）。

        失败开放：文件不存在 / 读取失败直接跳过；文件个数与单文件字符数均有上限，
        防止 IO/token 爆炸。
        """
        if not workspace_dir or not test_files:
            return []
        names: list[str] = []
        root = Path(workspace_dir).resolve()
        for path in test_files[:_MAX_COVERAGE_TEST_FILES]:
            try:
                candidate = (root / path).resolve()
                if not candidate.is_file() or not candidate.is_relative_to(root):
                    continue
                content = candidate.read_text(
                    encoding="utf-8", errors="replace"
                )[:_MAX_COVERAGE_TEST_FILE_CHARS]
            except OSError:
                continue
            for case_names in collect_test_case_names({path: content}).values():
                for case in case_names:
                    if case not in names:
                        names.append(case)
        return names

    # ===================== 验收链：各 stage 汇总与汇总事件 =====================

    @staticmethod
    def _gate_stage_summary(gate_events: list[SessionEvent]) -> dict[str, object]:
        """验收门禁 stage 汇总（已跑且通过）：detail 记录退出码。"""
        finished = next(
            (
                event
                for event in gate_events
                if event.type is SessionEventType.acceptance_gate_finished
            ),
            None,
        )
        payload = finished.payload if finished is not None else {}
        return {"status": "passed", "detail": f"exit_code={payload.get('exit_code')}"}

    @staticmethod
    def _scope_stage_summary(scope_events: list[SessionEvent]) -> dict[str, object]:
        """范围审计 stage 汇总（已跑且通过）：detail 记录评审者与检查文件数。"""
        finished = next(
            (
                event
                for event in scope_events
                if event.type is SessionEventType.scope_audit_finished
            ),
            None,
        )
        payload = finished.payload if finished is not None else {}
        return {
            "status": "passed",
            "detail": (
                f"reviewer={payload.get('reviewer')}, "
                f"checked_files={payload.get('checked_files')}"
            ),
        }

    @staticmethod
    def _coverage_stage_summary(coverage_events: list[SessionEvent]) -> dict[str, object]:
        """覆盖度评审 stage 汇总（链未被阻断）：detail 记录结论/评审者/缺口数；
        覆盖度不足但未强制时显式标注"仅建议"。"""
        finished = next(
            (
                event
                for event in coverage_events
                if event.type is SessionEventType.coverage_review_finished
            ),
            None,
        )
        payload = finished.payload if finished is not None else {}
        detail = (
            f"adequate={payload.get('adequate')}, "
            f"reviewer={payload.get('reviewer')}, "
            f"gap_count={payload.get('gap_count')}"
        )
        if payload.get("adequate") is False and payload.get("enforce_coverage") is not True:
            detail += "（未启用 enforce，仅建议）"
        return {"status": "passed", "detail": detail}

    async def _chain_finished_event(
        self,
        snapshot: MachineSnapshot,
        chain_stages: dict[str, dict[str, object]],
    ) -> SessionEvent | None:
        """验收链跑完后写一条 acceptance_chain_finished 汇总事件：列出各 stage 结论。

        仅当实际执行了 ≥2 个 stage（status=passed）时写入：单 stage 执行时其自身
        finished 事件即汇总，重复写无信息量（也保持老接线——仅 gate / 仅 scope——的
        事件流不变）。
        """
        ran = sum(1 for stage in chain_stages.values() if stage.get("status") == "passed")
        if ran < 2:
            return None
        state = snapshot.state
        return await self._event_sink.add(
            session_id=state.session_id,
            event_type=SessionEventType.acceptance_chain_finished,
            payload={
                "plan_id": plan_id(snapshot.plan),
                "plan_revision": state.plan_revision,
                "run_id": str(state.run_id),
                "stages": chain_stages,
            },
        )

    def _execution_request(
        self, snapshot: MachineSnapshot, context: AgentExecutionContext
    ) -> StepExecutionRequest:
        steps = snapshot.plan.get("steps")
        if not isinstance(steps, (list, tuple)):
            raise AppException(message="plan steps must be a sequence")
        step = steps[snapshot.state.step_index]
        if not isinstance(step, Mapping):
            raise AppException(message="plan step must be an object")
        return StepExecutionRequest(
            session_id=snapshot.state.session_id,
            run_id=snapshot.state.run_id,
            plan_revision=snapshot.state.plan_revision,
            plan=snapshot.plan,
            step=step,
            step_index=snapshot.state.step_index,
            attempt=snapshot.state.attempt,
            memory_context=context.memory_context,
            agent_context=context.agent_context,
            step_history=snapshot.step_history,
            workspace_dir=context.workspace_dir,
            full_access=context.full_access,
        )

    async def _reflection_events(
        self,
        snapshot: MachineSnapshot,
        next_state: AgentRunState,
        reflection: Reflection,
    ) -> tuple[SessionEvent, ...]:
        if reflection.action is ReflectionAction.accept:
            completed = await add_terminal_event(
                self._event_sink,
                snapshot,
                event_type=SessionEventType.step_completed,
                reason=reflection.reason,
            )
            return (completed,)
        if next_state.phase is AgentPhase.failed:
            failed = await add_terminal_event(
                self._event_sink,
                snapshot,
                event_type=SessionEventType.step_failed,
                reason=reflection.reason,
            )
            error = await add_failure_event(
                self._event_sink, snapshot, reflection.reason
            )
            return failed, error
        return ()
