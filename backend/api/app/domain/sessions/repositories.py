from typing import Protocol
from uuid import UUID

from app.domain.sessions.entities import (
    Session,
    SessionEvent,
    SessionEventType,
    SessionMessage,
)


class SessionRepository(Protocol):
    async def add(self, title: str) -> Session:
        raise NotImplementedError

    async def get(self, session_id: UUID) -> Session | None:
        raise NotImplementedError

    async def list_active(self) -> list[Session]:
        raise NotImplementedError

    async def soft_delete(self, session_id: UUID) -> None:
        raise NotImplementedError

    async def touch(self, session_id: UUID) -> None:
        raise NotImplementedError

    async def update_status(self, session_id: UUID, status: str) -> Session | None:
        raise NotImplementedError

    async def update_title(self, session_id: UUID, title: str) -> Session | None:
        raise NotImplementedError

    async def increment_unread(self, session_id: UUID) -> None:
        raise NotImplementedError

    async def clear_unread(self, session_id: UUID) -> Session | None:
        raise NotImplementedError


class SessionMessageRepository(Protocol):
    async def add_user_message(self, session_id: UUID, content: str) -> SessionMessage:
        raise NotImplementedError

    async def add_assistant_message(
        self, session_id: UUID, content: str
    ) -> SessionMessage:
        raise NotImplementedError

    async def list_by_session(self, session_id: UUID) -> list[SessionMessage]:
        raise NotImplementedError


class SessionEventRepository(Protocol):
    async def add(
        self,
        session_id: UUID,
        event_type: SessionEventType,
        payload: dict,
    ) -> SessionEvent:
        raise NotImplementedError

    async def list_by_session(self, session_id: UUID) -> list[SessionEvent]:
        raise NotImplementedError
