from app.domain.agent_core.tools import ToolRegistry, agent_tool
from app.infrastructure.agent_tools.a2a import register_a2a_tools
from app.infrastructure.agent_tools.mcp import register_mcp_tools
from app.infrastructure.agent_tools.multi_agent import register_multi_agent_tools
from app.infrastructure.agent_tools.search import register_search_tools
from app.infrastructure.agent_tools.sandbox_browser import register_sandbox_browser_tools
from app.infrastructure.agent_tools.sandbox_file import register_sandbox_file_tools
from app.infrastructure.agent_tools.sandbox_shell import register_sandbox_shell_tools


# ===================== 第1步：定义一个文本摘要工具 =====================
@agent_tool(
    name="summarize_text",
    description="把一段较长文本压缩成更短的摘要。",
    parameter_descriptions={
        "text": "需要压缩和概括的原始文本。",
    },
)
def summarize_text(text: str) -> str:
    """返回一个简单摘要。

    本章先使用确定性字符串处理，后续可以替换成真实 LLM 摘要。
    """

    clean_text = " ".join(text.split())
    if len(clean_text) <= 80:
        return f"摘要：{clean_text}"
    return f"摘要：{clean_text[:80]}..."


# ===================== 第2步：定义一个关键词提取工具 =====================
@agent_tool(
    name="extract_keywords",
    description="从任务文本中提取几个关键词，帮助 Agent 判断任务重点。",
    parameter_descriptions={
        "text": "需要提取关键词的文本。",
    },
)
def extract_keywords(text: str) -> str:
    """按长度和去重规则提取关键词。"""

    words = [
        word.strip("，。,.!?！？、")
        for word in text.split()
        if len(word.strip("，。,.!?！？、")) >= 2
    ]
    unique_words = list(dict.fromkeys(words))
    if not unique_words:
        return "关键词：暂无"
    return "关键词：" + "、".join(unique_words[:5])


# ===================== 第3步：定义一个计划草稿工具 =====================
@agent_tool(
    name="draft_plan",
    description="为一个任务生成 3 个粗粒度执行步骤。",
    parameter_descriptions={
        "task": "需要拆解的用户任务。",
    },
)
def draft_plan(task: str) -> str:
    """生成固定格式的计划草稿。"""

    return "\n".join(
        [
            f"1. 明确目标：确认“{task}”的最终交付物。",
            "2. 拆解步骤：列出需要完成的关键阶段。",
            "3. 验证结果：检查输出是否满足目标和约束。",
        ]
    )


# ===================== 第4步：创建内置工具注册表 =====================
def build_builtin_tool_registry() -> ToolRegistry:
    """注册并返回本章可用的内置工具。"""

    registry = ToolRegistry()
    registry.register(summarize_text)
    registry.register(extract_keywords)
    registry.register(draft_plan)
    register_sandbox_file_tools(registry)
    register_sandbox_shell_tools(registry)
    register_sandbox_browser_tools(registry)
    register_search_tools(registry)
    register_mcp_tools(registry)
    register_a2a_tools(registry)
    register_multi_agent_tools(registry)
    return registry
