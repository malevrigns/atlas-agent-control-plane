from dataclasses import dataclass


@dataclass(slots=True)
class SearchResult:
    """一条网页搜索结果。

    title 是页面标题，url 是页面地址，snippet 是搜索引擎返回的摘要。
    这三个字段也是前端工具预览面板展示搜索结果所需的最小信息。
    """

    title: str
    url: str
    snippet: str


@dataclass(slots=True)
class SearchResponse:
    """一次搜索调用的统一返回结构。"""

    query: str
    provider: str
    items: list[SearchResult]

