from collections import Counter
from uuid import UUID

from app.application.memory_retrieval_service import MemoryRetrievalService
from app.application.unit_of_work import UnitOfWork
from app.core.config import settings
from app.core.exceptions import AppException
from app.domain.context_engineering.entities import (
    ContextBudget,
    ContextEventSummary,
    ContextFileReference,
    ContextMessage,
    MemoryContext,
    SessionContextSnapshot,
)
from app.domain.files.entities import SessionFile
from app.domain.sessions.entities import SessionEvent, SessionMessage


class ContextEngineeringService:
    """生成会话上下文快照。

    上下文快照不是把所有历史内容原样塞给 Agent。
    它会按预算裁剪消息、压缩事件、只引用文件清单，为后续长任务执行打基础。
    """

    def __init__(self, uow: UnitOfWork) -> None:
        # ===================== 第1步：保存数据库事务入口 =====================
        self.uow = uow

    # ===================== 第2步：构建当前会话上下文快照 =====================
    async def build_snapshot(
        self,
        session_id: UUID,
        *,
        task: str | None = None,
    ) -> SessionContextSnapshot:
        """读取会话数据，并转换成适合 Agent 继续执行的上下文。"""

        # 1. 会话标题是长期稳定的任务线索，也会参与记忆检索。
        session = await self.uow.sessions.get(session_id)
        if session is None:
            raise AppException(
                message="session not found",
                code=404,
                status_code=404,
            )

        # 2. 读取当前会话的短期上下文数据。
        messages = await self.uow.session_messages.list_by_session(session_id)
        events = await self.uow.session_events.list_by_session(session_id)
        files = await self.uow.session_files.list_by_session(session_id)

        # 3. 先按原有预算构建短期消息、事件摘要和文件引用。
        context_messages = self._build_messages(messages)
        event_summaries = self._build_event_summaries(events)
        file_references = self._build_file_references(files)

        # 4. 使用当前任务、会话标题和最近消息构建长期记忆检索查询。
        memory_query = self._build_memory_query(
            task=task,
            session_title=session.title,
            messages=messages,
        )
        memory_context = await MemoryRetrievalService(self.uow).retrieve(
            query=memory_query,
            project_id="default",
        )

        # 4.5 用同一份检索查询挑选可注入的已发布技能。
        #     技能来自注册中心（published + enabled），失败时不阻塞会话上下文。
        skill_context = None
        try:
            from app.application.skill_service import SkillService

            skill_context = await SkillService(self.uow).build_skill_context(
                query=memory_query,
            )
        except Exception:  # noqa: BLE001 - 技能注入是增强项，不能拖垮上下文构建
            skill_context = None

        # 5. 汇总短期上下文和长期记忆的独立预算。
        budget = self._build_budget(
            all_messages=messages,
            included_messages=context_messages,
            all_events=events,
            memory_context=memory_context,
        )
        summary = self._build_summary(
            message_count=len(messages),
            event_count=len(events),
            file_count=len(files),
            budget=budget,
        )

        return SessionContextSnapshot(
            session_id=session_id,
            summary=summary,
            messages=context_messages,
            event_summaries=event_summaries,
            files=file_references,
            memory_context=memory_context,
            budget=budget,
            skill_context=skill_context,
        )

    # ===================== 第3步：裁剪消息上下文 =====================
    def _build_messages(self, messages: list[SessionMessage]) -> list[ContextMessage]:
        """只保留最近几条消息，并裁剪过长内容。"""

        recent_messages = messages[-settings.context_message_limit :]
        context_messages: list[ContextMessage] = []
        for message in recent_messages:
            content = message.content
            truncated = len(content) > settings.context_max_message_chars
            if truncated:
                content = content[: settings.context_max_message_chars] + "\n...[内容已裁剪]"
            context_messages.append(
                ContextMessage(
                    role=message.role.value,
                    content=content,
                    original_chars=len(message.content),
                    truncated=truncated,
                    created_at=message.created_at,
                )
            )
        return context_messages

    # ===================== 第4步：压缩事件上下文 =====================
    def _build_event_summaries(
        self,
        events: list[SessionEvent],
    ) -> list[ContextEventSummary]:
        """把大量事件压缩成按类型聚合的摘要。"""

        recent_events = events[-settings.context_event_limit :]
        counts = Counter(event.type.value for event in recent_events)
        latest_by_type: dict[str, SessionEvent] = {}
        for event in recent_events:
            latest_by_type[event.type.value] = event

        return [
            ContextEventSummary(
                type=event_type,
                count=count,
                latest_at=latest_by_type[event_type].created_at,
            )
            for event_type, count in counts.items()
        ]

    # ===================== 第5步：把文件变成引用清单 =====================
    def _build_file_references(
        self,
        files: list[SessionFile],
    ) -> list[ContextFileReference]:
        """上下文中只放文件引用，不直接塞入完整文件内容。"""

        return [
            ContextFileReference(
                id=session_file.file.id,
                name=session_file.file.original_name,
                content_type=session_file.file.content_type,
                size=session_file.file.size,
                usage_hint=self._build_file_usage_hint(session_file),
            )
            for session_file in files
        ]

    # ===================== 第6步：计算上下文预算 =====================
    def _build_budget(
        self,
        all_messages: list[SessionMessage],
        included_messages: list[ContextMessage],
        all_events: list[SessionEvent],
        memory_context: MemoryContext,
    ) -> ContextBudget:
        total_chars = sum(len(message.content) for message in included_messages)
        return ContextBudget(
            message_limit=settings.context_message_limit,
            event_limit=settings.context_event_limit,
            max_message_chars=settings.context_max_message_chars,
            included_messages=len(included_messages),
            omitted_messages=max(len(all_messages) - len(included_messages), 0),
            included_events=min(len(all_events), settings.context_event_limit),
            omitted_events=max(len(all_events) - settings.context_event_limit, 0),
            total_message_chars=total_chars,
            memory_limit=settings.context_memory_limit,
            max_memory_chars=settings.context_memory_max_chars,
            included_memories=len(memory_context.items),
            omitted_memories=memory_context.omitted_count,
            total_memory_chars=memory_context.total_chars,
        )

    def _build_summary(
        self,
        message_count: int,
        event_count: int,
        file_count: int,
        budget: ContextBudget,
    ) -> str:
        return (
            f"当前会话共有 {message_count} 条消息、{event_count} 条事件、"
            f"{file_count} 个文件引用；本次上下文纳入 {budget.included_messages} 条最近消息，"
            f"压缩 {budget.included_events} 条最近事件，并注入 "
            f"{budget.included_memories} 条长期记忆。"
        )

    # ===================== 第7步：构建长期记忆检索查询 =====================
    @staticmethod
    def _build_memory_query(
        *,
        task: str | None,
        session_title: str,
        messages: list[SessionMessage],
    ) -> str:
        """把当前任务、会话标题和最近消息合并为检索文本。"""

        parts = [task or "", session_title]
        parts.extend(message.content for message in messages[-3:])
        return "\n".join(part.strip() for part in parts if part.strip())

    # ===================== 第8步：把上下文快照渲染成 Agent 提示词 =====================
    @staticmethod
    def render_for_agent(snapshot: SessionContextSnapshot) -> str:
        """生成 Planner 和 ReAct 可以直接使用的紧凑上下文文本。"""

        sections: list[str] = []

        if snapshot.skill_context is not None and snapshot.skill_context.items:
            from app.application.skill_service import SkillService

            rendered_skills = SkillService.render_skill_context(snapshot.skill_context)
            if rendered_skills:
                sections.append(rendered_skills)

        if snapshot.memory_context.items:
            memory_lines = [
                (
                    f"- [{item.kind.value}] {item.content} "
                    f"(重要度 {item.importance}，相关度 {item.relevance_score:.2f})"
                )
                for item in snapshot.memory_context.items
            ]
            sections.append("长期记忆：\n" + "\n".join(memory_lines))

        if snapshot.messages:
            message_lines = [
                f"- {message.role}: {message.content}"
                for message in snapshot.messages
            ]
            sections.append("最近消息：\n" + "\n".join(message_lines))

        if snapshot.files:
            file_lines = [
                f"- {file.name} ({file.content_type}, {file.usage_hint})"
                for file in snapshot.files
            ]
            sections.append("文件引用：\n" + "\n".join(file_lines))

        return "\n\n".join(sections)

    @staticmethod
    def _build_file_usage_hint(session_file: SessionFile) -> str:
        file = session_file.file
        if file.content_type.startswith("text/") or file.content_type in {
            "application/json",
            "application/xml",
            "application/yaml",
        }:
            return "可在需要时读取文本预览或下载内容。"
        return "当前只作为文件引用放入上下文，暂不直接读取内容。"
