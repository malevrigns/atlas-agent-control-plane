from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.domain.agent_core.planner import PlanStepStatus
from app.domain.agent_core.tools import ToolInvocationStatus


class AgentPhase(StrEnum):
    executing = "executing"
    reflecting = "reflecting"
    replanning = "replanning"
    summarizing = "summarizing"
    completed = "completed"
    failed = "failed"
    blocked = "blocked"


class ReflectionAction(StrEnum):
    accept = "accept"
    retry = "retry"
    replan = "replan"
    fail = "fail"


@dataclass(frozen=True, slots=True)
class RunPlanStep:
    id: UUID
    title: str
    description: str
    expected_output: str
    status: PlanStepStatus

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "RunPlanStep":
        return cls(
            id=UUID(str(payload["id"])),
            title=str(payload["title"]),
            description=str(payload["description"]),
            expected_output=str(payload["expected_output"]),
            status=PlanStepStatus(str(payload["status"])),
        )


@dataclass(frozen=True, slots=True)
class RunPlan:
    goal: str
    steps: tuple[RunPlanStep, ...]

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "RunPlan":
        raw_steps = payload["steps"]
        if not isinstance(raw_steps, (list, tuple)):
            raise ValueError("plan payload steps must be a sequence")
        return cls(
            goal=str(payload.get("goal", "")),
            steps=tuple(RunPlanStep.from_payload(step) for step in raw_steps),
        )


@dataclass(frozen=True, slots=True)
class StepObservation:
    status: ToolInvocationStatus
    output: str


@dataclass(frozen=True, slots=True)
class Reflection:
    action: ReflectionAction
    reason: str


@dataclass(frozen=True, slots=True)
class AgentRunState:
    session_id: UUID
    run_id: UUID
    plan_revision: int
    plan: RunPlan
    phase: AgentPhase
    step_index: int
    attempt: int
    observation: StepObservation | None = None
    reflection: Reflection | None = None
    final_answer: str | None = None

    @classmethod
    def from_plan(
        cls,
        session_id: UUID,
        plan_payload: dict[str, object],
        *,
        run_id: UUID,
        plan_revision: int,
    ) -> "AgentRunState":
        if (
            isinstance(plan_revision, bool)
            or not isinstance(plan_revision, int)
            or plan_revision < 0
        ):
            raise ValueError("plan_revision must be non-negative")
        return cls(
            session_id=session_id,
            run_id=run_id,
            plan_revision=plan_revision,
            plan=RunPlan.from_payload(plan_payload),
            phase=AgentPhase.executing,
            step_index=0,
            attempt=1,
        )
