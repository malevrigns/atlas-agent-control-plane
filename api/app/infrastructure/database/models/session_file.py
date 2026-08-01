from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.files.entities import SessionFile
from app.infrastructure.database.base import Base
from app.infrastructure.database.models.file_object import FileObjectModel


class SessionFileModel(Base):
    __tablename__ = "session_files"
    __table_args__ = (
        UniqueConstraint("session_id", "file_id", name="uq_session_files_session_file"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    file: Mapped[FileObjectModel] = relationship(lazy="joined")

    def to_entity(self) -> SessionFile:
        return SessionFile(
            id=self.id,
            session_id=self.session_id,
            file=self.file.to_entity(),
            created_at=self.created_at,
        )
