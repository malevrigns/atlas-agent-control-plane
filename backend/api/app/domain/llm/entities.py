from dataclasses import dataclass, field
from typing import Any


# ===================== 第1步：定义最小消息结构 =====================
@dataclass(slots=True)
class LLMMessage:
    role: str
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    # assistant 消息可携带模型请求调用的工具（原生 function calling）。
    tool_calls: list["LLMToolCall"] | None = None


# ===================== 第1.5步：定义一次工具调用 =====================
@dataclass(slots=True)
class LLMToolCall:
    """模型请求调用的一次工具（OpenAI 兼容 tool_calls 的归一化表示）。"""

    id: str
    name: str
    arguments: dict[str, Any]


# ===================== 第2步：定义一次模型调用需要的完整参数 =====================
@dataclass(slots=True)
class LLMChatRequest:
    messages: list[LLMMessage]
    model: str
    provider: str
    temperature: float
    max_tokens: int
    # 附加到请求体的服务商专有字段（如 DashScope 的 enable_thinking）。
    extra_body: dict | None = None
    # 原生 function calling 的工具 schema 与选择策略（auto/none/required）。
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | None = None


# ===================== 第2.5步：定义流式输出的一段增量 =====================
@dataclass(slots=True)
class LLMStreamDelta:
    """一段流式增量。kind 为 content（正文）或 reasoning（思考过程）。"""

    kind: str
    text: str


# ===================== 第3步：定义模型调用完成后的统一结果 =====================
@dataclass(slots=True)
class LLMChatResult:
    provider: str
    model: str
    content: str
    usage: dict | None = None
    # 模型本轮请求调用的工具；为空表示模型给出了最终文本回答。
    tool_calls: list[LLMToolCall] = field(default_factory=list)
