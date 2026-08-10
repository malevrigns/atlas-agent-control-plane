import base64
import os

from app.core.exceptions import AppException
from app.core.llm_config import LLMConfig, load_llm_config
from app.core.module_policy import module_enabled
from app.domain.llm.entities import LLMChatRequest, LLMChatResult, LLMMessage
from app.infrastructure.llm.openai_compatible import OpenAICompatibleClient

# 视觉解析的默认提示词：面向 RAG 检索优化，要求完整、结构化、不省略。
DEFAULT_VISION_PROMPT = (
    "你是文档数字化助手。请完整提取这张图片中的所有信息，输出结构化 Markdown：\n"
    "1. 逐字提取全部可见文字（含表格，用 Markdown 表格还原）；\n"
    "2. 描述图表/流程图/架构图的结构与关键数据；\n"
    "3. 最后用一段话概括图片主题。\n"
    "不要省略内容，不要添加图片中不存在的信息。"
)


# ===================== 第1步：编写 LLM 应用服务 =====================
class LLMService:
    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or load_llm_config()

    # ===================== 第2步：返回可公开展示的配置 =====================
    def get_public_config(self) -> dict:
        return {
            "default_provider": self.config.llm.default_provider,
            "default_model": self.config.llm.default_model,
            "temperature": self.config.llm.temperature,
            "max_tokens": self.config.llm.max_tokens,
            "providers": [
                {
                    "name": name,
                    "base_url": provider.base_url,
                    "api_key_env": provider.api_key_env,
                    # 只返回是否已配置，不返回真实密钥。
                    "configured": bool(os.getenv(provider.api_key_env)),
                }
                for name, provider in self.config.providers.items()
            ],
        }

    # ===================== 第3步：解析 provider 配置并组装请求 =====================
    def _prepare_request(
        self,
        messages: list[LLMMessage],
        provider: str | None,
        model: str | None,
        temperature: float | None,
        max_tokens: int | None,
        extra_body: dict | None = None,
    ) -> tuple[LLMChatRequest, OpenAICompatibleClient]:
        if not module_enabled("llm"):
            raise AppException(message="LLM module is disabled", code=503, status_code=503)
        provider_name = provider or self.config.llm.default_provider
        provider_config = self.config.providers.get(provider_name)
        if provider_config is None:
            raise AppException(
                message=f"LLM provider not found: {provider_name}",
                code=400,
                status_code=400,
            )

        api_key = os.getenv(provider_config.api_key_env)
        if not api_key:
            # 密钥只能来自环境变量，不能写进 YAML，也不能从接口传入。
            raise AppException(
                message=f"LLM api key is not configured: {provider_config.api_key_env}",
                code=500,
                status_code=500,
            )

        # 请求参数优先使用接口传入值；没有传入时使用 YAML 默认值。
        request = LLMChatRequest(
            messages=messages,
            model=model or self.config.llm.default_model,
            provider=provider_name,
            temperature=temperature
            if temperature is not None
            else self.config.llm.temperature,
            max_tokens=max_tokens if max_tokens is not None else self.config.llm.max_tokens,
            extra_body=extra_body,
        )
        client = OpenAICompatibleClient(
            api_key=api_key,
            base_url=provider_config.base_url,
            provider=provider_name,
            timeout_seconds=provider_config.timeout_seconds,
        )
        return request, client

    # ===================== 第4步：根据配置和请求参数发起模型调用 =====================
    async def chat(
        self,
        messages: list[LLMMessage],
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMChatResult:
        request, client = self._prepare_request(
            messages, provider, model, temperature, max_tokens
        )
        return await client.chat(request)

    # ===================== 第5步：流式模型调用，逐段产出回复文本 =====================
    def is_configured(self) -> bool:
        """判断默认 provider 是否已具备可用密钥。"""

        provider_config = self.config.providers.get(self.config.llm.default_provider)
        if provider_config is None:
            return False
        return bool(os.getenv(provider_config.api_key_env))

    def thinking_enabled(self) -> bool:
        """流式对话是否默认请求思考过程。"""

        return bool(self.config.llm.thinking)

    def vision_enabled(self) -> bool:
        """是否配置了视觉模型（多模态解析可用）。"""

        return bool(self.config.llm.vision_model)

    # ===================== 第6步：视觉模型解析图片 =====================
    async def vision_extract(
        self,
        *,
        image_bytes: bytes,
        content_type: str,
        prompt: str | None = None,
        max_tokens: int = 2000,
    ) -> str:
        """用配置的视觉模型把图片解析成结构化文本。"""

        if not module_enabled("llm"):
            raise AppException(message="LLM module is disabled", code=503, status_code=503)
        vision_model = self.config.llm.vision_model
        if not vision_model:
            raise AppException(
                message="vision model is not configured (llm.vision_model)",
                code=503,
                status_code=503,
            )
        provider_name = self.config.llm.default_provider
        provider_config = self.config.providers.get(provider_name)
        if provider_config is None:
            raise AppException(
                message=f"LLM provider not found: {provider_name}",
                code=400,
                status_code=400,
            )
        api_key = os.getenv(provider_config.api_key_env)
        if not api_key:
            raise AppException(
                message=f"LLM api key is not configured: {provider_config.api_key_env}",
                code=500,
                status_code=500,
            )

        clean_type = (content_type or "image/png").split(";")[0].strip()
        encoded = base64.b64encode(image_bytes).decode("ascii")
        client = OpenAICompatibleClient(
            api_key=api_key,
            base_url=provider_config.base_url,
            provider=provider_name,
            timeout_seconds=provider_config.timeout_seconds,
        )
        return await client.chat_vision(
            model=vision_model,
            image_data_url=f"data:{clean_type};base64,{encoded}",
            prompt=prompt or DEFAULT_VISION_PROMPT,
            max_tokens=max_tokens,
            # 图片解析比纯文本慢，放宽到配置超时的 2 倍。
            timeout_seconds=provider_config.timeout_seconds * 2,
        )

    async def chat_stream(
        self,
        messages: list[LLMMessage],
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        thinking: bool | None = None,
    ):
        """流式模型调用，逐段产出 LLMStreamDelta（reasoning / content）。

        thinking 为 None 时使用 llm.yaml 的 thinking 配置；
        开启时向服务商附加 enable_thinking（DashScope/Qwen 约定）。
        """

        effective_thinking = self.thinking_enabled() if thinking is None else thinking
        request, client = self._prepare_request(
            messages,
            provider,
            model,
            temperature,
            max_tokens,
            extra_body={"enable_thinking": True} if effective_thinking else None,
        )
        async for delta in client.chat_stream(request):
            yield delta
