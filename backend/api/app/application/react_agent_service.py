import json
from pathlib import Path
from uuid import UUID
from urllib.parse import urlparse

from app.application.context_engineering_service import ContextEngineeringService
from app.application.llm_service import LLMService
from app.application.react_step_executor import (
    ReActStepExecutor,
    StepExecutionOutcome,
    StepExecutionRequest,
)
from app.application.tool_selection_service import ModelToolSelectionService
from app.application.tool_runtime import ToolExecutionContext
from app.application.unit_of_work import UnitOfWork
from app.core.config import settings
from app.core.exceptions import AppException, build_task_error_payload
from app.domain.agent_core.tools import ToolInvocationStatus
from app.domain.context_engineering.entities import MemoryContext
from app.domain.agent_runtime.router import FINAL_FAILURE_STATUSES, SUCCESS_STATUSES
from app.domain.llm.entities import LLMMessage
from app.domain.sessions.entities import SessionEvent, SessionEventType, SessionStatus
from app.infrastructure.agent_tools.builtin import build_builtin_tool_registry
from app.infrastructure.sandbox.file_client import SandboxFileClient
from app.infrastructure.storage.factory import build_file_storage


class ReActAgentService:
    """第 19 章的 ReActAgent 同步执行服务。

    本章先把计划步骤转成可观察事件，不引入后台队列。
    第 20 章会把这里的执行过程迁移到 Redis Stream 和 TaskRunner。
    """

    def __init__(
        self,
        uow: UnitOfWork,
        step_executor: ReActStepExecutor | None = None,
    ) -> None:
        # ===================== 第1步：保存数据库事务和工具注册表 =====================
        self.uow = uow
        self.registry = build_builtin_tool_registry()
        self.tool_selector = ModelToolSelectionService(registry=self.registry, uow=uow)
        self.step_executor = step_executor or ReActStepExecutor(
            uow=uow,
            tool_caller=self._call_tool_for_step,
            output_summarizer=self._summarize_tool_output,
        )

    # ===================== 第2步：执行当前会话的最新计划 =====================
    async def execute_latest_plan(self, session_id: UUID) -> list[SessionEvent]:
        """执行最近一次 plan_created 事件中的计划步骤。"""

        session = await self.uow.sessions.get(session_id)
        if session is None:
            raise AppException(
                message="session not found",
                code=404,
                status_code=404,
            )

        events = await self.uow.session_events.list_by_session(session_id)
        plan_event = self._find_latest_plan_event(events)
        plan = plan_event.payload
        steps = plan.get("steps", [])
        if not steps:
            raise AppException(
                message="plan has no steps",
                code=400,
                status_code=400,
            )

        # ReAct 使用和 Planner 相同的统一上下文快照，避免两套记忆检索结果。
        context_snapshot = await ContextEngineeringService(self.uow).build_snapshot(
            session_id,
            task=str(plan.get("goal", "")),
        )
        await self._sync_session_files_to_sandbox(session_id)
        memory_context = context_snapshot.memory_context
        agent_context = ContextEngineeringService.render_for_agent(context_snapshot)

        created_events: list[SessionEvent] = []
        step_history: list[str] = []
        current_step: dict | None = None
        current_index = 0
        await self.uow.sessions.update_status(session_id, SessionStatus.running.value)
        await self.uow.commit()

        try:
            for index, step in enumerate(steps, start=1):
                current_step = step
                current_index = index
                step_events = await self._execute_step(
                    session_id=session_id,
                    plan=plan,
                    step=step,
                    index=index,
                    memory_context=memory_context,
                    agent_context=agent_context,
                    step_history=step_history,
                )
                created_events.extend(step_events)
                self._append_step_history(step_history, index, step, step_events)
                # 每个步骤结束后提交一次，SSE 层才能把最新事件及时推给前端。
                await self.uow.sessions.touch(session_id)
                await self.uow.commit()

            final_answer = await self._build_final_answer(plan, created_events)
            answer_event = await self._persist_final_answer_message(
                session_id=session_id,
                final_answer=final_answer,
            )
            created_events.append(answer_event)
            done_event = await self.uow.session_events.add(
                session_id=session_id,
                event_type=SessionEventType.task_done,
                payload={
                    "plan_id": plan.get("id") or plan.get("plan_id"),
                    "final_answer": final_answer,
                    "message": "计划步骤已全部执行完成。",
                    "memory_ids": [str(item.id) for item in memory_context.items],
                    "memory_count": len(memory_context.items),
                },
            )
            created_events.append(done_event)
            await self.uow.sessions.update_status(session_id, SessionStatus.idle.value)
            await self.uow.sessions.touch(session_id)
            await self.uow.commit()
            return created_events
        except Exception as error:
            error_payload = build_task_error_payload(
                error,
                session_id=session_id,
                plan_id=plan.get("id") or plan.get("plan_id"),
                step=current_step,
                step_index=current_index,
            )
            error_event = await self.uow.session_events.add(
                session_id=session_id,
                event_type=SessionEventType.task_error,
                payload=error_payload,
            )
            await self.uow.sessions.update_status(session_id, SessionStatus.failed.value)
            await self.uow.commit()
            return [*created_events, error_event]

    # ===================== 第3步：执行单个计划步骤 =====================
    async def _execute_step(
        self,
        session_id: UUID,
        plan: dict,
        step: dict,
        index: int,
        memory_context: MemoryContext,
        agent_context: str,
        step_history: list[str] | None = None,
    ) -> list[SessionEvent]:
        """Compatibility wrapper that appends the status-aware terminal event."""

        request = StepExecutionRequest(
            session_id=session_id,
            plan=plan,
            step=step,
            step_index=index - 1,
            memory_context=memory_context,
            agent_context=agent_context,
            step_history=tuple(step_history or ()),
        )
        outcome = await self.step_executor.execute(request)
        terminal = await self._add_step_terminal_event(request, outcome)
        return [*outcome.events, terminal]

    async def _add_step_terminal_event(
        self,
        request: StepExecutionRequest,
        outcome: StepExecutionOutcome,
    ) -> SessionEvent:
        status = outcome.observation.status
        if status in SUCCESS_STATUSES:
            event_type = SessionEventType.step_completed
        elif status in FINAL_FAILURE_STATUSES:
            event_type = SessionEventType.step_failed
        elif status is ToolInvocationStatus.approval_required:
            event_type = SessionEventType.step_blocked
        else:
            raise ValueError(f"execution status is not terminal: {status}")
        return await self.uow.session_events.add(
            session_id=request.session_id,
            event_type=event_type,
            payload={
                "plan_id": request.plan.get("id") or request.plan.get("plan_id"),
                "step_id": request.step.get("id"),
                "index": request.step_index + 1,
                "title": request.step.get("title", ""),
                "summary": outcome.observation.output,
                "status": status.value,
            },
        )

    # ===================== 第4步：用教学工具模拟步骤执行 =====================
    async def _call_tool_for_step(
        self,
        *,
        request: StepExecutionRequest,
        agent_context: str,
        execution_context: ToolExecutionContext,
    ) -> dict:
        result = await self.tool_selector.call_tool_for_step(
            plan=dict(request.plan),
            step=dict(request.step),
            index=request.step_index + 1,
            agent_context=agent_context,
            execution_context=execution_context,
        )
        return {
            "tool_name": result.tool_name,
            "arguments": result.arguments,
            "output": result.output,
            "invocation_id": result.invocation_id,
            "status": result.status.value,
            "risk_level": result.risk_level.value,
            "artifact_id": result.artifact_id,
            "duration_ms": result.duration_ms,
            "audit": result.audit or {},
        }

    def _append_step_history(
        self,
        step_history: list[str],
        index: int,
        step: dict,
        step_events: list[SessionEvent],
    ) -> None:
        step_history.append(
            self.step_executor.format_step_history(
                step_index=index - 1,
                step=step,
                events=tuple(step_events),
            )
        )

    # ===================== 第5步：把会话附件同步到 Sandbox =====================
    async def _sync_session_files_to_sandbox(self, session_id: UUID) -> None:
        """把当前会话上传的文本附件写入 Sandbox 工作目录。

        页面上传的附件默认存放在主 API 的文件存储中；而 file_read 工具
        读取的是 Sandbox 工作目录。如果不做同步，Agent 能在上下文里看到
        Page.tsx，却无法在 Sandbox 中读取 Page.tsx。
        """

        # 1. 读取当前会话绑定的附件。没有附件时直接返回，不影响普通任务。
        session_files = await self.uow.session_files.list_by_session(session_id)
        if not session_files:
            return

        # 2. 准备两个端点：本地文件存储负责读上传内容，Sandbox API 负责写入工作目录。
        storage = build_file_storage()
        sandbox_files = SandboxFileClient(
            base_url=settings.sandbox_api_base_url,
            timeout_seconds=settings.sandbox_api_timeout_seconds,
        )

        for session_file in session_files:
            file_object = session_file.file
            if not self._is_syncable_text_file(
                content_type=file_object.content_type,
                filename=file_object.original_name,
            ):
                continue

            # 3. 第 38 章先同步文本类文件；读取上限和文件预览保持一致，
            #    避免把大文件一次性写进 Sandbox。
            raw_content = storage.read_bytes(
                file_object.storage_path,
                max_size=settings.max_file_preview_size,
            )
            content = raw_content.decode("utf-8", errors="replace")
            safe_name = Path(file_object.original_name).name

            # 4. 同时写入两个位置：
            #    - Page.tsx：兼容模型直接选择 file_read(path="Page.tsx")。
            #    - attachments/Page.tsx：保留上传附件来源，方便用户排查。
            for path in {safe_name, f"attachments/{safe_name}"}:
                sandbox_files.write_file(
                    path=path,
                    content=content,
                    create_parent=True,
                )

    @staticmethod
    def _is_syncable_text_file(content_type: str, filename: str) -> bool:
        """判断上传文件是否适合直接同步成 Sandbox 文本文件。"""

        clean_content_type = content_type.split(";")[0].lower()
        if clean_content_type.startswith("text/") or clean_content_type in {
            "application/json",
            "application/xml",
            "application/yaml",
        }:
            return True
        return Path(filename).suffix.lower() in {
            ".css",
            ".csv",
            ".html",
            ".js",
            ".json",
            ".jsx",
            ".md",
            ".py",
            ".ts",
            ".tsx",
            ".txt",
            ".yaml",
            ".yml",
        }

    def _needs_browser_open(self, text: str) -> bool:
        """判断当前步骤是否需要打开网页。"""

        keywords = ["网页", "网站", "浏览器", "访问", "打开", "页面"]
        return any(keyword in text for keyword in keywords)

    def _needs_search(self, text: str) -> bool:
        """判断当前步骤是否需要搜索公开网页。

        第 30 章先用关键词规则选择 SearchTool。后续接入更完整的模型
        工具选择后，这里会逐步退化成兜底逻辑。
        """

        keywords = ["搜索", "检索", "查找", "查询", "资料", "新闻", "最新"]
        return any(keyword in text for keyword in keywords)

    def _needs_mcp(self, text: str) -> bool:
        """判断当前步骤是否需要调用 MCP 工具。"""

        keywords = ["MCP", "mcp", "外部工具", "外部系统"]
        return any(keyword in text for keyword in keywords)

    def _needs_a2a(self, text: str) -> bool:
        """判断当前步骤是否需要调用 A2A 远程 Agent。

        第 35 章先使用关键词规则，让本地验证可以稳定命中工具事件。
        后续模型工具选择增强后，这里会变成兜底逻辑。
        """

        keywords = [
            "A2A",
            "a2a",
            "远程 Agent",
            "远程agent",
            "远程智能体",
            "协作 Agent",
            "协作智能体",
            "远程研究",
            "研究 Agent",
            "调用另一个 Agent",
            "调用其他 Agent",
        ]
        return any(keyword in text for keyword in keywords)

    def _needs_multi_agent(self, text: str) -> bool:
        """判断当前步骤是否需要多 Agent 协作编排。"""

        if any(keyword in text for keyword in ["A2A", "a2a", "远程 Agent", "远程智能体"]):
            return False

        keywords = [
            "多 Agent",
            "多Agent",
            "多个 Agent",
            "多个智能体",
            "分工",
            "协作",
            "评审",
            "Reviewer",
            "Manager",
            "Worker",
            "汇总",
        ]
        return any(keyword in text for keyword in keywords)

    def _needs_browser_screenshot(self, text: str) -> bool:
        """判断当前步骤是否需要对页面截图。"""

        keywords = ["截图", "截屏", "页面截图", "观察页面"]
        return any(keyword in text for keyword in keywords)

    def _extract_url(self, text: str) -> str:
        """从计划步骤中提取 URL，没有 URL 时使用稳定示例站点。

        本章先用简单规则，后续会由 LLM 结构化输出工具参数。
        """

        for token in text.split():
            clean_token = token.strip("，。,.!?！？、()（）")
            parsed = urlparse(clean_token)
            if parsed.scheme in {"http", "https"} and parsed.netloc:
                return clean_token
        return "https://example.com"

    def _extract_search_query(self, text: str) -> str:
        """从计划文本中提取搜索关键词。

        现在的计划步骤还不是严格工具参数，所以先去掉常见动作词，
        保留用户真正想查的内容。
        """

        clean_text = " ".join(text.split())
        for keyword in ["搜索", "检索", "查找", "查询", "一下", "资料"]:
            clean_text = clean_text.replace(keyword, " ")
        return " ".join(clean_text.split())[:120] or text[:120]

    def _extract_a2a_message(self, text: str) -> str:
        """从计划文本中提取给远程 Agent 的任务消息。"""

        clean_text = " ".join(text.split())
        for keyword in ["A2A", "a2a", "远程 Agent", "远程agent", "远程智能体"]:
            clean_text = clean_text.replace(keyword, " ")
        return " ".join(clean_text.split())[:400] or text[:400]

    def _extract_multi_agent_task(self, text: str) -> str:
        """从计划文本中提取多 Agent 协作任务。"""

        clean_text = " ".join(text.split())
        for keyword in ["多 Agent", "多Agent", "多个 Agent", "多个智能体"]:
            clean_text = clean_text.replace(keyword, " ")
        return " ".join(clean_text.split())[:400] or text[:400]

    # ===================== 第5步：找到最新 plan_created 事件 =====================
    def _find_latest_plan_event(self, events: list[SessionEvent]) -> SessionEvent:
        """从会话事件中倒序查找最近一次计划。"""

        for event in reversed(events):
            if event.type is SessionEventType.plan_created:
                return event
        raise AppException(
            message="plan not found",
            code=404,
            status_code=404,
        )

    # ===================== 第6步：以流式方式执行当前会话的最新计划 =====================
    async def stream_latest_plan(self, session_id: UUID):
        """边执行计划边产出事件。

        第 39 章开始，前端发送任务后不再手动点击“生成”和“执行”。
        这个方法把 step_started、tool_called、step_completed、task_done
        逐个 yield 给 HTTP SSE 层，让中间对话流可以实时更新。
        """

        # 1. 确认会话存在，并读取当前会话全部事件。
        session = await self.uow.sessions.get(session_id)
        if session is None:
            raise AppException(
                message="session not found",
                code=404,
                status_code=404,
            )

        # 2. 找到最新的 plan_created 事件。PlannerService 会先写入它。
        events = await self.uow.session_events.list_by_session(session_id)
        plan_event = self._find_latest_plan_event(events)
        plan = plan_event.payload
        steps = plan.get("steps", [])
        if not steps:
            raise AppException(
                message="plan has no steps",
                code=400,
                status_code=400,
            )

        # 3. Planner 和 ReAct 复用同一套上下文构建方式。
        context_snapshot = await ContextEngineeringService(self.uow).build_snapshot(
            session_id,
            task=str(plan.get("goal", "")),
        )
        await self._sync_session_files_to_sandbox(session_id)
        memory_context = context_snapshot.memory_context
        agent_context = ContextEngineeringService.render_for_agent(context_snapshot)

        # 4. 标记会话进入 running 状态。状态事件由路由层负责推送。
        step_history: list[str] = []
        current_step: dict | None = None
        current_index = 0
        await self.uow.sessions.update_status(session_id, SessionStatus.running.value)
        await self.uow.commit()

        try:
            # 5. 每执行一个步骤，就立刻提交并 yield 对应事件。
            for index, step in enumerate(steps, start=1):
                current_step = step
                current_index = index
                step_events = await self._execute_step(
                    session_id=session_id,
                    plan=plan,
                    step=step,
                    index=index,
                    memory_context=memory_context,
                    agent_context=agent_context,
                    step_history=step_history,
                )
                self._append_step_history(step_history, index, step, step_events)
                await self.uow.sessions.touch(session_id)
                await self.uow.commit()
                for event in step_events:
                    yield event

            # 6. 所有步骤完成后流式生成最终回答（GPT 式打字机），
            #    思考与正文增量实时推送；失败时回退到规则版总结。
            completed_events: list[SessionEvent] = []
            for event in await self.uow.session_events.list_by_session(session_id):
                if (
                    event.type
                    in {
                        SessionEventType.tool_called,
                        SessionEventType.step_completed,
                    }
                    and event.payload.get("plan_id")
                    == (plan.get("id") or plan.get("plan_id"))
                ):
                    completed_events.append(event)

            answer_parts: list[str] = []
            reasoning_parts: list[str] = []
            evidence = self._build_final_answer_evidence(plan, completed_events)
            if evidence:
                try:
                    async for delta in LLMService().chat_stream(
                        self._build_final_answer_messages(plan, evidence),
                        temperature=0.2,
                        max_tokens=2500,
                    ):
                        if delta.kind == "reasoning":
                            reasoning_parts.append(delta.text)
                            yield ("thinking_delta", delta.text)
                        else:
                            answer_parts.append(delta.text)
                            yield ("answer_delta", delta.text)
                except AppException:
                    answer_parts = []
            final_answer = "".join(answer_parts).strip() or (
                self._build_rule_based_final_answer(plan, completed_events)
            )
            reasoning = "".join(reasoning_parts).strip()

            answer_message = await self.uow.session_messages.add_assistant_message(
                session_id=session_id,
                content=final_answer,
            )
            answer_event = await self.uow.session_events.add(
                session_id=session_id,
                event_type=SessionEventType.message_created,
                payload={
                    "message_id": str(answer_message.id),
                    "role": answer_message.role.value,
                    "content": answer_message.content,
                },
            )
            done_event = await self.uow.session_events.add(
                session_id=session_id,
                event_type=SessionEventType.task_done,
                payload={
                    "plan_id": plan.get("id") or plan.get("plan_id"),
                    "final_answer": final_answer,
                    # 与直答路径同构：思考过程关联回答消息，刷新后可回看。
                    "reasoning": reasoning,
                    "message_id": str(answer_message.id),
                    "message": "计划步骤已全部执行完成。",
                    "memory_ids": [str(item.id) for item in memory_context.items],
                    "memory_count": len(memory_context.items),
                },
            )
            await self.uow.sessions.update_status(session_id, SessionStatus.idle.value)
            await self.uow.sessions.touch(session_id)
            await self.uow.commit()
            yield answer_event
            yield done_event
        except Exception as error:
            # 7. 任意步骤失败时，写入结构化 task_error。
            #    message 保留给旧前端；user_message/suggestion/source 给新前端展示。
            error_payload = build_task_error_payload(
                error,
                session_id=session_id,
                plan_id=plan.get("id") or plan.get("plan_id"),
                step=current_step,
                step_index=current_index,
            )
            error_event = await self.uow.session_events.add(
                session_id=session_id,
                event_type=SessionEventType.task_error,
                payload=error_payload,
            )
            await self.uow.sessions.update_status(session_id, SessionStatus.failed.value)
            await self.uow.commit()
            yield error_event

    async def _persist_final_answer_message(
        self,
        *,
        session_id: UUID,
        final_answer: str,
    ) -> SessionEvent:
        """把最终回答落库成 assistant 消息并返回 message_created 事件。

        消息列表是客户端刷新后的事实源。回答只存在 task_done 事件里时，
        刷新后消息列表只剩用户消息，对话看起来像“没有人回复”。
        """

        message = await self.uow.session_messages.add_assistant_message(
            session_id=session_id,
            content=final_answer,
        )
        return await self.uow.session_events.add(
            session_id=session_id,
            event_type=SessionEventType.message_created,
            payload={
                "message_id": str(message.id),
                "role": message.role.value,
                "content": message.content,
            },
        )

    # ===================== 第7步：根据工具输出生成最终总结 =====================
    async def _build_final_answer(
        self,
        plan: dict,
        events: list[SessionEvent],
    ) -> str:
        """把本轮执行的工具观察结果整理成面向用户的最终回答。

        这里不输出隐藏推理，只总结可观察证据：
        - 搜索工具：查询词、结果数量和候选标题。
        - 浏览器工具：页面标题、当前地址或截图大小。
        - Shell 工具：命令和退出码。
        - 文件工具：文件路径、写入/读取结果。
        """

        fallback_answer = self._build_rule_based_final_answer(plan, events)
        evidence = self._build_final_answer_evidence(plan, events)
        if not evidence:
            return fallback_answer

        try:
            result = await LLMService().chat(
                messages=self._build_final_answer_messages(plan, evidence),
                temperature=0.2,
                # 思考型模型的 reasoning 计入输出额度，给足空间避免总结被截断。
                max_tokens=2500,
            )
        except AppException:
            return fallback_answer

        clean_content = result.content.strip()
        return clean_content or fallback_answer

    @staticmethod
    def _build_final_answer_messages(plan: dict, evidence: str) -> list[LLMMessage]:
        """最终回答总结器的提示词，供流式与非流式两条路径共用。"""

        return [
            LLMMessage(
                role="system",
                content=(
                    "你是 AtlasAgent 的任务总结器。"
                    "请根据可观察的工具输出写最终回复正文，不要编造未执行的动作，"
                    "不要输出隐藏推理，不要提到 JSON 或内部事件。"
                    "如果是代码文件解析任务，请总结组件结构、状态逻辑、风险点和优化建议。"
                    "如果是搜索任务，请总结搜索发现和可点击来源价值。"
                    "输出中文 Markdown，并固定包含：## 总结、## 证据与引用、## 产物、## 下一步建议。"
                    "没有产物时写“本次任务没有生成新的文件产物”。"
                ),
            ),
            LLMMessage(
                role="user",
                content=(
                    f"任务目标：{plan.get('goal') or plan.get('title') or '未命名任务'}\n\n"
                    f"工具观察材料：\n{evidence}"
                ),
            ),
        ]

    def _build_rule_based_final_answer(
        self,
        plan: dict,
        events: list[SessionEvent],
    ) -> str:
        """在 LLM 不可用时，用确定性规则生成最终总结。"""

        # 1. 先建立 step_id -> step 的映射。工具事件只知道 step_id，
        #    最终总结需要把它还原成用户能看懂的步骤标题。
        steps = plan.get("steps", [])
        step_map = {
            str(step.get("id")): step
            for step in steps
            if isinstance(step, dict) and step.get("id")
        }

        # 2. 只关心 tool_called 事件，因为它保存了工具名、调用参数和输出结果。
        tool_events = [
            event for event in events if event.type is SessionEventType.tool_called
        ]
        summary_lines: list[str] = []
        evidence_lines: list[str] = []
        artifact_lines: list[str] = []
        for index, event in enumerate(tool_events, start=1):
            step_id = str(event.payload.get("step_id") or "")
            step = step_map.get(step_id, {})
            title = str(
                step.get("title")
                or event.payload.get("tool_name")
                or f"步骤 {index}"
            )
            tool_name = str(event.payload.get("tool_name") or "")
            output = str(event.payload.get("output") or "")
            summary = self._summarize_tool_output(tool_name, output)
            summary_lines.append(f"{index}. **{title}**：{summary}")
            evidence_lines.extend(
                self._build_final_answer_reference_lines(
                    title=title,
                    tool_name=tool_name,
                    output=output,
                )
            )
            artifact_lines.extend(
                self._build_final_answer_artifact_lines(
                    title=title,
                    tool_name=tool_name,
                    output=output,
                )
            )

        # 3. 如果没有工具事件，给出保守总结，避免前端展示空白结果。
        if not summary_lines:
            return "任务已完成，但本轮没有产生可展示的工具观察结果。"

        goal = str(plan.get("goal") or plan.get("title") or "本次任务")
        sections = [
            "## 总结",
            f"任务已完成。我围绕“{goal}”完成了计划步骤，并整理了可追溯的工具观察结果。",
            "",
            "## 执行结果",
            *summary_lines,
        ]
        if evidence_lines:
            sections.extend(["", "## 证据与引用", *evidence_lines])
        if artifact_lines:
            sections.extend(["", "## 产物", *artifact_lines])
        sections.extend(
            [
                "",
                "## 下一步建议",
                "- 可以点击每个步骤里的工具节点，在右侧查看调用参数、搜索来源、终端输出、截图或协作详情。",
                "- 如果需要继续交付，可以基于这些证据生成报告、代码修改建议或可下载文件。",
            ]
        )
        return "\n".join(sections)

    def _build_final_answer_reference_lines(
        self,
        *,
        title: str,
        tool_name: str,
        output: str,
    ) -> list[str]:
        """从工具输出中提取最终回答可展示的证据引用。

        这里仍然只使用可观察输出，不输出隐藏推理。搜索结果引用标题和 URL；
        文件工具引用文件名和行号；浏览器工具引用页面标题和地址。
        """

        parsed = self._parse_json_object(output)
        if parsed and parsed.get("kind") == "search_results":
            items = parsed.get("items") if isinstance(parsed.get("items"), list) else []
            lines: list[str] = []
            for item in items[:5]:
                if not isinstance(item, dict):
                    continue
                item_title = str(item.get("title") or "").strip()
                url = str(item.get("url") or "").strip()
                snippet = str(item.get("snippet") or "").strip()
                if item_title and url:
                    suffix = f"：{self._trim_text(snippet, 90)}" if snippet else ""
                    lines.append(f"- **{item_title}**（{url}）{suffix}")
            return lines

        if tool_name.startswith("file_"):
            useful_lines = [
                line.strip()
                for line in output.splitlines()
                if line.strip()
                and (
                    line.startswith(("文件：", "路径：", "第 "))
                    or "行" in line
                    or Path(line.strip()).suffix
                )
            ][:4]
            if useful_lines:
                return [f"- **{title}**：{self._trim_text(line, 160)}" for line in useful_lines]

        if tool_name.startswith("browser_"):
            page_title = self._match_line_value(output, "页面标题")
            current_url = (
                self._match_line_value(output, "页面已打开")
                or self._match_line_value(output, "当前地址")
            )
            if page_title or current_url:
                return [
                    f"- **{title}**：{page_title or '浏览器页面'}"
                    f"{f'（{current_url}）' if current_url else ''}"
                ]

        return []

    def _build_final_answer_artifact_lines(
        self,
        *,
        title: str,
        tool_name: str,
        output: str,
    ) -> list[str]:
        """从工具输出中提取可交付产物路径或截图信息。"""

        parsed = self._parse_json_object(output)
        if parsed and parsed.get("kind") == "browser_screenshot":
            size = int(parsed.get("size") or 0)
            size_text = f"{round(size / 1024)} KB" if size > 0 else "未知大小"
            return [f"- **{title}**：浏览器截图已生成，大小约 {size_text}。"]

        artifact_labels = ["输出文件", "文件路径", "保存路径", "下载地址"]
        lines: list[str] = []
        for label in artifact_labels:
            value = self._match_line_value(output, label)
            if value:
                lines.append(f"- **{title}**：{label} `{value}`")
        if lines:
            return lines

        if tool_name.startswith("file_write"):
            first_line = self._first_useful_line(output)
            return [f"- **{title}**：{self._trim_text(first_line, 160)}"]

        return []

    def _build_final_answer_evidence(
        self,
        plan: dict,
        events: list[SessionEvent],
    ) -> str:
        """把工具事件整理成 LLM 可消费的观察材料。"""

        steps = plan.get("steps", [])
        step_map = {
            str(step.get("id")): step
            for step in steps
            if isinstance(step, dict) and step.get("id")
        }
        blocks: list[str] = []
        for index, event in enumerate(events, start=1):
            if event.type is not SessionEventType.tool_called:
                continue
            step_id = str(event.payload.get("step_id") or "")
            step = step_map.get(step_id, {})
            title = str(
                step.get("title")
                or event.payload.get("tool_name")
                or f"步骤 {index}"
            )
            tool_name = str(event.payload.get("tool_name") or "")
            arguments = event.payload.get("arguments") or {}
            output = str(event.payload.get("output") or "")
            summary = self._summarize_tool_output(tool_name, output)
            references = self._build_final_answer_reference_lines(
                title=title,
                tool_name=tool_name,
                output=output,
            )
            artifacts = self._build_final_answer_artifact_lines(
                title=title,
                tool_name=tool_name,
                output=output,
            )
            block_lines = [
                f"## {title}",
                f"- 工具：{tool_name}",
                f"- 参数：{json.dumps(arguments, ensure_ascii=False)}",
                f"- 摘要：{summary}",
            ]
            if references:
                block_lines.extend(["- 引用：", *references])
            if artifacts:
                block_lines.extend(["- 产物：", *artifacts])
            block_lines.extend(["- 原始观察摘录：", self._trim_text(output, 900)])
            blocks.append(
                "\n".join(block_lines)
            )
        return "\n\n".join(blocks)

    def _summarize_tool_output(self, tool_name: str, output: str) -> str:
        """把不同工具的原始输出压缩成一句可读观察。"""

        # 1. JSON 类工具先按 kind 识别，这覆盖搜索、截图、多 Agent 等结构化输出。
        parsed = self._parse_json_object(output)
        if parsed:
            kind = str(parsed.get("kind") or "")
            if kind == "search_results":
                items = parsed.get("items") if isinstance(parsed.get("items"), list) else []
                titles = [
                    str(item.get("title"))
                    for item in items[:3]
                    if isinstance(item, dict) and item.get("title")
                ]
                suffix = f" 代表结果包括：{'、'.join(titles)}。" if titles else ""
                return (
                    f"已搜索“{parsed.get('query') or '相关关键词'}”，"
                    f"找到 {len(items)} 条候选结果。{suffix}"
                )
            if kind == "search_error":
                return (
                    f"搜索“{parsed.get('query') or '相关关键词'}”时页面搜索暂不可用，"
                    f"原因：{parsed.get('message') or '网络请求失败'}。"
                )
            if kind == "browser_screenshot":
                size = int(parsed.get("size") or 0)
                size_text = f"{round(size / 1024)} KB" if size > 0 else "未知大小"
                return f"已完成浏览器截图，图片大小约 {size_text}。"
            if kind == "multi_agent_result" and parsed.get("final_answer"):
                return self._trim_text(str(parsed.get("final_answer")), 180)
            if kind:
                return f"工具返回了 {kind} 类型的结构化结果。"

        # 2. Shell 输出通常是多行文本，优先提取命令和退出码。
        if tool_name.startswith("shell_"):
            command = self._match_line_value(output, "命令")
            return_code = self._match_line_value(output, "退出码")
            return (
                f"已执行命令{f'“{command}”' if command else ''}，"
                f"退出码 {return_code or '未知'}。"
            )

        # 3. 浏览器打开页面时，工具输出里会带页面标题或当前地址。
        if tool_name.startswith("browser_"):
            page_title = self._match_line_value(output, "页面标题")
            current_url = (
                self._match_line_value(output, "页面已打开")
                or self._match_line_value(output, "当前地址")
            )
            if page_title:
                return f"浏览器已打开页面，页面标题为：{page_title}。"
            if current_url:
                return f"浏览器已访问：{current_url}。"
            return "浏览器工具已返回页面观察结果。"

        # 4. 文件工具直接取第一行有意义的文本。
        if tool_name.startswith("file_"):
            return self._trim_text(self._first_useful_line(output), 180)

        return self._trim_text(self._first_useful_line(output), 180)

    @staticmethod
    def _parse_json_object(value: str) -> dict | None:
        """安全解析工具输出中的 JSON 对象。"""

        try:
            loaded = json.loads(value)
        except (TypeError, ValueError):
            return None
        return loaded if isinstance(loaded, dict) else None

    @staticmethod
    def _match_line_value(text: str, label: str) -> str:
        """从“标签：值”格式的工具输出中提取值。"""

        prefix = f"{label}："
        for line in text.splitlines():
            if line.startswith(prefix):
                return line.removeprefix(prefix).strip()
        return ""

    @staticmethod
    def _first_useful_line(text: str) -> str:
        """取第一行非空文本作为兜底摘要。"""

        for line in text.splitlines():
            clean_line = line.strip()
            if clean_line:
                return clean_line
        return "工具已返回结果。"

    @staticmethod
    def _trim_text(value: str, max_length: int) -> str:
        """限制最终摘要长度，避免一条工具输出撑开对话气泡。"""

        clean_value = " ".join(value.split())
        if len(clean_value) <= max_length:
            return clean_value
        return f"{clean_value[:max_length]}..."
