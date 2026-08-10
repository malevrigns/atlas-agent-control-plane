from dataclasses import dataclass
from uuid import UUID

from app.application.attachment_excerpt import build_attachment_excerpt
from app.application.context_engineering_service import ContextEngineeringService
from app.application.llm_service import LLMService
from app.application.planner_service import PlannerService
from app.application.react_agent_service import ReActAgentService
from app.application.session_service import SessionService
from app.application.unit_of_work import UnitOfWork
from app.core.config import settings
from app.core.exceptions import AppException, build_task_error_payload
from app.domain.context_engineering.entities import SessionContextSnapshot
from app.domain.llm.entities import LLMMessage
from app.domain.sessions.entities import (
    Session,
    SessionEvent,
    SessionEventType,
    SessionStatus,
)
from app.infrastructure.storage.factory import build_file_storage

# 强信号：命中即进入“计划 + 工具”执行流水线。
# 注意只放歧义极小的词——“查找/保存/运行”这类词在编程问答里太常见
# （“二分查找怎么写”），会把本该像 GPT 一样直接回答的问题误送进流水线。
_PIPELINE_STRONG_KEYWORDS = (
    # 沙箱与环境
    "沙箱",
    "sandbox",
    "Sandbox",
    # 搜索与资讯
    "搜索",
    "检索一下",
    "新闻",
    "资讯",
    # 浏览器与网页操作
    "浏览器",
    "网页",
    "网站",
    "截图",
    "爬取",
    "抓取",
    # 文件动作短语（区别于“读取列表元素”这类编程语义）
    "写入文件",
    "保存到",
    "保存为",
    "存到",
    "导出到",
    "读取文件",
    "创建文件",
    "生成文件",
    # 终端
    "终端",
    "命令行",
    "shell",
    "Shell",
    # 外部集成与多 Agent
    "MCP",
    "mcp",
    "A2A",
    "a2a",
    "多 Agent",
    "多Agent",
    "远程 Agent",
    "远程智能体",
)

# 弱信号动词：必须与执行对象共现才算工具任务。
# “执行任务”“运行脚本”是流水线；“怎么运行 Python”单靠动词不触发。
_PIPELINE_ACTION_VERBS = ("执行", "运行", "跑一下", "跑个")
_PIPELINE_ACTION_OBJECTS = (
    "任务",
    "脚本",
    "命令",
    "代码",
    "程序",
    "测试",
    "pytest",
    "文件",
)


def needs_agent_pipeline(content: str) -> bool:
    """判断一条用户消息是否需要完整的计划执行流水线。

    默认走直接问答（像 GPT 一样流式回答）——这是对话产品的主路径。
    只有出现明确的工具意图（沙箱、搜索、网页、文件动作、终端、集成），
    或“执行/运行 + 对象”的组合语义时，才启动 Planner + ReAct。
    URL 一律按工具任务处理。
    """

    if "http://" in content or "https://" in content:
        return True
    if any(keyword in content for keyword in _PIPELINE_STRONG_KEYWORDS):
        return True
    if any(verb in content for verb in _PIPELINE_ACTION_VERBS) and any(
        target in content for target in _PIPELINE_ACTION_OBJECTS
    ):
        return True
    return False


@dataclass(slots=True)
class AgentRunnerStreamItem:
    """Agent Runner 推给 HTTP/SSE 层的一条可观察输出。

    `name` 对应 SSE event 名称；`payload` 保留领域对象或简单字典。
    路由层负责把领域对象转换成 Pydantic 响应模型，避免应用服务依赖 HTTP 细节。
    """

    name: str
    payload: Session | SessionEvent | dict


