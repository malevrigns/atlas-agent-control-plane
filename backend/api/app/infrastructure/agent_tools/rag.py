"""RAG 检索工具。

把知识库检索注册为 Agent 可调用工具。Agent 在 ReAct 循环中可以
主动查询知识库，拿到带 [编号] 引用的证据片段再作答。

实现说明：这是项目里第一个异步 handler 工具——检索需要访问
PostgreSQL 与向量存储，ToolRuntime 会直接 await 异步 handler，
不再经过线程池。工具自己开独立数据库会话，与调用方事务隔离。
"""

import json
from uuid import UUID

from app.application.unit_of_work import UnitOfWork
from app.core.exceptions import AppException
from app.domain.agent_core.tools import (
    AgentTool,
    ToolDefinition,
    ToolParameter,
    ToolRegistry,
    ToolRiskLevel,
)
from app.infrastructure.database.session import AsyncSessionLocal


def register_rag_tools(registry: ToolRegistry) -> None:
    """注册 knowledge_search 工具。"""

    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="knowledge_search",
                description=(
                    "在指定知识库中检索与问题相关的内容片段，"
                    "返回带引用编号和评分的证据，用于回答业务与领域问题。"
                ),
                risk_level=ToolRiskLevel.low,
                required_permissions=(),
                idempotent=True,
                timeout_seconds=20.0,
                parameters=[
                    ToolParameter(
                        name="knowledge_base_id",
                        type="string",
                        description="知识库 ID（UUID）。可先通过 /api/rag/knowledge-bases 查询。",
                    ),
                    ToolParameter(
                        name="query",
                        type="string",
                        description="要检索的问题或关键词。",
                    ),
                    ToolParameter(
                        name="top_k",
                        type="integer",
                        description="返回片段数量，默认 5。",
                        required=False,
                    ),
                ],
            ),
            handler=_run_knowledge_search,
        )
    )


async def _run_knowledge_search(
    knowledge_base_id: str,
    query: str,
    top_k: int | None = None,
) -> str:
    """执行知识库检索，把结果格式化为前端可解析的 JSON。

    与 SearchTool 一致：检索失败不应让整次 Agent 任务失败，
    错误会转换成结构化输出，前端与模型都能看到失败原因。
    """

    from app.application.rag_service import RagService

    try:
        kb_id = UUID(str(knowledge_base_id))
    except ValueError:
        return json.dumps(
            {
                "kind": "rag_error",
                "message": f"invalid knowledge_base_id: {knowledge_base_id}",
                "items": [],
            },
            ensure_ascii=False,
        )

    try:
        async with AsyncSessionLocal() as db_session:
            service = RagService(UnitOfWork(db_session))
            result = await service.query(
                kb_id,
                query=str(query),
                top_k=_normalize_top_k(top_k),
            )
    except AppException as exc:
        return json.dumps(
            {
                "kind": "rag_error",
                "knowledge_base_id": str(knowledge_base_id),
                "query": str(query),
                "message": exc.message,
                "items": [],
            },
            ensure_ascii=False,
        )

    return json.dumps(
        {
            "kind": "rag_results",
            "knowledge_base_id": str(result.knowledge_base_id),
            "query": result.query,
            "backend": result.backend,
            "context_text": result.context_text,
            "items": [
                {
                    "citation": chunk.citation,
                    "document_title": chunk.document_title,
                    "seq": chunk.seq,
                    "content": chunk.content,
                    "final_score": chunk.final_score,
                    "vector_score": chunk.vector_score,
                    "lexical_score": chunk.lexical_score,
                }
                for chunk in result.chunks
            ],
        },
        ensure_ascii=False,
    )


def _normalize_top_k(value: int | str | None) -> int | None:
    if value is None:
        return None
    try:
        top_k = int(value)
    except (TypeError, ValueError):
        return None
    return max(1, min(top_k, 20))
