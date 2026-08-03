import json

from app.core.config import settings
from app.core.exceptions import AppException
from app.domain.agent_core.tools import (
    AgentTool,
    ToolDefinition,
    ToolParameter,
    ToolRegistry,
    ToolRiskLevel,
)
from app.domain.search.entities import SearchResponse
from app.infrastructure.search.bing import BingSearchClient, build_bing_search_client


def register_search_tools(
    registry: ToolRegistry,
    client: BingSearchClient | None = None,
) -> None:
    """把网页搜索能力注册成 Agent 可调用工具。

    SearchTool 不直接写会话事件。它只返回工具执行结果，
    ReActAgentService 会统一把结果包装成 `tool_called` 事件。
    """

    # 1. 默认使用 Bing 适配器。测试或后续多搜索引擎时，可以传入别的 client。
    search_client = client or build_bing_search_client()

    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="search_web",
                description="搜索互联网公开网页，返回标题、链接和摘要。",
                risk_level=ToolRiskLevel.medium,
                required_permissions=("network:access",),
                parameters=[
                    ToolParameter(
                        name="query",
                        type="string",
                        description="搜索关键词或问题，例如 Python 3.12 release notes。",
                    ),
                    ToolParameter(
                        name="count",
                        type="integer",
                        description="返回结果数量，默认 5，最大值由 SEARCH_MAX_RESULTS 控制。",
                        required=False,
                    ),
                ],
            ),
            handler=lambda query, count=5: _run_search_tool(
                client=search_client,
                query=str(query),
                count=_normalize_count(count),
            ),
        )
    )


def _normalize_count(value: object) -> int:
    """把工具参数里的 count 转成安全整数。"""

    try:
        count = int(value) if value is not None else 5
    except (TypeError, ValueError):
        count = 5
    return max(1, min(count, settings.search_max_results))


def _format_search_response(data: SearchResponse) -> str:
    """把搜索结果格式化成前端可解析的 JSON 字符串。

    这里使用 `kind=search_results`，第 29 章的工具预览面板可以根据
    kind 判断应该显示图片、搜索结果、Shell 输出还是普通文本。
    """

    return json.dumps(
        {
            "kind": "search_results",
            "provider": data.provider,
            "query": data.query,
            "items": [
                {
                    "title": item.title,
                    "url": item.url,
                    "snippet": item.snippet,
                }
                for item in data.items
            ],
        },
        ensure_ascii=False,
    )


def _run_search_tool(
    *,
    client: BingSearchClient,
    query: str,
    count: int,
) -> str:
    """执行搜索工具，并把网络失败转换成结构化工具输出。

    Agent 的一次任务不应该因为搜索页 TLS EOF 就整体失败。
    搜索不可用时，前端仍然能在工具详情里看到错误原因和重试建议。
    """

    try:
        return _format_search_response(client.search(query=query, count=count))
    except AppException as exc:
        return json.dumps(
            {
                "kind": "search_error",
                "provider": "page-search",
                "query": query,
                "message": exc.message,
                "items": [],
            },
            ensure_ascii=False,
        )
