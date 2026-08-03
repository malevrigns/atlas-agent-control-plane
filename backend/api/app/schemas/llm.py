from pydantic import BaseModel, Field


# ===================== 第1步：定义对外展示的 provider 信息 =====================
class LLMProviderResponse(BaseModel):
    name: str
    base_url: str
    api_key_env: str
    configured: bool


# ===================== 第2步：定义 LLM 配置接口响应 =====================
class LLMConfigResponse(BaseModel):
    default_provider: str
    default_model: str
    temperature: float
    max_tokens: int
    providers: list[LLMProviderResponse]


# ===================== 第3步：定义聊天请求中的消息结构 =====================
class LLMMessageRequest(BaseModel):
    role: str = Field(pattern="^(system|user|assistant)$")
    content: str = Field(min_length=1)


# ===================== 第4步：定义聊天请求体 =====================
class LLMChatRequest(BaseModel):
    messages: list[LLMMessageRequest] = Field(min_length=1)
    provider: str | None = None
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, gt=0)


# ===================== 第5步：定义聊天响应体 =====================
class LLMChatResponse(BaseModel):
    provider: str
    model: str
    content: str
    usage: dict | None = None