class AgentRunnerService:
    """统一编排一次会话任务的主执行链路。

    第 42 章把前面分散在路由里的步骤收敛到这里：
    1. 标记会话运行中。
    2. 写入用户消息和 message_created 事件。
    3. 按消息意图分流：
       - 普通问答：直接调用 LLM 流式回答，并把回答落库成 assistant 消息。
       - 工具任务：使用 Planner 生成 plan_created，再由 ReAct 按步骤执行。
    4. 读取最终会话状态并发出 stream_done。
    """

    def __init__(
        self,
        *,
        session_service: SessionService,
        planner_service: PlannerService,
        react_service: ReActAgentService,
        llm_service: LLMService | None = None,
        context_service: ContextEngineeringService | None = None,
    ) -> None:
        # ===================== 第1步：保存 Runner 需要协调的应用服务 =====================
        self.session_service = session_service
        self.planner_service = planner_service
        self.react_service = react_service
        self.llm_service = llm_service or LLMService()
        self._context_service = context_service

    @property
    def context_service(self) -> ContextEngineeringService:
        if self._context_service is None:
            self._context_service = ContextEngineeringService(self.session_service.uow)
        return self._context_service

    @classmethod
    def from_uow(
        cls,
        uow: UnitOfWork,
        *,
        planner_service: PlannerService | None = None,
    ) -> "AgentRunnerService":
        """用同一个 UnitOfWork 构建 Runner，保证执行链路使用同一事务入口。"""

        return cls(
            session_service=SessionService(uow),
            planner_service=planner_service or PlannerService(uow),
            react_service=ReActAgentService(uow),
        )

    # ===================== 第2步：运行一次用户消息驱动的 Agent 任务 =====================
    async def stream_user_message(
        self,
        *,
        session_id: UUID,
        content: str,
    ):
        """把用户消息转换成可流式观察的 Agent 执行过程。

        finally 兜底：客户端中断 SSE 时 async generator 在当前 yield 处
        被关闭，正常收尾不再执行；这里保证会话不会永远停在 running。
        """

        try:
            async for item in self._stream_user_message_inner(
                session_id=session_id,
                content=content,
            ):
                yield item
        finally:
            await self._reset_running_session(session_id)

    async def _stream_user_message_inner(
        self,
        *,
        session_id: UUID,
        content: str,
    ):
        """stream_user_message 的主体流程。"""

        # 1. 会话先进入 running，前端可以立即展示任务开始。
        running_session = await self.session_service.mark_running(session_id)
        yield AgentRunnerStreamItem(
            name="session_status",
            payload=running_session,
        )

        message = None
        try:
            # 2. 写入用户消息，并把 message_created 推给前端时间线。
            message, message_event = await self.session_service.create_user_message(
                session_id=session_id,
                content=content,
            )
            yield AgentRunnerStreamItem(
                name=message_event.type.value,
                payload=message_event,
            )

            if needs_agent_pipeline(content):
                # 3a. 工具任务：流式生成计划——规划阶段的模型思考实时推给前端，
                #     用户不再只看到“正在生成计划”的加载态。
                async for kind, value in self.planner_service.stream_plan(
                    session_id=session_id,
                    task=content,
                ):
                    if kind == "thinking":
                        yield AgentRunnerStreamItem(
                            name="thinking_delta",
                            payload={
                                "session_id": str(session_id),
                                "delta": value,
                                "phase": "planning",
                            },
                        )
                        continue
                    _plan, plan_event = value
                    yield AgentRunnerStreamItem(
                        name=plan_event.type.value,
                        payload=plan_event,
                    )

                # 4a. 执行计划。ReAct 持续产出 step/tool/task 事件；
                #     最终回答阶段还会产出 (thinking_delta|answer_delta, 文本) 增量元组，
                #     让流水线的收尾也像 GPT 一样打字机输出。
                async for item in self.react_service.stream_latest_plan(session_id):
                    if isinstance(item, tuple):
                        kind, text = item
                        yield AgentRunnerStreamItem(
                            name=kind,
                            payload={
                                "session_id": str(session_id),
                                "delta": text,
                                "phase": "final_answer",
                            },
                        )
                        continue
                    yield AgentRunnerStreamItem(
                        name=item.type.value,
                        payload=item,
                    )
            else:
                # 3b. 普通问答：跳过计划和工具，直接流式回答。
                async for item in self._stream_direct_answer(
                    session_id=session_id,
                    content=content,
                ):
                    yield item
        except Exception as error:
            # 5. 任一阶段失败，都写入统一 task_error。
            #    这样前端 SSE 不会只看到连接断开，而是能看到错误原因和建议。
            error_event = await self.session_service.uow.session_events.add(
                session_id=session_id,
                event_type=SessionEventType.task_error,
                payload=build_task_error_payload(
                    error,
                    session_id=session_id,
                    plan_id=None,
                    task_id=None,
                ),
            )
            await self.session_service.uow.sessions.update_status(
                session_id=session_id,
                status=SessionStatus.failed.value,
            )
            await self.session_service.uow.commit()
            yield AgentRunnerStreamItem(
                name=error_event.type.value,
                payload=error_event,
            )

        # 6. 推送最终会话状态和 stream_done，前端据此收尾 loading 状态。
        final_session = await self.session_service.get_session(session_id)
        yield AgentRunnerStreamItem(
            name="session_status",
            payload=final_session,
        )
        yield AgentRunnerStreamItem(
            name="stream_done",
            payload={
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
            },
        )
    async def _reset_running_session(self, session_id: UUID) -> None:
        """把仍处于 running 的会话恢复为 idle（尽力而为）。

        客户端中断 SSE 时，async generator 在当前 yield 处被关闭，
        正常收尾逻辑不再执行；不做兜底会话就永远停在“运行中”。
        """

        try:
            uow = self.session_service.uow
            session = await uow.sessions.get(session_id)
            if session is not None and session.status is SessionStatus.running:
                await uow.sessions.update_status(
                    session_id, SessionStatus.idle.value
                )
                await uow.commit()
        except Exception:
            # 连接可能已随请求关闭；兜底失败不影响主流程。
            return

    # ===================== 第3步：直接问答路径 =====================
    async def _stream_direct_answer(
        self,
        *,
        session_id: UUID,
        content: str,
    ):
        """跳过计划流水线，直接用 LLM 流式回答用户问题。

        回答过程持续产出 answer_delta；结束后把完整回答落库成
        assistant 消息（message_created），并写入 task_done 事件，
        让事件时间线和消息列表在刷新后都能还原这轮对话。
        """

        yield AgentRunnerStreamItem(
            name="answer_started",
            payload={"session_id": str(session_id), "mode": "chat"},
        )

        uow = self.session_service.uow
        snapshot = await self.context_service.build_snapshot(
            session_id,
            task=content,
        )
        attachment_excerpts = await self._load_attachment_excerpts(session_id)
        rag_context, rag_sources = await self._load_rag_context(content)
        chat_messages = self._build_chat_messages(
            snapshot, content, attachment_excerpts, rag_context
        )

        answer_parts: list[str] = []
        reasoning_parts: list[str] = []
        # 第一轮按配置请求思考过程；模型不支持 enable_thinking 而在
        # 任何输出产生前报错时，自动降级为普通流式重试一次。
        attempts: list[bool | None] = [None]
        if self.llm_service.thinking_enabled():
            attempts.append(False)

        for attempt_index, thinking in enumerate(attempts):
            try:
                async for delta in self.llm_service.chat_stream(
                    chat_messages,
                    thinking=thinking,
                ):
                    if delta.kind == "reasoning":
                        reasoning_parts.append(delta.text)
                        yield AgentRunnerStreamItem(
                            name="thinking_delta",
                            payload={"session_id": str(session_id), "delta": delta.text},
                        )
                    else:
                        answer_parts.append(delta.text)
                        yield AgentRunnerStreamItem(
                            name="answer_delta",
                            payload={"session_id": str(session_id), "delta": delta.text},
                        )
                break
            except AppException as error:
                if answer_parts or reasoning_parts:
                    # 已经流出部分内容后 provider 中断，按任务错误处理。
                    raise
                if attempt_index + 1 < len(attempts):
                    continue
                # 模型没配置或不可达时，用明确的提示回复，而不是让请求失败。
                fallback = self._build_llm_unavailable_answer(error)
                answer_parts = [fallback]
                yield AgentRunnerStreamItem(
                    name="answer_delta",
                    payload={"session_id": str(session_id), "delta": fallback},
                )

        final_answer = "".join(answer_parts).strip() or "模型没有返回内容，请重试。"
        reasoning = "".join(reasoning_parts).strip()

        # 回答落库：消息列表和事件时间线都能看到这轮回答。
        message, message_event = await self.session_service.create_assistant_message(
            session_id=session_id,
            content=final_answer,
        )
        yield AgentRunnerStreamItem(
            name=message_event.type.value,
            payload=message_event,
        )

        done_event = await uow.session_events.add(
            session_id=session_id,
            event_type=SessionEventType.task_done,
            payload={
                "mode": "chat",
                "final_answer": final_answer,
                # 思考过程与回答消息关联，客户端刷新后仍能展开查看。
                "reasoning": reasoning,
                "message_id": str(message.id),
                "message": "问答完成。",
                "memory_ids": [
                    str(item.id) for item in snapshot.memory_context.items
                ],
                "memory_count": len(snapshot.memory_context.items),
                # 本轮自动检索命中的知识库文档，便于前端展示引用来源。
                "rag_sources": rag_sources,
            },
        )
        await uow.sessions.update_status(session_id, SessionStatus.idle.value)
        await uow.sessions.touch(session_id)
        await uow.commit()
        yield AgentRunnerStreamItem(
            name=done_event.type.value,
            payload=done_event,
        )

    async def _load_rag_context(self, question: str) -> tuple[str, list[str]]:
        """直答前自动检索所有知识库，返回（注入文本, 命中文档标题）。

        与 knowledge_search 工具一致，用独立数据库会话执行检索，
        不与当前请求事务纠缠。任何失败（无知识库、向量服务异常、
        测试环境无数据库）都静默降级为无知识库上下文，绝不阻断问答。
        """

        if settings.chat_rag_top_k <= 0:
            return "", []
        try:
            from app.application.rag_service import RagService
            from app.infrastructure.database.session import AsyncSessionLocal

            async with AsyncSessionLocal() as db_session:
                service = RagService(UnitOfWork(db_session))
                bases = await service.list_knowledge_bases()
                scored: list[tuple[str, object]] = []
                for base in bases:
                    if not base.chunk_count:
                        continue
                    result = await service.query(
                        base.id,
                        query=question,
                        top_k=settings.chat_rag_top_k,
                        record_trace=False,
                    )
                    scored.extend((base.name, chunk) for chunk in result.chunks)
        except Exception:  # noqa: BLE001 —— RAG 是增强项，失败不影响直答。
            return "", []

        relevant = sorted(
            (
                item
                for item in scored
                if item[1].final_score >= settings.chat_rag_min_score
            ),
            key=lambda item: item[1].final_score,
            reverse=True,
        )[: settings.chat_rag_top_k]
        if not relevant:
            return "", []

        lines: list[str] = []
        sources: list[str] = []
        remaining = settings.chat_rag_context_chars
        for index, (base_name, chunk) in enumerate(relevant, start=1):
            content_text = chunk.content.strip()
            if len(content_text) > remaining:
                content_text = content_text[:remaining]
            remaining -= len(content_text)
            lines.append(
                f"[{index}]《{chunk.document_title}》（知识库：{base_name}，"
                f"相关度 {chunk.final_score:.2f}）：\n{content_text}"
            )
            if chunk.document_title not in sources:
                sources.append(chunk.document_title)
            if remaining <= 0:
                break
        return "\n\n".join(lines), sources

    async def _load_attachment_excerpts(
        self,
        session_id: UUID,
    ) -> list[tuple[str, str]]:
        """读取最近几个会话附件的文本节选，供直答上下文注入。

        文本类附件直接解码，PDF 用 pypdf 抽取文本层；不支持或过大的
        附件返回明确说明，避免模型只看到文件名后编造内容。
        """

        try:
            session_files = await self.session_service.uow.session_files.list_by_session(
                session_id
            )
        except Exception:
            return []
        if not session_files:
            return []

        storage = build_file_storage()
        excerpts: list[tuple[str, str]] = []
        remaining = settings.chat_attachment_context_chars
        for session_file in session_files[-settings.chat_attachment_limit :]:
            file_object = session_file.file
            name = file_object.original_name
            if remaining <= 0:
                excerpts.append((name, "（附件内容预算已用完，本文件未注入。）"))
                continue
            if file_object.size > settings.chat_attachment_max_file_bytes:
                excerpts.append(
                    (name, "（文件过大，未注入内容；可拆分后重新上传。）")
                )
                continue
            try:
                data = storage.read_bytes(file_object.storage_path)
            except Exception:
                excerpts.append((name, "（读取文件内容失败。）"))
                continue
            excerpt = build_attachment_excerpt(
                filename=name,
                content_type=file_object.content_type,
                data=data,
                char_budget=remaining,
            )
            if excerpt is None:
                excerpts.append(
                    (
                        name,
                        f"（{file_object.content_type or '未知类型'} 格式暂不支持内容提取，"
                        "仅可引用文件名与大小。）",
                    )
                )
                continue
            remaining -= len(excerpt)
            excerpts.append((name, excerpt))
        return excerpts

    def _build_chat_messages(
        self,
        snapshot: SessionContextSnapshot,
        content: str,
        attachment_excerpts: list[tuple[str, str]] | None = None,
        rag_context: str = "",
    ) -> list[LLMMessage]:
        """把上下文快照转换成多轮对话消息。

        最近消息按原始角色还原成对话轮次；长期记忆和附件内容
        进入 system 提示，模型可以引用但不会把它们误当成用户发言。
        """

        sections: list[str] = [
            "你是 AtlasAgent，一个严谨的中文 AI 助手。"
            "请直接回答用户的问题：答案准确、结构清晰，可以使用 Markdown。"
            "不知道就说不知道，不要编造。",
        ]
        if snapshot.summary:
            sections.append(f"会话概要：{snapshot.summary}")
        if snapshot.memory_context.items:
            memory_lines = "\n".join(
                f"- [{item.kind.value}] {item.content}"
                for item in snapshot.memory_context.items
            )
            sections.append(f"长期记忆（可参考，不要复述）：\n{memory_lines}")
        if rag_context:
            sections.append(
                "知识库检索结果（系统已自动检索，按相关度排序）：\n"
                f"{rag_context}\n\n"
                "回答与知识库内容相关的问题时，优先依据以上片段作答，"
                "并在对应句子末尾用（来源：《文档标题》）标注引用；"
                "片段与问题无关时直接忽略，不要强行引用，"
                "也不要编造知识库里没有的内容。"
            )
        if attachment_excerpts:
            attachment_blocks = "\n\n".join(
                f"《{name}》：\n{excerpt}" for name, excerpt in attachment_excerpts
            )
            sections.append(
                "会话附件内容（回答时可直接引用，注明出自哪个附件）：\n"
                f"{attachment_blocks}"
            )
        elif snapshot.files:
            file_lines = "\n".join(
                f"- {file.name}（{file.content_type}，{file.size} 字节）"
                for file in snapshot.files
            )
            sections.append(f"会话附件清单：\n{file_lines}")

        messages: list[LLMMessage] = [
            LLMMessage(role="system", content="\n\n".join(sections)),
        ]
        for context_message in snapshot.messages:
            if context_message.role not in {"user", "assistant"}:
                continue
            messages.append(
                LLMMessage(role=context_message.role, content=context_message.content)
            )

        # 快照为空时兜底，保证至少携带当前问题。
        if len(messages) == 1 or messages[-1].role != "user":
            messages.append(LLMMessage(role="user", content=content))
        return messages

    @staticmethod
    def _build_llm_unavailable_answer(error: AppException) -> str:
        """模型不可用时给用户可执行的排查指引。"""

        return (
            "当前无法调用模型服务，所以这条消息没有得到 AI 回答。\n\n"
            f"- 原因：{error.message}\n"
            "- 请在服务端配置 `LLM_API_KEY` 环境变量（OpenAI 兼容服务的密钥），"
            "并确认 `backend/api/config/llm.yaml` 中的 `base_url` 与 `default_model` 正确。\n"
            "- 配置完成后重启 API 服务，再发送一条消息即可。"
        )

    # ===================== 第4步：运行已有计划，供同步接口和后台任务复用 =====================
    async def execute_latest_plan(self, session_id: UUID) -> list[SessionEvent]:
        """执行会话最近一次计划，保持旧接口兼容。"""

        return await self.react_service.execute_latest_plan(session_id)
