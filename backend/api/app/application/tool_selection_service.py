import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from app.application.llm_service import LLMService
from app.application.tool_runtime import ToolExecutionContext, ToolRuntime
from app.application.unit_of_work import UnitOfWork
from app.core.exceptions import AppException
from app.domain.agent_core.tools import (
    AgentTool,
    ToolCallResult,
    ToolDefinition,
    ToolRegistry,
)
from app.domain.llm.entities import LLMMessage


@dataclass(slots=True)
class ToolSelectionDecision:
    """模型或 fallback 产出的工具选择结果。"""

    tool_name: str
    arguments: dict[str, Any]
    source: str
    observable_summary: str


class ModelToolSelectionService:
    """结合模型输出和确定性 fallback 选择工具。

    第 43 章开始把工具选择从 ReActAgentService 中抽出来：
    1. 优先让模型基于工具 schema、任务、上下文输出结构化 tool call。
    2. 模型不可用或输出不合法时，回退到规则选择，保证课程本地可验证。
    3. 调用前修复缺失的常见参数，避免简单参数缺失导致整步失败。
    """

    def __init__(
        self,
        *,
        registry: ToolRegistry,
        llm_service: LLMService | None = None,
        uow: UnitOfWork | None = None,
    ) -> None:
        # ===================== 第1步：保存工具注册表和模型服务 =====================
        self.registry = registry
        self.llm_service = llm_service or LLMService()
        self.runtime = ToolRuntime(registry, uow=uow)

    # ===================== 第2步：为计划步骤选择并调用工具 =====================
    async def call_tool_for_step(
        self,
        *,
        plan: dict,
        step: dict,
        index: int,
        agent_context: str,
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolCallResult:
        """选择一个工具、修复参数、执行工具并返回统一结果。"""

        # 1. 收集当前任务文本。工具选择必须优先看当前任务，避免长期记忆误触发工具。
        goal = str(plan.get("goal", ""))
        title = str(step.get("title", ""))
        description = str(step.get("description", ""))
        expected_output = str(step.get("expected_output", ""))
        step_text = f"{title} {description} {expected_output}".strip()
        task_text = f"{goal} {step_text}".strip()

        # 2. 先尝试模型工具选择；失败后使用确定性规则兜底。
        decision = await self._select_with_model(
            task_text=task_text,
            agent_context=agent_context,
        )
        if decision is None:
            decision = self._select_with_rules(
                task_text=task_text,
                step_text=step_text,
                index=index,
                agent_context=agent_context,
            )

        # 3. 校验工具存在，并在调用前修复缺失的常见参数。
        tool = self.registry.get(decision.tool_name)
        arguments = self._repair_arguments(
            tool=tool,
            arguments=decision.arguments,
            task_text=task_text,
            agent_context=agent_context,
        )

        # 4. 统一 Runtime 执行权限、风险、超时、幂等和审计。
        runtime_context = execution_context or ToolExecutionContext(
            allowed_permissions=set(tool.definition.required_permissions),
        )
        return await self.runtime.execute(
            tool.definition.name,
            arguments,
            runtime_context,
        )

    # ===================== 第3步：让模型输出结构化 tool call =====================
    async def _select_with_model(
        self,
        *,
        task_text: str,
        agent_context: str,
    ) -> ToolSelectionDecision | None:
        """调用 LLM 选择工具；任何异常都交给 fallback。"""

        try:
            result = await self.llm_service.chat(
                messages=[
                    LLMMessage(
                        role="system",
                        content=(
                            "你是 Agent 的工具选择器。请只返回 JSON，不要返回 Markdown。"
                            "JSON 格式："
                            '{"tool_name":"工具名","arguments":{},"observable_summary":"给用户看的简短说明"}'
                            "\n\n可用工具：\n"
                            f"{self._render_tool_schemas()}\n\n"
                            "工具使用准则：\n"
                            "1. 分析、推演、解释、撰写这类纯思考步骤（不需要外部操作）必须用 "
                            "write_content，并把该步骤要产出的具体内容要求完整写进 task 参数；"
                            "严禁使用 draft_plan / summarize_text / extract_keywords 这类模板工具，"
                            "它们只会输出无信息量的固定文本。\n"
                            "2. 执行多行代码时，禁止塞进 shell 单行命令（python -c 多行必然语法错误）；"
                            "正确做法：先用 file_write 把完整代码写入脚本文件（如 main.py），"
                            "下一步再用 shell_run 执行 `python3 main.py`。\n"
                            "3. 上下文里已有此前步骤的执行结果；根据当前步骤的目的选择工具，"
                            "不要重复做已完成的事（例如页面已打开就不要再 browser_open）。\n"
                            "4. 若历史里有 ⚠️ 失败 的步骤，本步优先补救：缺文件就先写文件，"
                            "写完的脚本还没成功执行就再次执行，然后才继续原步骤目标。"
                            "严禁执行尚未创建的脚本文件。\n"
                            "5. 需要根据网页内容回答问题、提取网页信息或总结页面时，"
                            "必须用 browser_read（可直接传 url，一步完成打开+读取正文），"
                            "然后基于返回的正文作答；同一网页的正文已经出现在步骤历史里时，"
                            "严禁再次 browser_read，后续分析/总结步骤直接用 write_content 引用已读内容。"
                            "browser_open 只用于确认页面可达或为截图做准备；"
                            "截图必须用 browser_screenshot；查会话状态用 browser_status。\n"
                            "6. 文件读写用 file_read / file_write，路径相对于沙箱工作目录。\n\n"
                            "压缩上下文：\n"
                            f"{agent_context or '暂无额外上下文'}\n\n"
                            "注意：不要输出隐藏推理，只输出可观察的工具选择结果。"
                        ),
                    ),
                    LLMMessage(role="user", content=task_text),
                ],
                temperature=0.1,
                # 思考型模型的 reasoning 计入输出额度，给足空间避免 JSON 被截断。
                max_tokens=2400,
            )
            payload = json.loads(self._strip_code_fence(result.content))
        except (AppException, json.JSONDecodeError, TypeError, ValueError):
            return None

        if not isinstance(payload, dict):
            return None
        tool_name = str(payload.get("tool_name") or "").strip()
        arguments = payload.get("arguments")
        if not tool_name or not isinstance(arguments, dict):
            return None

        try:
            self.registry.get(tool_name)
        except AppException:
            return None

        return ToolSelectionDecision(
            tool_name=tool_name,
            arguments=arguments,
            source="model",
            observable_summary=str(payload.get("observable_summary") or ""),
        )

    # ===================== 第4步：模型不可用时使用确定性规则兜底 =====================
    def _select_with_rules(
        self,
        *,
        task_text: str,
        step_text: str,
        index: int,
        agent_context: str,
    ) -> ToolSelectionDecision:
        """保留本地稳定可验证的规则选择逻辑。"""

        text_with_context = (
            f"{task_text}\n\n需要遵守的上下文：\n{agent_context}"
            if agent_context
            else task_text
        )

        if self._needs_multi_agent(task_text):
            return ToolSelectionDecision(
                tool_name="multi_agent_collaborate",
                arguments={"task": self._trim(text_with_context, 500)},
                source="fallback",
                observable_summary="使用多 Agent 协作完成任务。",
            )
        if self._needs_a2a(task_text):
            return ToolSelectionDecision(
                tool_name="a2a_call",
                arguments={
                    "agent_key": "demo_researcher",
                    "message": self._trim(text_with_context, 500),
                },
                source="fallback",
                observable_summary="调用远程 Agent 协作。",
            )
        if self._needs_mcp(task_text):
            return ToolSelectionDecision(
                tool_name="mcp_call",
                arguments={
                    "server_name": "demo",
                    "tool_name": "mcp_echo",
                    "arguments_json": '{"text":"来自 MCP 工具的演示响应"}',
                },
                source="fallback",
                observable_summary="调用 MCP 工具。",
            )
        if self._needs_file_read(task_text):
            return ToolSelectionDecision(
                tool_name="file_read",
                arguments={"path": self._extract_file_path(agent_context)},
                source="fallback",
                observable_summary="读取上传文件内容。",
            )
        if self._needs_search(task_text):
            return ToolSelectionDecision(
                tool_name="search_web",
                arguments={"query": self._extract_search_query(task_text), "count": 5},
                source="fallback",
                observable_summary="搜索公开网页资料。",
            )
        if self._needs_browser_screenshot(task_text):
            if index == 1 or (
                self._needs_browser_open(step_text)
                and not self._needs_browser_screenshot(step_text)
            ):
                return ToolSelectionDecision(
                    tool_name="browser_open",
                    arguments={"url": self._extract_url(task_text)},
                    source="fallback",
                    observable_summary="打开网页。",
                )
            return ToolSelectionDecision(
                tool_name="browser_screenshot",
                arguments={"full_page": True},
                source="fallback",
                observable_summary="截取浏览器页面。",
            )
        if self._needs_browser_open(task_text):
            return ToolSelectionDecision(
                tool_name="browser_open",
                arguments={"url": self._extract_url(task_text)},
                source="fallback",
                observable_summary="打开网页。",
            )
        if "关键" in task_text or "重点" in task_text:
            return ToolSelectionDecision(
                tool_name="extract_keywords",
                arguments={"text": text_with_context},
                source="fallback",
                observable_summary="提取关键词。",
            )
        if "拆" in task_text or "步骤" in task_text or "计划" in task_text:
            return ToolSelectionDecision(
                tool_name="draft_plan",
                arguments={"task": text_with_context},
                source="fallback",
                observable_summary="生成计划草稿。",
            )
        return ToolSelectionDecision(
            tool_name="summarize_text",
            arguments={"text": text_with_context},
            source="fallback",
            observable_summary="总结当前步骤。",
        )

    # ===================== 第5步：修复模型遗漏的常见必填参数 =====================
    def _repair_arguments(
        self,
        *,
        tool: AgentTool,
        arguments: dict[str, Any],
        task_text: str,
        agent_context: str,
    ) -> dict[str, Any]:
        """在 AgentTool 校验前清洗多余参数并补齐可推断参数。

        模型偶尔会把协议字段（observable_summary / tool_name）或臆造的
        键混进 arguments；严格校验会因此拒绝整次调用。这里先按工具
        schema 白名单过滤，小偏差不应毁掉整个任务。
        """

        allowed_names = {parameter.name for parameter in tool.definition.parameters}
        repaired = {
            key: value for key, value in arguments.items() if key in allowed_names
        }
        text_with_context = (
            f"{task_text}\n\n需要遵守的上下文：\n{agent_context}"
            if agent_context
            else task_text
        )
        for parameter in tool.definition.parameters:
            value = repaired.get(parameter.name)
            if not parameter.required or value not in (None, ""):
                continue

            if parameter.name in {"query", "q"}:
                repaired[parameter.name] = self._extract_search_query(task_text)
            elif parameter.name in {"text", "task", "message"}:
                repaired[parameter.name] = text_with_context
            elif parameter.name == "url":
                repaired[parameter.name] = self._extract_url(task_text)
            elif parameter.name == "server_name":
                repaired[parameter.name] = "demo"
            elif parameter.name == "tool_name":
                repaired[parameter.name] = "mcp_echo"
            elif parameter.name == "agent_key":
                repaired[parameter.name] = "demo_researcher"
            elif parameter.name == "path" and tool.definition.name.startswith("file_"):
                repaired[parameter.name] = self._extract_file_path(agent_context)
        if tool.definition.name == "search_web":
            repaired["query"] = self._normalize_search_query(
                query=str(repaired.get("query") or ""),
                task_text=task_text,
            )
        return repaired

    # ===================== 第6步：把工具 schema 渲染进模型提示词 =====================
    def _render_tool_schemas(self) -> str:
        lines: list[str] = []
        for tool in self.registry.list_tools():
            lines.append(self._render_tool_schema(tool))
        return "\n".join(lines)

    @staticmethod
    def _render_tool_schema(tool: ToolDefinition) -> str:
        parameters = [
            {
                "name": parameter.name,
                "type": parameter.type,
                "required": parameter.required,
                "description": parameter.description,
            }
            for parameter in tool.parameters
        ]
        return json.dumps(
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": parameters,
                "version": tool.version,
                "risk_level": tool.risk_level.value,
                "required_permissions": list(tool.required_permissions),
                "idempotent": tool.idempotent,
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _strip_code_fence(content: str) -> str:
        clean = content.strip()
        if clean.startswith("```"):
            clean = clean.strip("`")
            if clean.startswith("json"):
                clean = clean[4:]
        return clean.strip()

    @staticmethod
    def _trim(value: str, limit: int) -> str:
        clean = " ".join(value.split())
        return clean[:limit]

    @staticmethod
    def _needs_browser_open(text: str) -> bool:
        return any(keyword in text for keyword in ["网页", "网站", "浏览器", "访问", "打开", "页面"])

    @staticmethod
    def _needs_search(text: str) -> bool:
        return any(keyword in text for keyword in ["搜索", "检索", "查找", "查询", "资料", "新闻", "最新"])

    @staticmethod
    def _needs_mcp(text: str) -> bool:
        return any(keyword in text for keyword in ["MCP", "mcp", "外部工具", "外部系统"])

    @staticmethod
    def _needs_a2a(text: str) -> bool:
        return any(keyword in text for keyword in ["A2A", "a2a", "远程 Agent", "远程agent", "远程智能体"])

    @staticmethod
    def _needs_multi_agent(text: str) -> bool:
        if any(keyword in text for keyword in ["A2A", "a2a", "远程 Agent", "远程智能体"]):
            return False
        return any(keyword in text for keyword in ["多 Agent", "多Agent", "分工", "协作", "评审", "汇总"])

    @staticmethod
    def _needs_file_read(text: str) -> bool:
        return any(
            keyword in text
            for keyword in [
                "读取文件",
                "解析文件",
                "分析文件",
                "查看文件",
                "文件内容",
                ".tsx",
                ".ts",
                ".py",
                ".md",
                ".txt",
            ]
        )

    @staticmethod
    def _needs_browser_screenshot(text: str) -> bool:
        return any(keyword in text for keyword in ["截图", "截屏", "页面截图", "观察页面"])

    @staticmethod
    def _extract_url(text: str) -> str:
        for token in text.split():
            clean_token = token.strip("，。,.!?！？、()（）")
            parsed = urlparse(clean_token)
            if parsed.scheme in {"http", "https"} and parsed.netloc:
                return clean_token
        return "https://example.com"

    @staticmethod
    def _extract_search_query(text: str) -> str:
        clean_text = " ".join(text.split())
        for keyword in ["搜索", "检索", "查找", "查询", "一下", "资料"]:
            clean_text = clean_text.replace(keyword, " ")
        return " ".join(clean_text.split())[:120] or text[:120]

    @classmethod
    def _normalize_search_query(cls, *, query: str, task_text: str) -> str:
        """把模型生成的搜索词修正成更适合中文网络环境的查询。

        Bing 页面搜索在中文地区容易把 `recent artificial intelligence news`
        理解成查 recent 这个英文单词。这里把 AI 新闻类任务改成
        “中文主题 + 英文关键词 + 年份”的形式，提高命中新闻页的概率。
        """

        clean_query = " ".join(query.split())
        clean_task = " ".join(task_text.split())
        lower_query = clean_query.lower()
        lower_task = clean_task.lower()

        if cls._looks_like_ai_news_task(lower_query, lower_task) and (
            not clean_query
            or "recent" in lower_query
            or "artificial intelligence" in lower_query
        ):
            if "agent" in lower_query or "agent" in lower_task:
                return "AI Agent 最新新闻 2025"
            return "人工智能 AI 新闻 最新 2025"

        if not clean_query:
            return cls._extract_search_query(clean_task)

        return clean_query[:120]

    @staticmethod
    def _looks_like_ai_news_task(query: str, task: str) -> bool:
        """判断当前搜索是否属于 AI 新闻类任务。"""

        ai_terms = ["ai", "artificial intelligence", "人工智能", "智能体"]
        news_terms = ["news", "新闻", "动态", "latest", "recent", "最新"]
        combined = f"{query} {task}"
        return any(term in combined for term in ai_terms) and any(
            term in combined for term in news_terms
        )

    @staticmethod
    def _extract_file_path(agent_context: str) -> str:
        """从上下文里的文件引用提取一个可读文件名。

        ContextEngineeringService.render_for_agent() 会输出：
        - Page.tsx (text/plain, 可在需要时读取文本预览或下载内容。)
        这里取出 Page.tsx，配合 ReActAgentService 的附件同步逻辑，
        file_read 就能在 Sandbox 根目录中读到同名文件。
        """

        for line in agent_context.splitlines():
            clean_line = line.strip()
            if not clean_line.startswith("- "):
                continue
            candidate = clean_line.removeprefix("- ").split(" (", 1)[0].strip()
            if candidate and "." in candidate and "/" not in candidate:
                return candidate
        return "."
