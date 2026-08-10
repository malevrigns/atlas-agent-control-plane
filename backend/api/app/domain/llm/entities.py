from dataclasses import dataclass


# ===================== 第1步：定义最小消息结构 =====================
@dataclass(slots=True)
class LLMMessage:
    role: str
    content: str


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
