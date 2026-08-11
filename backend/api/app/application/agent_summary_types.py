from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol
from uuid import UUID

from app.domain.context_engineering.entities import MemoryContext
from app.domain.llm.entities import LLMMessage
from app.domain.sessions.entities import SessionEvent


class SummaryModel(Protocol):
    def chat_stream(
        self,
        messages: list[LLMMessage],
        *,
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        thinking: bool | None = None,
    ) -> AsyncIterator[object]: ...


@dataclass(frozen=True, slots=True)
class AgentSummaryRequest:
    session_id: UUID
    plan: Mapping[str, object]
    events: tuple[SessionEvent, ...]
    memory_context: MemoryContext

    def __post_init__(self) -> None:
        object.__setattr__(self, "plan", MappingProxyType(dict(self.plan)))
        object.__setattr__(self, "events", tuple(self.events))


@dataclass(frozen=True, slots=True)
class AgentSummaryResult:
    final_answer: str
    reasoning: str
    message_event: SessionEvent
    message_id: UUID
