from app.core.exceptions import AppException
from app.domain.agent_core.memory import ConversationMemory, MemoryMessage
from app.domain.agent_core.tools import ToolCallResult, ToolDefinition, ToolRegistry


class AgentCoreService:
    """第 17 章的最小 Agent 核心服务。

    本章先把 Memory、工具 schema、工具调用结果串起来。
    它还不是完整 Agent，但已经具备后续 PlannerAgent 和 ReActAgent 需要的基础积木。
    """

    def __init__(self, registry: ToolRegistry) -> None:
        # ===================== 第1步：准备工具注册表 =====================
        # registry 由组合层显式构建并注入，以共享同一个模型实例。
        self.registry = registry

    # ===================== 第2步：返回工具 schema 给前端或模型查看 =====================
    def list_tools(self) -> list[ToolDefinition]:
        """列出当前 Agent 可以调用的工具。"""

        return self.registry.list_tools()

    # ===================== 第3步：运行一次最小 Agent 演示 =====================
    def run_demo(
        self,
        task: str,
        tool_name: str | None = None,
    ) -> tuple[list[MemoryMessage], ToolDefinition, ToolCallResult, str]:
        """把用户任务、工具调用和工具结果写入 Memory。"""

        clean_task = task.strip()
        if not clean_task:
            raise AppException(
                message="task is required",
                code=400,
                status_code=400,
            )

        memory = ConversationMemory()
        memory.add_user_message(clean_task)

        selected_tool_name = tool_name or self._choose_tool(clean_task)
        selected_tool = self.registry.get(selected_tool_name)
        arguments = self._build_arguments(selected_tool.definition, clean_task)

        memory.add_assistant_message(
            f"我会调用 {selected_tool.definition.name} 工具处理这个任务。"
        )
        tool_result = selected_tool.call(arguments)
        memory.add_tool_message(
            tool_name=tool_result.tool_name,
            content=tool_result.output,
        )

        next_step = (
            "下一步可以把这些 Memory 消息交给 LLM，让模型基于工具结果继续生成回答。"
        )
        memory.add_assistant_message(next_step)

        return (
            memory.list_messages(),
            selected_tool.definition,
            tool_result,
            next_step,
        )

    # ===================== 第4步：根据任务内容选择默认工具 =====================
    def _choose_tool(self, task: str) -> str:
        """用简单规则模拟 Agent 的工具选择。"""

        if "计划" in task or "步骤" in task or "拆解" in task:
            return "draft_plan"
        if "关键词" in task or "重点" in task:
            return "extract_keywords"
        return "summarize_text"

    # ===================== 第5步：把用户任务转换成工具参数 =====================
    def _build_arguments(
        self,
        definition: ToolDefinition,
        task: str,
    ) -> dict[str, str]:
        """根据工具 schema 生成本次调用参数。"""

        arguments: dict[str, str] = {}
        for parameter in definition.parameters:
            if parameter.name == "task":
                arguments[parameter.name] = task
            else:
                arguments[parameter.name] = task
        return arguments

