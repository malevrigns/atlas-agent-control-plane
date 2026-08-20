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
from app.domain.llm.entities import LLMMessage
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
        self,
        *,
        session_id: UUID,
        content: str,
        skill_ids: list[UUID] | None = None,
        resume: bool = False,
    ) -> AsyncIterator[AgentRunnerStreamItem]:
        try:
            async for item in self._stream_user_message_inner(
                session_id=session_id,
                content=content,
                skill_ids=skill_ids,
                resume=resume,
            ):
                yield item
        finally:
            await self._reset_running_session(session_id)

    async def _stream_user_message_inner(
        self,
        *,
        session_id: UUID,
        content: str,
        skill_ids: list[UUID] | None = None,
        resume: bool = False,
    ) -> AsyncIterator[AgentRunnerStreamItem]:
        running = await self.session_service.mark_running(session_id)
        yield AgentRunnerStreamItem("session_status", running)
        message = None
        try:
            if resume:
                stream = self._stream_resume(session_id=session_id)
            else:
                message, message_event = await self.session_service.create_user_message(
                    session_id=session_id,
                    content=content,
                )
                yield AgentRunnerStreamItem(message_event.type.value, message_event)

                # 用户显式调用的技能（/ 触发）：流水线拼进规划任务，直答注入 system 上下文。
                invoked_skills = await self._load_invoked_skills(skill_ids)

                if needs_agent_pipeline(content):
                    task_text = content
                    if invoked_skills:
                        skill_blocks = "\n\n".join(
                            f"《{label}》：\n{instructions}"
                            for label, instructions in invoked_skills
                        )
                        task_text = (
                            f"{content}\n\n[用户显式调用的技能指引，规划与执行时必须遵循]\n"
                            f"{skill_blocks}"
                        )
                    stream = self._stream_pipeline(
                        session_id=session_id, content=task_text
                    )
                else:
                    stream = self.direct_chat_service.stream(
                        session_id=session_id,
                        content=content,
                        invoked_skills=invoked_skills,
                    )
            async for item in stream:
                yield item
        except Exception as error:
            event = await self._persist_error(session_id, error)
            yield AgentRunnerStreamItem(event.type.value, event)
        if not resume:
            await self._auto_title(session_id, content)
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

    async def _stream_resume(
        self, *, session_id: UUID
    ) -> AsyncIterator[AgentRunnerStreamItem]:
        """从上次失败处续跑：不重新规划、不重复创建用户消息。"""

        async for item in self.react_service.stream_latest_plan(session_id, resume=True):
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

    async def _load_invoked_skills(
        self,
        skill_ids: list[UUID] | None,
    ) -> list[tuple[str, str]]:
        """加载用户显式调用（/ 触发）的技能指引。

        只接受 published 且启用的技能；查询失败静默降级为空，
        与 RAG 自动召回一致——增强项不阻断问答主链路。
        """

        if not skill_ids:
            return []
        try:
            from app.application.skill_service import SkillService
            from app.domain.skills.entities import SkillStatus
            from app.infrastructure.database.session import AsyncSessionLocal

            async with AsyncSessionLocal() as db_session:
                service = SkillService(UnitOfWork(db_session))
                loaded: list[tuple[str, str]] = []
                for skill_id in skill_ids[:4]:
                    try:
                        skill = await service.get_skill(skill_id)
                    except Exception:  # noqa: BLE001 —— 单个技能失效不影响其余。
                        continue
                    if skill.status is not SkillStatus.published or not skill.enabled:
                        continue
                    if not skill.instructions.strip():
                        continue
                    loaded.append(
                        (f"{skill.name} v{skill.version}", skill.instructions.strip())
                    )
                return loaded
        except Exception:  # noqa: BLE001
            return []

    async def _auto_title(self, session_id: UUID, content: str) -> None:
        """首条消息自动生成会话标题（仅当会话还是默认标题时）。

        标题生成放在回答之后，不阻塞用户看到正文；失败静默降级，
        保留「新工作区」占位标题。
        """

        session = await self.session_service.get_session(session_id)
        if session.title != "新工作区":
            return
        try:
            result = await self.llm_service.chat(
                messages=[
                    LLMMessage(
                        role="system",
                        content=(
                            "你是会话标题生成器。根据用户的任务或问题，生成一个不超过 12 个字的"
                            "简短中文标题。只输出标题本身，不要引号、标点或解释。"
                        ),
                    ),
                    LLMMessage(role="user", content=content[:200]),
                ],
                temperature=0.2,
                max_tokens=32,
            )
        except Exception:  # noqa: BLE001 —— 标题是增强项，失败不影响主链路。
            return
        title = result.content.strip().strip('\"\'“”「」').strip()[:24]
        if title:
            await self.session_service.update_title(session_id, title)

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
