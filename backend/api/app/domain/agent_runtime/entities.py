from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping
from uuid import UUID

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


@dataclass(frozen=True, slots=True)
class RunPlanStep:
    tool_name: str
    arguments: Mapping[str, object]

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "RunPlanStep":
        return cls(
            tool_name=str(payload["tool_name"]),
            arguments=MappingProxyType(dict(payload.get("arguments", {}))),
        )


@dataclass(frozen=True, slots=True)
class RunPlan:
    goal: str
    steps: tuple[RunPlanStep, ...]

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "RunPlan":
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
    plan: RunPlan
    phase: AgentPhase
    step_index: int
    attempt: int
    observation: StepObservation | None = None
    reflection: Reflection | None = None
    final_answer: str | None = None

    @classmethod
    def from_plan(
        cls, session_id: UUID, plan_payload: dict[str, object]
    ) -> "AgentRunState":
        return cls(
            session_id=session_id,
            plan=RunPlan.from_payload(plan_payload),
            phase=AgentPhase.executing,
            step_index=0,
            attempt=1,
        )
