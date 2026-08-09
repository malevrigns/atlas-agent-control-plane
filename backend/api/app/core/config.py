from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_app_name: str = "AtlasAgent API"
    api_env: str = "development"
    api_version: str = "0.1.0"
    api_prefix: str = "/api"
    api_auth_enabled: bool = False
    atlas_api_key: SecretStr = SecretStr("")
    cors_allow_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = ["*"]
    cors_allow_headers: list[str] = ["*"]
    log_level: str = "INFO"
    llm_config_path: str = "runtime-config/llm.yaml"
    mcp_config_path: str = "runtime-config/mcp.yaml"
    a2a_config_path: str = "runtime-config/a2a.yaml"
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/atlas_agents"
    )
    database_echo: bool = False
    redis_url: str = "redis://localhost:6379/0"
    agent_task_stream: str = "agent:tasks"
    agent_task_consumer_group: str = "atlas-agent-runners"
    agent_task_claim_idle_ms: int = 30_000
    agent_task_max_concurrency: int = 4
    agent_task_poll_timeout_ms: int = 1000
    context_message_limit: int = 8
    context_event_limit: int = 20
    context_max_message_chars: int = 1200
    context_memory_candidate_limit: int = 100
    context_memory_limit: int = 6
    context_memory_max_chars: int = 2400
    context_memory_item_max_chars: int = 500
    context_memory_min_score: float = 0.12
    file_storage_backend: str = "local"
    upload_dir: str = "uploads"
    artifact_dir: str = "artifacts"
    tool_output_inline_limit: int = 64 * 1024
    tool_default_timeout_seconds: float = 30.0
    tool_auto_approve_risk: str = "medium"
    max_upload_size: int = 10 * 1024 * 1024
    max_file_preview_size: int = 64 * 1024
    sandbox_api_base_url: str = "http://localhost:8100/api"
    sandbox_auth_enabled: bool = False
    sandbox_api_timeout_seconds: float = 30.0
    sandbox_shell_wait_timeout_seconds: float = 10.0
    docker_sandbox_id: str = "default"
    docker_sandbox_name: str = "atlas-sandbox"
    docker_sandbox_wait_retries: int = 10
    docker_sandbox_wait_interval_seconds: float = 1.0
    bing_search_api_key: str = ""
    bing_search_endpoint: str = "https://api.bing.microsoft.com"
    bing_search_market: str = "zh-CN"
    search_timeout_seconds: float = 10.0
    search_max_results: int = 5
    # ===================== RAG 检索增强生成 =====================
    # 向量后端：pgvector（默认，复用 PostgreSQL）或 qdrant（独立服务）。
    rag_vector_backend: str = "pgvector"
    # embedding 实现：auto（按 llm.yaml 与密钥自动选择）或 local_hash（强制本地）。
    rag_embedding_provider: str = "auto"
    rag_embedding_dim: int = 256
    rag_chunk_size: int = 800
    rag_chunk_overlap: int = 120
    rag_top_k: int = 5
    rag_candidate_limit: int = 24
    rag_min_score: float = 0.15
    rag_max_context_chars: int = 3600
    rag_max_document_chars: int = 200_000
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: SecretStr = SecretStr("")
    qdrant_timeout_seconds: float = 10.0
    # ===================== 技能注册中心 =====================
    context_skill_limit: int = 3
    context_skill_max_chars: int = 2000
    context_skill_min_score: float = 0.1
    module_config_path: str = "runtime-config/modules.yaml"
    mcp_stdio_enabled: bool = False
    mcp_stdio_allowed_commands: list[str] = []
    mcp_http_allowed_hosts: list[str] = []
    a2a_http_allowed_hosts: list[str] = []

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
