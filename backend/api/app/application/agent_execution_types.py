from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol
from uuid import UUID

from app.application.agent_summary_service import AgentSummaryRequest, AgentSummaryResult
from app.application.react_step_executor import StepExecutionOutcome, StepExecutionRequest
from app.domain.agent_runtime.entities import (
    AgentRunState,
    Reflection,
    RunPlanStep,
    StepObservation,
)
from app.domain.context_engineering.entities import MemoryContext
from app.domain.sessions.entities import SessionEvent, SessionEventType


StreamItem = SessionEvent | tuple[str, str]


@dataclass(frozen=True, slots=True)
class AgentExecutionContext:
    memory_context: MemoryContext
    agent_context: str


@dataclass(frozen=True, slots=True)
class MachineSnapshot:
    state: AgentRunState
    plan: Mapping[str, object]
    step_history: tuple[str, ...] = ()
    events: tuple[SessionEvent, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "plan", MappingProxyType(dict(self.plan)))


@dataclass(frozen=True, slots=True)
class NodeTransition:
    snapshot: MachineSnapshot


class StepExecutor(Protocol):
    async def execute(self, request: StepExecutionRequest) -> StepExecutionOutcome: ...

    def format_step_history(
        self,
        *,
        step_index: int,
        step: Mapping[str, object],
        events: tuple[SessionEvent, ...],
    ) -> str: ...


class Critic(Protocol):
    async def evaluate(
        self,
        step: RunPlanStep,
        observation: StepObservation,
    ) -> Reflection: ...


class Summarizer(Protocol):
    def stream(
        self, request: AgentSummaryRequest
    ) -> AsyncIterator[tuple[str, str] | AgentSummaryResult]: ...


class EventSink(Protocol):
    async def add(
        self,
        *,
        session_id: UUID,
        event_type: SessionEventType,
        payload: dict[str, object],
    ) -> SessionEvent: ...


class Replanner(Protocol):
    async def replan(self, state: AgentRunState) -> Mapping[str, object]: ...
