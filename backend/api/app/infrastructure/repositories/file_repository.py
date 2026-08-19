from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.files.entities import FileObject, SessionFile
from app.domain.files.repositories import FileRepository, SessionFileRepository
from app.infrastructure.database.models.file_object import FileObjectModel
from app.infrastructure.database.models.session_file import SessionFileModel


class SqlAlchemyFileRepository(FileRepository):
    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def add(
        self,
        original_name: str,
        stored_name: str,
        content_type: str,
        size: int,
        storage_path: str,
    ) -> FileObject:
        model = FileObjectModel(
            original_name=original_name,
            stored_name=stored_name,
            content_type=content_type,
            size=size,
            storage_path=storage_path,
        )
        self.db_session.add(model)
        await self.db_session.flush()
        await self.db_session.refresh(model)
        return model.to_entity()

    async def get(self, file_id: UUID) -> FileObject | None:
        stmt = select(FileObjectModel).where(FileObjectModel.id == file_id)
        result = await self.db_session.execute(stmt)
        model = result.scalar_one_or_none()
        return model.to_entity() if model else None

    async def delete(self, file_object: FileObject) -> None:
        model = await self.db_session.get(FileObjectModel, file_object.id)
        if model is not None:
            await self.db_session.delete(model)


class SqlAlchemySessionFileRepository(SessionFileRepository):
    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def add(self, session_id: UUID, file_id: UUID) -> SessionFile:
        # 关系表只保存归属关系，不冗余保存文件内容和文件元数据。
        model = SessionFileModel(session_id=session_id, file_id=file_id)
        self.db_session.add(model)
        await self.db_session.flush()
        stmt = select(SessionFileModel).where(SessionFileModel.id == model.id)
        result = await self.db_session.execute(stmt)
        created = result.scalar_one()
        return created.to_entity()

    async def get(self, session_file_id: UUID) -> SessionFile | None:
        stmt = select(SessionFileModel).where(SessionFileModel.id == session_file_id)
        result = await self.db_session.execute(stmt)
        model = result.scalar_one_or_none()
        return model.to_entity() if model else None

    async def list_by_session(self, session_id: UUID) -> list[SessionFile]:
        stmt = (
            select(SessionFileModel)
            .where(SessionFileModel.session_id == session_id)
            .order_by(SessionFileModel.created_at.desc())
        )
        result = await self.db_session.execute(stmt)
        return [model.to_entity() for model in result.scalars()]

    async def delete(self, session_file: SessionFile) -> None:
        model = await self.db_session.get(SessionFileModel, session_file.id)
        if model is not None:
            await self.db_session.delete(model)
