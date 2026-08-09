from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.repositories.file_repository import (
    SqlAlchemyFileRepository,
    SqlAlchemySessionFileRepository,
)
from app.infrastructure.repositories.control_plane_repository import (
    SqlAlchemyControlPlaneRepository,
)
from app.infrastructure.repositories.memory_repository import (
    SqlAlchemyAgentMemoryRepository,
)
from app.infrastructure.repositories.rag_repository import (
    SqlAlchemyKnowledgeBaseRepository,
    SqlAlchemyKnowledgeChunkRepository,
    SqlAlchemyKnowledgeDocumentRepository,
)
from app.infrastructure.repositories.skill_repository import (
    SqlAlchemySkillRepository,
)
from app.infrastructure.repositories.session_repository import (
    SqlAlchemySessionEventRepository,
    SqlAlchemySessionMessageRepository,
    SqlAlchemySessionRepository,
)


class UnitOfWork:
    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session
        self.files = SqlAlchemyFileRepository(db_session)
        self.control_plane = SqlAlchemyControlPlaneRepository(db_session)
        self.memories = SqlAlchemyAgentMemoryRepository(db_session)
        self.knowledge_bases = SqlAlchemyKnowledgeBaseRepository(db_session)
        self.knowledge_documents = SqlAlchemyKnowledgeDocumentRepository(db_session)
        self.knowledge_chunks = SqlAlchemyKnowledgeChunkRepository(db_session)
        self.skills = SqlAlchemySkillRepository(db_session)
        self.session_files = SqlAlchemySessionFileRepository(db_session)
        self.sessions = SqlAlchemySessionRepository(db_session)
        self.session_messages = SqlAlchemySessionMessageRepository(db_session)
        self.session_events = SqlAlchemySessionEventRepository(db_session)

    async def commit(self) -> None:
        await self.db_session.commit()

    async def rollback(self) -> None:
        await self.db_session.rollback()
