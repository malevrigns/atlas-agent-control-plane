from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.sessions.entities import (
    MessageRole,
    Session,
    SessionEvent,
    SessionEventType,
    SessionMessage,
    SessionStatus,
)
from app.domain.sessions.repositories import (
    SessionEventRepository,
    SessionMessageRepository,
    SessionRepository,
)
from app.infrastructure.database.models.session_event import SessionEventModel
from app.infrastructure.database.models.session_message import SessionMessageModel
from app.infrastructure.database.models.session import SessionModel


class SqlAlchemySessionRepository(SessionRepository):
    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def add(
        self,
        title: str,
        workspace_dir: str = "",
        full_access: bool = False,
    ) -> Session:
        model = SessionModel(
            title=title,
            status=SessionStatus.idle.value,
            unread_count=0,
            workspace_dir=workspace_dir,
            full_access=full_access,
        )
        self.db_session.add(model)
        await self.db_session.flush()
        await self.db_session.refresh(model)
        return model.to_entity()

    async def get(self, session_id: UUID) -> Session | None:
        stmt = self._active_stmt().where(SessionModel.id == session_id)
        result = await self.db_session.execute(stmt)
        model = result.scalar_one_or_none()
        return model.to_entity() if model else None

    async def list_active(self) -> list[Session]:
        stmt = self._active_stmt().order_by(SessionModel.updated_at.desc())
        result = await self.db_session.execute(stmt)
        return [model.to_entity() for model in result.scalars()]

    async def soft_delete(self, session_id: UUID) -> None:
        stmt = self._active_stmt().where(SessionModel.id == session_id)
        result = await self.db_session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is not None:
            model.deleted_at = datetime.now(UTC)

    async def touch(self, session_id: UUID) -> None:
        stmt = self._active_stmt().where(SessionModel.id == session_id)
        result = await self.db_session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is not None:
            model.updated_at = datetime.now(UTC)

    async def update_status(self, session_id: UUID, status: str) -> Session | None:
        stmt = self._active_stmt().where(SessionModel.id == session_id)
        result = await self.db_session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        model.status = status
        model.updated_at = datetime.now(UTC)
        await self.db_session.flush()
        await self.db_session.refresh(model)
        return model.to_entity()

    async def update_title(self, session_id: UUID, title: str) -> Session | None:
        stmt = self._active_stmt().where(SessionModel.id == session_id)
        result = await self.db_session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        model.title = title
        model.updated_at = datetime.now(UTC)
        await self.db_session.flush()
        await self.db_session.refresh(model)
        return model.to_entity()

    async def increment_unread(self, session_id: UUID) -> None:
        stmt = self._active_stmt().where(SessionModel.id == session_id)
        result = await self.db_session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is not None:
            model.unread_count += 1
            model.updated_at = datetime.now(UTC)

    async def clear_unread(self, session_id: UUID) -> Session | None:
        stmt = self._active_stmt().where(SessionModel.id == session_id)
        result = await self.db_session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        model.unread_count = 0
        model.updated_at = datetime.now(UTC)
        await self.db_session.flush()
        await self.db_session.refresh(model)
        return model.to_entity()

    @staticmethod
    def _active_stmt() -> Select[tuple[SessionModel]]:
        return select(SessionModel).where(SessionModel.deleted_at.is_(None))


class SqlAlchemySessionMessageRepository(SessionMessageRepository):
    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def add_user_message(self, session_id: UUID, content: str) -> SessionMessage:
        return await self._add_message(session_id, MessageRole.user, content)

    async def add_assistant_message(
        self, session_id: UUID, content: str
    ) -> SessionMessage:
        return await self._add_message(session_id, MessageRole.assistant, content)

    async def _add_message(
        self,
        session_id: UUID,
        role: MessageRole,
        content: str,
    ) -> SessionMessage:
        model = SessionMessageModel(
            session_id=session_id,
            role=role.value,
            content=content,
        )
        self.db_session.add(model)
        await self.db_session.flush()
        await self.db_session.refresh(model)
        return model.to_entity()

    async def list_by_session(self, session_id: UUID) -> list[SessionMessage]:
        stmt = (
            select(SessionMessageModel)
            .where(SessionMessageModel.session_id == session_id)
            .order_by(SessionMessageModel.created_at.asc())
        )
        result = await self.db_session.execute(stmt)
        return [model.to_entity() for model in result.scalars()]


class SqlAlchemySessionEventRepository(SessionEventRepository):
    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def add(
        self,
        session_id: UUID,
        event_type: SessionEventType,
        payload: dict,
    ) -> SessionEvent:
        model = SessionEventModel(
            session_id=session_id,
            type=event_type.value,
            payload=payload,
        )
        self.db_session.add(model)
        await self.db_session.flush()
        await self.db_session.refresh(model)
        return model.to_entity()

    async def list_by_session(self, session_id: UUID) -> list[SessionEvent]:
        stmt = (
            select(SessionEventModel)
            .where(SessionEventModel.session_id == session_id)
            .order_by(SessionEventModel.created_at.asc())
        )
        result = await self.db_session.execute(stmt)
        return [model.to_entity() for model in result.scalars()]
