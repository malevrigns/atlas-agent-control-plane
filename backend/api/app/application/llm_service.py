import os

from app.core.exceptions import AppException
from app.core.llm_config import LLMConfig, load_llm_config
from app.core.module_policy import module_enabled
from app.domain.llm.entities import LLMChatRequest, LLMChatResult, LLMMessage
from app.infrastructure.llm.openai_compatible import OpenAICompatibleClient


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

    # ===================== 第3步：根据配置和请求参数发起模型调用 =====================
    async def chat(
        self,
        messages: list[LLMMessage],
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMChatResult:
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
        )
        client = OpenAICompatibleClient(
            api_key=api_key,
            base_url=provider_config.base_url,
            provider=provider_name,
            timeout_seconds=provider_config.timeout_seconds,
        )
        return await client.chat(request)
