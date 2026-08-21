from uuid import UUID

from app.application.unit_of_work import UnitOfWork
from app.core.exceptions import AppException
from app.domain.sessions.entities import (
    Session,
    SessionEvent,
    SessionEventType,
    SessionMessage,
    SessionStatus,
)


def normalize_workspace_dir(raw: str) -> str:
    """把用户输入的工作区路径规范成沙箱相对路径。

    D:\\projects\\myapp -> projects/myapp
    D:/projects/myapp      -> projects/myapp
    projects\\myapp       -> projects/myapp
    projects/myapp         -> projects/myapp（不变）
    拒绝 ..（路径穿越）。
    """

    value = raw.strip()
    if not value:
        return ""
    value = value.replace("\\", "/")
    if len(value) >= 2 and value[1] == ":":
        value = value[2:]
    value = value.strip("/")
    parts = [part for part in value.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise AppException(
            message="工作区路径不能包含 ..", code=400, status_code=400
        )
    return "/".join(parts)


class SessionService:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def create_session(
        self,
        title: str,
        workspace_dir: str = "",
        full_access: bool = False,
    ) -> Session:
        clean_title = title.strip() or "新工作区"
        session = await self.uow.sessions.add(
            title=clean_title,
            workspace_dir=normalize_workspace_dir(workspace_dir),
            full_access=full_access,
        )
        await self.uow.commit()
        return session

    async def update_title(self, session_id: UUID, title: str) -> Session | None:
        clean_title = title.strip()
        if not clean_title:
            return None
        session = await self.uow.sessions.update_title(session_id, clean_title)
        await self.uow.commit()
        return session

    async def list_sessions(self) -> list[Session]:
        return await self.uow.sessions.list_active()

    async def get_session(self, session_id: UUID) -> Session:
        session = await self.uow.sessions.get(session_id)
        if session is None:
            raise AppException(
                message="session not found",
                code=404,
                status_code=404,
            )
        return session

    async def list_messages(self, session_id: UUID) -> list[SessionMessage]:
        await self.get_session(session_id)
        return await self.uow.session_messages.list_by_session(session_id)

    async def list_events(self, session_id: UUID) -> list[SessionEvent]:
        await self.get_session(session_id)
        return await self.uow.session_events.list_by_session(session_id)

    async def create_user_message(
        self,
        session_id: UUID,
        content: str,
    ) -> tuple[SessionMessage, SessionEvent]:
        await self.get_session(session_id)
        clean_content = content.strip()
        if not clean_content:
            raise AppException(
                message="message content is required",
                code=400,
                status_code=400,
            )

        message = await self.uow.session_messages.add_user_message(
            session_id=session_id,
            content=clean_content,
        )
        event = await self.uow.session_events.add(
            session_id=session_id,
            event_type=SessionEventType.message_created,
            payload={
                "message_id": str(message.id),
                "role": message.role.value,
                "content": message.content,
            },
        )
        await self.uow.sessions.increment_unread(session_id)
        await self.uow.sessions.touch(session_id)
        await self.uow.commit()
        return message, event

    async def create_assistant_message(
        self,
        session_id: UUID,
        content: str,
    ) -> tuple[SessionMessage, SessionEvent]:
        """把 Agent 的最终回答落库成 assistant 消息。

        没有这一步，消息列表里永远只有用户消息，
        客户端刷新后只能看到“半边对话”。
        """

        await self.get_session(session_id)
        clean_content = content.strip()
        if not clean_content:
            raise AppException(
                message="assistant message content is required",
                code=400,
                status_code=400,
            )

        message = await self.uow.session_messages.add_assistant_message(
            session_id=session_id,
            content=clean_content,
        )
        event = await self.uow.session_events.add(
            session_id=session_id,
            event_type=SessionEventType.message_created,
            payload={
                "message_id": str(message.id),
                "role": message.role.value,
                "content": message.content,
            },
        )
        await self.uow.sessions.touch(session_id)
        await self.uow.commit()
        return message, event

    async def mark_running(self, session_id: UUID) -> Session:
        await self.get_session(session_id)
        session = await self.uow.sessions.update_status(
            session_id=session_id,
            status=SessionStatus.running.value,
        )
        await self.uow.commit()
        if session is None:
            raise AppException(
                message="session not found",
                code=404,
                status_code=404,
            )
        return session

    async def mark_idle(self, session_id: UUID) -> Session:
        await self.get_session(session_id)
        session = await self.uow.sessions.update_status(
            session_id=session_id,
            status=SessionStatus.idle.value,
        )
        await self.uow.commit()
        if session is None:
            raise AppException(
                message="session not found",
                code=404,
                status_code=404,
            )
        return session

    async def stop_session(self, session_id: UUID) -> Session:
        await self.get_session(session_id)
        session = await self.uow.sessions.update_status(
            session_id=session_id,
            status=SessionStatus.stopped.value,
        )
        await self.uow.commit()
        if session is None:
            raise AppException(
                message="session not found",
                code=404,
                status_code=404,
            )
        return session

    async def clear_unread(self, session_id: UUID) -> Session:
        await self.get_session(session_id)
        session = await self.uow.sessions.clear_unread(session_id)
        await self.uow.commit()
        if session is None:
            raise AppException(
                message="session not found",
                code=404,
                status_code=404,
            )
        return session

    async def delete_session(self, session_id: UUID) -> None:
        await self.get_session(session_id)
        await self.uow.sessions.soft_delete(session_id)
        await self.uow.commit()
