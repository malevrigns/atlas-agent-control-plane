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
    # ===================== 记忆生命周期：衰减与巩固 =====================
    # 是否启用后台生命周期任务（启动时注册，周期性执行衰减+巩固）。
    memory_decay_enabled: bool = True
    # 艾宾浩斯式衰减系数 λ：confidence * exp(-λ * days_since_last_access)。
    memory_decay_lambda_fact: float = 0.01
    memory_decay_lambda_preference: float = 0.005
    memory_decay_lambda_event: float = 0.05
    # 衰减后的置信度下限，低于该值的记忆不会再继续衰减写入。
    memory_decay_floor: float = 0.05
    # 单次衰减幅度小于该值时不写库，避免无意义的行更新。
    memory_decay_min_drop: float = 0.005
    # 巩固阈值：被检索命中 ≥ N 次且通过验证的记忆，authority 从 suggested 升为 verified。
    memory_consolidation_min_accesses: int = 3
    # 巩固后写入的置信度下限（检索反复命中本身就是佐证）。
    memory_consolidation_confidence: float = 0.9
    # 后台任务调度参数。
    memory_lifecycle_interval_seconds: int = 3600
    memory_lifecycle_limit: int = 1000
    # ===================== 记忆冲突消解 =====================
    # 同 subject + 同 predicate 但不同 value 的冲突消解策略：
    # latest_wins（默认，新记忆胜出）/ authority_wins（高权威胜出）/ manual_review（挂起人工复核）。
    memory_conflict_strategy: str = "latest_wins"
    # 冲突检测扫描的存量记忆上限。
    memory_conflict_scan_limit: int = 500
    # ===================== 记忆图谱关联 =====================
    # 单条记忆最多允许的关联边数，防止上下文爆炸。
    memory_graph_max_links: int = 3
    # expand_context 默认展开深度（硬上限 1，只带直接关联）。
    memory_graph_expand_depth: int = 1
    # 检索命中后是否顺带带上关联记忆。
    memory_graph_expand_enabled: bool = True
    file_storage_backend: str = "local"
    upload_dir: str = "uploads"
    artifact_dir: str = "artifacts"
    tool_output_inline_limit: int = 64 * 1024
    tool_default_timeout_seconds: float = 30.0
    tool_auto_approve_risk: str = "medium"
    # ===================== 工具结果缓存（Result Cache） =====================
    tool_cache_enabled: bool = True
    tool_cache_ttl_seconds: int = 300
    tool_cache_max_entries: int = 256
    # ===================== 工具调用重试与降级（Retry & Fallback） =====================
    tool_retry_enabled: bool = True
    tool_retry_max_retries: int = 2
    tool_retry_base_backoff_seconds: float = 1.5
    tool_retry_backoff_factor: float = 2.0
    # ===================== 工具调用预算（Budget） =====================
    tool_budget_max_calls_per_step: int = 12
    tool_budget_max_calls_per_tool: int = 4
    tool_budget_max_token_estimate: int = 100_000
    # ===================== 工具依赖并行批次（Dependency Graph） =====================
    # 同一批内用 asyncio.gather 并行执行；关闭后退回顺序执行。
    # 注意：有 uow（共享 async DB 会话）时并发写调用记录可能争抢 flush，
    # 如遇 "Session is already flushing" 可置为 false。
    tool_parallel_batches_enabled: bool = True
    # ===================== 多轮工具调用循环 =====================
    agent_tool_mode: str = "auto"
    agent_step_max_iterations: int = 15
    agent_step_max_tool_calls: int = 20
    agent_step_repeat_call_limit: int = 3
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
    # ---- RAG 高级检索：查询改写 / 父文档 / 重排（默认全部不依赖 LLM 也能工作） ----
    # 查询改写：把主查询扩展为若干变体（LLM 多查询优先，无 LLM 时规则改写），
    # 各查询独立召回后按 RRF 融合。variants 为 0 时退化为单查询（旧行为）。
    rag_query_expand_enabled: bool = True
    rag_query_expand_variants: int = 3
    # RRF（Reciprocal Rank Fusion）的 k 参数：越大名次差异越被平滑，推荐 60。
    rag_rrf_k: int = 60
    # 父文档检索（small-to-big）：摄取时先切父块（parent_size 字）再切子块，
    # 向量库只索引子块，命中后按 parent_seq 拼回父块作为上下文窗口。
    # 子块大小/重叠沿用知识库创建时冻结的 chunk_size / chunk_overlap。
    rag_parent_enabled: bool = True
    rag_parent_size: int = 2000
    # 旧文档（无父块信息）的邻块扩展窗口：命中 chunk 前后各扩展 N 个。
    rag_parent_neighbor_expand: int = 1
    # 重排：LLM listwise 打分优先，无 LLM（或调用失败）时降级为增强词法信号
    # （TF-IDF + 短语匹配 + 位置衰减），纯本地计算，离线可用。
    rag_rerank_enabled: bool = True
    rag_rerank_use_llm: bool = True
    rag_rerank_top_n: int = 10
    # final_score 融合权重：0.5*向量(含 RRF 融合) + 0.3*词法 + 0.2*重排；
    # 重排不可用时自动回退到 0.7*向量 + 0.3*词法（旧公式）。
    rag_weight_vector: float = 0.5
    rag_weight_lexical: float = 0.3
    rag_weight_rerank: float = 0.2
    # 引用置信度的新鲜度半衰期（天）：文档距上次更新越久，置信度衰减越快。
    rag_confidence_freshness_half_life_days: float = 180.0
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: SecretStr = SecretStr("")
    qdrant_timeout_seconds: float = 10.0
    # ===================== 技能注册中心 =====================
    context_skill_limit: int = 3
    context_skill_max_chars: int = 2000
    context_skill_min_score: float = 0.1
    # ===================== 直答路径的附件内容注入 =====================
    # 最近 N 个附件的文本内容（文本直读 / PDF 抽取）注入对话上下文。
    chat_attachment_limit: int = 3
    chat_attachment_context_chars: int = 20000
    chat_attachment_max_file_bytes: int = 15 * 1024 * 1024
    # ===================== 直答路径的知识库自动检索（RAG） =====================
    # 每次直答前自动检索所有知识库；top_k 设为 0 可整体关闭。
    # min_score 的尺度不直观：向量分由余弦按 (cos+1)/2 映射，
    # 完全无关的内容也有约 0.35 的底噪，所以阈值必须明显高于它才有意义。
    # 0.42 是实测值——无关问题最高 0.388、相关命中 0.46 以上，取两者中点。
    chat_rag_top_k: int = 4
    chat_rag_min_score: float = 0.42
    chat_rag_context_chars: int = 6000
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
