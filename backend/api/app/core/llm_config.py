from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.exceptions import AppException


# ===================== 第1步：定义 YAML 中 llm 节点的数据结构 =====================
class LLMDefaults(BaseModel):
    default_provider: str
    default_model: str
    temperature: float = Field(ge=0, le=2)
    max_tokens: int = Field(gt=0)


# ===================== 第2步：定义每个模型服务商的连接配置 =====================
class LLMProviderConfig(BaseModel):
    base_url: str
    # 这里保存的是环境变量名称，不是真实密钥，避免把密钥写进配置文件。
    api_key_env: str = ""
    timeout_seconds: float = Field(gt=0)


# ===================== 第2.5步：定义 embedding 模型配置 =====================
class EmbeddingConfig(BaseModel):
    """RAG 使用的向量化模型配置。

    provider 指向 providers 中的某个服务商；base_url 留空时复用
    该服务商的聊天地址。dim 填 0 表示由首次真实响应自动学习维度。
    """

    provider: str
    model: str
    dim: int = Field(default=0, ge=0)
    base_url: str = ""
    batch_size: int = Field(default=16, gt=0)


# ===================== 第3步：定义完整 LLM 配置文件结构 =====================
class LLMConfig(BaseModel):
    llm: LLMDefaults
    providers: dict[str, LLMProviderConfig]
    embedding: EmbeddingConfig | None = None


# ===================== 第4步：读取、解析并校验 YAML 配置 =====================
@lru_cache
def load_llm_config() -> LLMConfig:
    path = Path(settings.llm_config_path)
    if not path.is_file():
        path = Path(__file__).resolve().parents[2] / "config/llm.yaml"
    if not path.is_file():
        raise AppException(
            message=f"LLM config file not found: {settings.llm_config_path}",
            code=500,
            status_code=500,
        )

    raw_config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    config = LLMConfig.model_validate(raw_config)
    # 默认 provider 必须能在 providers 中找到，否则后续聊天接口不知道该调用谁。
    if config.llm.default_provider not in config.providers:
        raise AppException(
            message="default LLM provider is not defined",
            code=500,
            status_code=500,
        )
    if config.embedding is not None and config.embedding.provider not in config.providers:
        raise AppException(
            message="embedding provider is not defined",
            code=500,
            status_code=500,
        )
    return config
