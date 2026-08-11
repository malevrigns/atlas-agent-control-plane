from dataclasses import replace

from app.domain.agent_core.tools import ToolInvocationStatus
from app.domain.agent_runtime.entities import (
    AgentPhase,
    AgentRunState,
    Reflection,
    ReflectionAction,
    StepObservation,
)


SUCCESS_STATUSES = {
    ToolInvocationStatus.succeeded,
    ToolInvocationStatus.deduplicated,
}
FINAL_FAILURE_STATUSES = {
    ToolInvocationStatus.failed,
    ToolInvocationStatus.timed_out,
    ToolInvocationStatus.denied,
}


class AgentStateRouter:
    def after_execution(
        self, state: AgentRunState, observation: StepObservation
    ) -> AgentRunState:
        if observation.status in SUCCESS_STATUSES:
            return replace(
                state,
                phase=AgentPhase.reflecting,
                observation=observation,
            )
        if observation.status in FINAL_FAILURE_STATUSES:
            return replace(
                state,
                phase=AgentPhase.failed,
                observation=observation,
            )
        if observation.status is ToolInvocationStatus.approval_required:
            return replace(
                state,
                phase=AgentPhase.blocked,
                observation=observation,
            )
        raise ValueError(f"execution status is not terminal: {observation.status}")

    def after_reflection(
        self, state: AgentRunState, reflection: Reflection
    ) -> AgentRunState:
        if reflection.action is ReflectionAction.retry:
            return replace(
                state,
                phase=AgentPhase.executing,
                attempt=state.attempt + 1,
                reflection=reflection,
            )
        if reflection.action is ReflectionAction.replan:
            return replace(state, phase=AgentPhase.replanning, reflection=reflection)
        if reflection.action is ReflectionAction.accept:
            return self._accept(state, reflection)
        raise ValueError(f"unsupported reflection action: {reflection.action}")

    def after_summary(self, state: AgentRunState, final_answer: str) -> AgentRunState:
        return replace(state, phase=AgentPhase.completed, final_answer=final_answer)

    @staticmethod
    def _accept(state: AgentRunState, reflection: Reflection) -> AgentRunState:
        if state.step_index + 1 == len(state.plan.steps):
            return replace(state, phase=AgentPhase.summarizing, reflection=reflection)
        return replace(
            state,
            phase=AgentPhase.executing,
            step_index=state.step_index + 1,
            attempt=1,
            reflection=reflection,
        )
