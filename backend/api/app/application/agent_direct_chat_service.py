from collections.abc import AsyncIterator
from uuid import UUID

from app.application.agent_runner_types import AgentRunnerStreamItem, DirectAnswer
from app.application.attachment_excerpt import build_attachment_excerpt
from app.application.context_engineering_service import ContextEngineeringService
from app.application.llm_service import LLMService
from app.application.session_service import SessionService
from app.application.unit_of_work import UnitOfWork
from app.core.config import settings
from app.core.exceptions import AppException
from app.domain.context_engineering.entities import SessionContextSnapshot
from app.domain.llm.entities import LLMMessage
from app.domain.sessions.entities import SessionEventType, SessionStatus
from app.infrastructure.storage.factory import build_file_storage


class AgentDirectChatService:
    def __init__(
        self,
        session_service: SessionService,
        model: LLMService,
        context_service: ContextEngineeringService,
    ) -> None:
        self.session_service = session_service
        self.model = model
        self.context_service = context_service

    async def stream(
        self,
        *,
        session_id: UUID,
        content: str,
        invoked_skills: list[tuple[str, str]] | None = None,
    ) -> AsyncIterator[AgentRunnerStreamItem]:
        payload = {"session_id": str(session_id), "mode": "chat"}
        yield AgentRunnerStreamItem("answer_started", payload)
        snapshot = await self.context_service.build_snapshot(session_id, task=content)
        attachments = await self._load_attachment_excerpts(session_id)
        rag_context, rag_sources = await self._load_rag_context(content)
        messages = self._build_chat_messages(
            snapshot=snapshot,
            content=content,
            attachment_excerpts=attachments,
            rag_context=rag_context,
            invoked_skills=invoked_skills,
        )
        result = None
        async for item in self._stream_model(session_id, messages):
            if isinstance(item, DirectAnswer):
                result = item
            else:
                yield item
        if result is None:
            raise AppException(message="direct answer stream returned no result")
        async for item in self._persist_answer(
            session_id=session_id,
            snapshot=snapshot,
            result=result,
            rag_sources=rag_sources,
        ):
            yield item

    async def _stream_model(
        self, session_id: UUID, messages: list[LLMMessage]
    ) -> AsyncIterator[AgentRunnerStreamItem | DirectAnswer]:
        answers: list[str] = []
        reasoning: list[str] = []
        delta_routes = {"reasoning": (reasoning, "thinking_delta")}
        attempts: list[bool | None] = [None]
        if self.model.thinking_enabled():
            attempts.append(False)
        for attempt_index, thinking in enumerate(attempts):
            try:
                async for delta in self.model.chat_stream(messages, thinking=thinking):
                    target, name = delta_routes.get(delta.kind, (answers, "answer_delta"))
                    target.append(delta.text)
                    yield AgentRunnerStreamItem(
                        name, {"session_id": str(session_id), "delta": delta.text}
                    )
                break
            except AppException as error:
                if answers or reasoning:
                    raise
                if attempt_index + 1 < len(attempts):
                    continue
                fallback = self._build_llm_unavailable_answer(error)
                answers = [fallback]
                yield AgentRunnerStreamItem(
                    "answer_delta", {"session_id": str(session_id), "delta": fallback}
                )
        content = "".join(answers).strip() or "模型没有返回内容，请重试。"
        yield DirectAnswer(content, "".join(reasoning).strip())

    async def _persist_answer(
        self,
        *,
        session_id: UUID,
        snapshot: SessionContextSnapshot,
        result: DirectAnswer,
        rag_sources: list[str],
    ) -> AsyncIterator[AgentRunnerStreamItem]:
        message, message_event = await self.session_service.create_assistant_message(
            session_id=session_id,
            content=result.content,
        )
        yield AgentRunnerStreamItem(message_event.type.value, message_event)
        uow = self.session_service.uow
        done = await uow.session_events.add(
            session_id=session_id,
            event_type=SessionEventType.task_done,
            payload={
                "mode": "chat",
                "final_answer": result.content,
                "reasoning": result.reasoning,
                "message_id": str(message.id),
                "message": "问答完成。",
                "memory_ids": [str(item.id) for item in snapshot.memory_context.items],
                "memory_count": len(snapshot.memory_context.items),
                "rag_sources": rag_sources,
            },
        )
        await uow.sessions.update_status(session_id, SessionStatus.idle.value)
        await uow.sessions.touch(session_id)
        await uow.commit()
        yield AgentRunnerStreamItem(done.type.value, done)

    async def _load_rag_context(self, question: str) -> tuple[str, list[str]]:
        if settings.chat_rag_top_k <= 0:
            return "", []
        scored = await self._query_rag_chunks(question)
        relevant = sorted(
            (
                item
                for item in scored
                if item[1].final_score >= settings.chat_rag_min_score
            ),
            key=lambda item: item[1].final_score,
            reverse=True,
        )[: settings.chat_rag_top_k]
        return self._render_rag_context(relevant)

    @staticmethod
    async def _query_rag_chunks(question: str) -> list[tuple[str, object]]:
        try:
            from app.application.rag_service import RagService
            from app.infrastructure.database.session import AsyncSessionLocal

            async with AsyncSessionLocal() as db_session:
                service = RagService(UnitOfWork(db_session))
                bases = await service.list_knowledge_bases()
                scored: list[tuple[str, object]] = []
                available = (base for base in bases if base.chunk_count)
                for base in available:
                    result = await service.query(
                        base.id,
                        query=question,
                        top_k=settings.chat_rag_top_k,
                        record_trace=False,
                    )
                    scored.extend((base.name, chunk) for chunk in result.chunks)
                return scored
        except Exception:  # noqa: BLE001 - RAG remains optional for direct chat.
            return []

    @staticmethod
    def _render_rag_context(relevant: list[tuple[str, object]]) -> tuple[str, list[str]]:
        lines: list[str] = []
        sources: list[str] = []
        remaining = settings.chat_rag_context_chars
        for index, (base_name, chunk) in enumerate(relevant, start=1):
            content = chunk.content.strip()[:remaining]
            remaining -= len(content)
            lines.append(
                f"[{index}]《{chunk.document_title}》（知识库：{base_name}，"
                f"相关度 {chunk.final_score:.2f}）：\n{content}"
            )
            if chunk.document_title not in sources:
                sources.append(chunk.document_title)
            if remaining <= 0:
                break
        return "\n\n".join(lines), sources

    async def _load_attachment_excerpts(
        self, session_id: UUID
    ) -> list[tuple[str, str]]:
        try:
            files = await self.session_service.uow.session_files.list_by_session(session_id)
        except Exception:
            return []
        storage = build_file_storage()
        excerpts: list[tuple[str, str]] = []
        remaining = settings.chat_attachment_context_chars
        for session_file in files[-settings.chat_attachment_limit :]:
            name, excerpt, consumed = self._attachment_excerpt(
                session_file, remaining, storage
            )
            excerpts.append((name, excerpt))
            remaining -= consumed
        return excerpts

    @staticmethod
    def _attachment_excerpt(
        session_file, remaining: int, storage
    ) -> tuple[str, str, int]:
        file_object = session_file.file
        name = file_object.original_name
        if remaining <= 0:
            return name, "（附件内容预算已用完，本文件未注入。）", 0
        if file_object.size > settings.chat_attachment_max_file_bytes:
            return name, "（文件过大，未注入内容；可拆分后重新上传。）", 0
        try:
            data = storage.read_bytes(file_object.storage_path)
        except Exception:
            return name, "（读取文件内容失败。）", 0
        excerpt = build_attachment_excerpt(
            filename=name,
            content_type=file_object.content_type,
            data=data,
            char_budget=remaining,
        )
        if excerpt is not None:
            return name, excerpt, len(excerpt)
        content_type = file_object.content_type or "未知类型"
        text = f"（{content_type} 格式暂不支持内容提取，仅可引用文件名与大小。）"
        return name, text, 0

    def _build_chat_messages(
        self,
        *,
        snapshot: SessionContextSnapshot,
        content: str,
        attachment_excerpts: list[tuple[str, str]],
        rag_context: str,
        invoked_skills: list[tuple[str, str]] | None = None,
    ) -> list[LLMMessage]:
        sections = self._build_system_sections(snapshot, rag_context)
        self._append_invoked_skills(sections, invoked_skills)
        self._append_attachment_context(sections, snapshot, attachment_excerpts)
        messages = [LLMMessage(role="system", content="\n\n".join(sections))]
        messages.extend(
            LLMMessage(role=item.role, content=item.content)
            for item in snapshot.messages
            if item.role in {"user", "assistant"}
        )
        if len(messages) == 1 or messages[-1].role != "user":
            messages.append(LLMMessage(role="user", content=content))
        return messages

    @staticmethod
    def _build_system_sections(
        snapshot: SessionContextSnapshot, rag_context: str
    ) -> list[str]:
        sections = [
            "你是 AtlasAgent，一个严谨的中文 AI 助手。"
            "请直接回答用户的问题：答案准确、结构清晰，可以使用 Markdown。"
            "不知道就说不知道，不要编造。"
        ]
        if snapshot.summary:
            sections.append(f"会话概要：{snapshot.summary}")
        if snapshot.memory_context.items:
            memories = "\n".join(
                f"- [{item.kind.value}] {item.content}"
                for item in snapshot.memory_context.items
            )
            sections.append(f"长期记忆（可参考，不要复述）：\n{memories}")
        if rag_context:
            sections.append(
                "知识库检索结果（系统已自动检索，按相关度排序）：\n"
                f"{rag_context}\n\n"
                "回答与知识库内容相关的问题时，优先依据以上片段作答，"
                "并在对应句子末尾用（来源：《文档标题》）标注引用；"
                "片段与问题无关时直接忽略，不要强行引用，"
                "也不要编造知识库里没有的内容。"
            )
        return sections

    @staticmethod
    def _append_invoked_skills(
        sections: list[str],
        invoked_skills: list[tuple[str, str]] | None,
    ) -> None:
        if invoked_skills:
            skill_blocks = "\n\n".join(
                f"《{label}》：\n{instructions}"
                for label, instructions in invoked_skills
            )
            sections.append(
                "用户本轮通过 / 显式调用了以下技能，回答时必须遵循其中的操作指引：\n"
                f"{skill_blocks}"
            )

    @staticmethod
    def _append_attachment_context(
        sections: list[str],
        snapshot: SessionContextSnapshot,
        excerpts: list[tuple[str, str]],
    ) -> None:
        if excerpts:
            blocks = "\n\n".join(f"《{name}》：\n{text}" for name, text in excerpts)
            sections.append(
                "会话附件内容（回答时可直接引用，注明出自哪个附件）：\n"
                f"{blocks}"
            )
            return
        if snapshot.files:
            files = "\n".join(
                f"- {item.name}（{item.content_type}，{item.size} 字节）"
                for item in snapshot.files
            )
            sections.append(f"会话附件清单：\n{files}")

    @staticmethod
    def _build_llm_unavailable_answer(error: AppException) -> str:
        return (
            "当前无法调用模型服务，所以这条消息没有得到 AI 回答。\n\n"
            f"- 原因：{error.message}\n"
            "- 请在服务端配置 `LLM_API_KEY` 环境变量（OpenAI 兼容服务的密钥），"
            "并确认 `backend/api/config/llm.yaml` 中的 `base_url` 与 `default_model` 正确。\n"
            "- 配置完成后重启 API 服务，再发送一条消息即可。"
        )
