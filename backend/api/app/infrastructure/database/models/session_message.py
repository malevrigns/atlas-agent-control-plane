from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.sessions.entities import MessageRole, SessionMessage
from app.infrastructure.database.base import Base
from app.infrastructure.database.types import UtcDateTime, UuidValue


class SessionMessageModel(Base):
    __tablename__ = "session_messages"

    id: Mapped[UUID] = mapped_column(UuidValue, primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        UuidValue,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime,
        nullable=False,
        server_default=func.now(),
    )

    def to_entity(self) -> SessionMessage:
        return SessionMessage(
            id=self.id,
            session_id=self.session_id,
            role=MessageRole(self.role),
            content=self.content,
            created_at=self.created_at,
        )
