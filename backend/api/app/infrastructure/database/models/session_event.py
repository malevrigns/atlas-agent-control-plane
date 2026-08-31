from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.sessions.entities import SessionEvent, SessionEventType
from app.infrastructure.database.base import Base
from app.infrastructure.database.types import JsonValue, UtcDateTime, UuidValue


class SessionEventModel(Base):
    __tablename__ = "session_events"

    id: Mapped[UUID] = mapped_column(UuidValue, primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        UuidValue,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JsonValue, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime,
        nullable=False,
        server_default=func.now(),
    )

    def to_entity(self) -> SessionEvent:
        return SessionEvent(
            id=self.id,
            session_id=self.session_id,
            type=SessionEventType(self.type),
            payload=self.payload,
            created_at=self.created_at,
        )
