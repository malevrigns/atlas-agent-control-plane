from dataclasses import dataclass

from app.domain.sessions.entities import Session, SessionEvent


@dataclass(frozen=True, slots=True)
class AgentRunnerStreamItem:
    name: str
    payload: Session | SessionEvent | dict


@dataclass(frozen=True, slots=True)
class DirectAnswer:
    content: str
    reasoning: str
