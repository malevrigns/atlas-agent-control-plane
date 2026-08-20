from collections.abc import AsyncIterator, Mapping
from uuid import UUID, uuid4

from app.application.agent_execution_event_writer import (
    add_done_event,
    add_failure_event,
    add_plan_event,
    add_reflected_event,
    add_terminal_event,
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
from app.application.react_step_executor import StepExecutionRequest
from app.core.exceptions import AppException, ErrorSource
from app.domain.agent_runtime.entities import (
    AgentPhase,
    AgentRunState,
    Reflection,
    ReflectionAction,
)
from app.domain.agent_runtime.router import AgentStateRouter
from app.domain.sessions.entities import SessionEvent, SessionEventType


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
    ) -> None:
        self._executor = executor
        self._critic = critic
        self._summarizer = summarizer
        self._event_sink = event_sink
        self._replanner = replanner
        self._router = router

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
