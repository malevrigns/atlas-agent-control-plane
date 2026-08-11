from collections.abc import AsyncIterator
from typing import TYPE_CHECKING
from uuid import UUID

from app.application.agent_direct_chat_service import AgentDirectChatService
from app.application.agent_pipeline_policy import needs_agent_pipeline
from app.application.agent_runner_types import AgentRunnerStreamItem
from app.application.planner_service import PlannerService
from app.application.react_agent_service import ReActAgentService
from app.application.session_service import SessionService
from app.application.unit_of_work import UnitOfWork
from app.core.exceptions import build_task_error_payload
from app.domain.sessions.entities import SessionEvent, SessionEventType, SessionStatus

if TYPE_CHECKING:
    from app.application.context_engineering_service import ContextEngineeringService
    from app.application.llm_service import LLMService

__all__ = ["AgentRunnerService", "AgentRunnerStreamItem", "needs_agent_pipeline"]


class AgentRunnerService:
    def __init__(
        self,
        *,
        session_service: SessionService,
        planner_service: PlannerService,
        react_service: ReActAgentService,
        direct_chat_service: AgentDirectChatService,
    ) -> None:
        self.session_service = session_service
        self.planner_service = planner_service
        self.react_service = react_service
        self.direct_chat_service = direct_chat_service
        self.llm_service = direct_chat_service.model

    @property
    def context_service(self) -> "ContextEngineeringService":
        return self.direct_chat_service.context_service

    @classmethod
    def from_uow(
        cls,
        uow: UnitOfWork,
        *,
        llm_service: "LLMService | None" = None,
        planner_service: PlannerService | None = None,
    ) -> "AgentRunnerService":
        from app.application.agent_runtime_composition import compose_agent_runtime

        runtime = compose_agent_runtime(
            uow,
            llm_service=llm_service,
            planner_service=planner_service,
        )
        return cls(
            session_service=runtime.session_service,
            planner_service=runtime.planner_service,
            react_service=runtime.react_service,
            direct_chat_service=runtime.direct_chat_service,
        )

    async def stream_user_message(
        self, *, session_id: UUID, content: str
    ) -> AsyncIterator[AgentRunnerStreamItem]:
        try:
            async for item in self._stream_user_message_inner(
                session_id=session_id,
                content=content,
            ):
                yield item
        finally:
            await self._reset_running_session(session_id)

    async def _stream_user_message_inner(
        self, *, session_id: UUID, content: str
    ) -> AsyncIterator[AgentRunnerStreamItem]:
        running = await self.session_service.mark_running(session_id)
        yield AgentRunnerStreamItem("session_status", running)
        message = None
        try:
            message, message_event = await self.session_service.create_user_message(
                session_id=session_id,
                content=content,
            )
            yield AgentRunnerStreamItem(message_event.type.value, message_event)
            if needs_agent_pipeline(content):
                stream = self._stream_pipeline(session_id=session_id, content=content)
            else:
                stream = self.direct_chat_service.stream(
                    session_id=session_id,
                    content=content,
                )
            async for item in stream:
                yield item
        except Exception as error:
            event = await self._persist_error(session_id, error)
            yield AgentRunnerStreamItem(event.type.value, event)
        final = await self.session_service.get_session(session_id)
        yield AgentRunnerStreamItem("session_status", final)
        yield AgentRunnerStreamItem(
            "stream_done",
            self._stream_done_payload(session_id, message),
        )

    async def _stream_pipeline(
        self, *, session_id: UUID, content: str
    ) -> AsyncIterator[AgentRunnerStreamItem]:
        async for kind, value in self.planner_service.stream_plan(
            session_id=session_id,
            task=content,
        ):
            if kind == "thinking":
                yield AgentRunnerStreamItem(
                    "thinking_delta",
                    {
                        "session_id": str(session_id),
                        "delta": value,
                        "phase": "planning",
                    },
                )
                continue
            _, plan_event = value
            yield AgentRunnerStreamItem(plan_event.type.value, plan_event)
        async for item in self.react_service.stream_latest_plan(session_id):
            if isinstance(item, tuple):
                kind, text = item
                yield AgentRunnerStreamItem(
                    kind,
                    {
                        "session_id": str(session_id),
                        "delta": text,
                        "phase": "final_answer",
                    },
                )
            else:
                yield AgentRunnerStreamItem(item.type.value, item)

    async def _persist_error(
        self, session_id: UUID, error: Exception
    ) -> SessionEvent:
        uow = self.session_service.uow
        event = await uow.session_events.add(
            session_id=session_id,
            event_type=SessionEventType.task_error,
            payload=build_task_error_payload(
                error,
                session_id=session_id,
                plan_id=None,
                task_id=None,
            ),
        )
        await uow.sessions.update_status(session_id, SessionStatus.failed.value)
        await uow.commit()
        return event

    @staticmethod
    def _stream_done_payload(session_id: UUID, message) -> dict[str, object]:
        return {
            "session_id": str(session_id),
            "message_id": str(message.id) if message else None,
            "message": {
                "id": str(message.id),
                "session_id": str(message.session_id),
                "role": message.role.value,
                "content": message.content,
                "created_at": message.created_at.isoformat(),
            }
            if message
            else None,
        }

    async def _reset_running_session(self, session_id: UUID) -> None:
        try:
            uow = self.session_service.uow
            session = await uow.sessions.get(session_id)
            if session is not None and session.status is SessionStatus.running:
                await uow.sessions.update_status(session_id, SessionStatus.idle.value)
                await uow.commit()
        except Exception:
            return

    async def execute_latest_plan(self, session_id: UUID) -> list[SessionEvent]:
        return await self.react_service.execute_latest_plan(session_id)
