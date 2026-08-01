from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_app_name: str = "AtlasAgent API"
    api_env: str = "development"
    api_version: str = "0.1.0"
    api_prefix: str = "/api"
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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
