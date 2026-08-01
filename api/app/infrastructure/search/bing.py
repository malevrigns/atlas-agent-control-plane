import re
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag

from app.core.config import settings
from app.core.exceptions import AppException
from app.domain.search.entities import SearchResponse, SearchResult


class BingSearchClient:
    """Bing Web Search 适配器。

    第 30 章先把搜索能力封装在这个 client 中。Agent 工具只依赖
    `search()` 方法，不直接知道 HTTP 地址、请求头和响应 JSON 结构。
    后续如果要换 Google、Tavily、SerpAPI 或自建搜索，只需要替换这一层。
    """

    def __init__(
        self,
        api_key: str,
        endpoint: str,
        market: str,
        timeout_seconds: float,
    ) -> None:
        # 1. 保存搜索引擎配置。这里不在构造函数中发请求，避免应用启动被网络阻塞。
        self.api_key = api_key
        self.endpoint = endpoint.rstrip("/")
        self.market = market
        self.timeout_seconds = timeout_seconds

    # ===================== 第1步：执行网页搜索 =====================
    def search(self, query: str, count: int) -> SearchResponse:
        """调用 Bing Web Search API，并转换成项目内统一结构。"""

        clean_query = query.strip()
        if not clean_query:
            raise AppException(
                message="search query is required",
                code=400,
                status_code=400,
            )

        # 2. 没有配置 API Key 时，降级为 Bing 页面搜索。
        #    课程环境里很多人没有 Bing Web Search API key；直接返回“未配置”
        #    会让 SearchTool 看起来不可用。这里借鉴浏览器搜索的常见做法，
        #    访问 bing.com/search 并解析页面里的自然结果。
        if not self.api_key:
            return self._search_bing_page(clean_query, count)

        try:
            # 3. Bing Web Search API 使用 Ocp-Apim-Subscription-Key 作为鉴权头。
            response = httpx.get(
                f"{self.endpoint}/v7.0/search",
                headers={"Ocp-Apim-Subscription-Key": self.api_key},
                params={
                    "q": clean_query,
                    "count": max(1, min(count, settings.search_max_results)),
                    "mkt": self.market,
                    "responseFilter": "Webpages",
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise AppException(
                message=f"bing search failed: HTTP {exc.response.status_code}",
                code=502,
                status_code=502,
            ) from exc
        except httpx.HTTPError as exc:
            raise AppException(
                message=f"bing search request failed: {exc}",
                code=502,
                status_code=502,
            ) from exc

        # 4. 把 Bing 原始 JSON 压成稳定结构，避免上层代码依赖供应商字段。
        payload = response.json()
        web_pages = payload.get("webPages", {})
        values = web_pages.get("value", [])
        items = [
            SearchResult(
                title=str(item.get("name") or ""),
                url=str(item.get("url") or ""),
                snippet=str(item.get("snippet") or ""),
            )
            for item in values
        ]

        return SearchResponse(
            query=clean_query,
            provider="bing",
            items=items,
        )

    # ===================== 第2步：无 API Key 时使用网页搜索降级 =====================
    def _search_bing_page(self, query: str, count: int) -> SearchResponse:
        """请求 Bing 搜索页，并从 HTML 中解析自然搜索结果。

        这个方法不是生产环境的首选方案，因为搜索页 DOM 可能变化。
        但它非常适合课程和本地开发：没有 API key 时，SearchTool 仍然能
        产生真实搜索结果，前端也能看到完整工具调用过程。
        """

        max_count = max(1, min(count, settings.search_max_results))
        bing_error = ""

        try:
            response = self._get_html(
                "https://www.bing.com/search",
                params={"q": query, "mkt": self.market},
            )
            if _is_bing_challenge_page(response.text):
                raise AppException(
                    message="bing page search returned a verification page",
                    code=502,
                    status_code=502,
                )
            items = _filter_low_quality_results(
                _parse_bing_results(response.text),
                query=query,
            )
            if items:
                return SearchResponse(
                    query=query,
                    provider="bing-page",
                    items=items[:max_count],
                )
            bing_error = "bing page search returned no parseable results"
        except (AppException, httpx.HTTPError) as exc:
            bing_error = str(exc)

        try:
            response = self._get_html(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
            )
            items = _filter_low_quality_results(
                _parse_duckduckgo_results(response.text),
                query=query,
            )
            if items:
                return SearchResponse(
                    query=query,
                    provider="duckduckgo-page",
                    items=items[:max_count],
                )
        except httpx.HTTPError as exc:
            raise AppException(
                message=(
                    "page search request failed: "
                    f"bing={bing_error}; duckduckgo={exc}"
                ),
                code=502,
                status_code=502,
            ) from exc

        raise AppException(
            message=(
                "page search returned no parseable results: "
                f"bing={bing_error}; duckduckgo=no results"
            ),
            code=502,
            status_code=502,
        )

    def _get_html(self, url: str, params: dict[str, str]) -> httpx.Response:
        """请求搜索 HTML 页面，并统一设置浏览器请求头。

        这里显式使用 trust_env=False，避免 Docker 或本机代理环境变量
        把搜索请求转发到不可用代理，导致 TLS EOF 这类网络错误。
        """

        response = httpx.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "close",
                "Upgrade-Insecure-Requests": "1",
            },
            params=params,
            timeout=self.timeout_seconds,
            follow_redirects=True,
        )
        response.raise_for_status()
        return response


def _parse_bing_results(html: str) -> list[SearchResult]:
    """从 Bing 搜索结果页中解析自然结果。

    Bing 搜索页不是稳定 API，页面结构可能因为地区、登录状态或 A/B
    实验变化。这里参考真实 Agent 项目常用做法，不只依赖单一 DOM
    路径，而是按“结果块 -> 标题链接 -> 摘要文本”的顺序做多层兜底。
    """

    soup = BeautifulSoup(html, "html.parser")
    results: list[SearchResult] = []

    # ===================== 第1步：定位 Bing 自然搜索结果块 =====================
    # 常规结果一般在 li.b_algo 中。这里保留 CSS 选择器，后续如果 Bing
    # DOM 变化，只需要补充选择器，不影响上层 SearchTool。
    for item in soup.select("li.b_algo"):
        if not isinstance(item, Tag):
            continue

        # ===================== 第2步：提取标题和链接 =====================
        # 首选 h2 > a，这是 Bing 自然结果最常见结构。
        title = ""
        url = ""
        title_link = item.select_one("h2 a")
        if isinstance(title_link, Tag):
            title = _clean_text(title_link.get_text(" ", strip=True))
            url = str(title_link.get("href") or "")

        # 如果 h2 缺失，退化为寻找结果块中第一个“像标题”的链接。
        # 这能覆盖部分特殊卡片或区域差异导致的结构变化。
        if not title:
            for link in item.find_all("a"):
                if not isinstance(link, Tag):
                    continue
                text = _clean_text(link.get_text(" ", strip=True))
                href = str(link.get("href") or "")
                if len(text) > 10 and href:
                    title = text
                    url = href
                    break

        if not title or not url:
            continue

        # ===================== 第3步：提取摘要 =====================
        # Bing 的摘要可能在 p、b_caption、b_descript、b_lineclamp 等位置。
        snippet = _extract_snippet(item, title)
        results.append(
            SearchResult(
                title=title,
                url=_normalize_bing_url(url),
                snippet=snippet,
            )
        )

    return results


def _parse_duckduckgo_results(html: str) -> list[SearchResult]:
    """从 DuckDuckGo HTML 搜索页解析自然结果。"""

    soup = BeautifulSoup(html, "html.parser")
    results: list[SearchResult] = []

    for item in soup.select(".result"):
        if not isinstance(item, Tag):
            continue

        link = item.select_one("a.result__a")
        if not isinstance(link, Tag):
            continue

        title = _clean_text(link.get_text(" ", strip=True))
        url = _normalize_duckduckgo_url(str(link.get("href") or ""))
        if not title or not url:
            continue

        snippet = ""
        snippet_node = item.select_one(".result__snippet")
        if isinstance(snippet_node, Tag):
            snippet = _clean_text(snippet_node.get_text(" ", strip=True))

        results.append(
            SearchResult(
                title=title,
                url=url,
                snippet=snippet,
            )
        )

    return results


def _filter_low_quality_results(
    results: list[SearchResult],
    *,
    query: str,
) -> list[SearchResult]:
    """过滤词典、翻译等明显偏题结果。

    页面搜索不是正式 API，中文地区搜索英文 query 时经常返回词典页。
    AI 新闻任务里这类结果会误导 Agent，所以在进入工具输出前先过滤。
    """

    return [
        result
        for result in results
        if not _is_dictionary_result(result) and _matches_query_topic(result, query)
    ]


def _is_dictionary_result(result: SearchResult) -> bool:
    """判断结果是否明显是词典、翻译或单词释义页面。"""

    text = f"{result.title} {result.url} {result.snippet}".lower()
    dictionary_markers = [
        "dictionary",
        "dict",
        "词典",
        "翻译",
        "读音",
        "音标",
        "释义",
        "同义词",
        "反义词",
        "iciba.com",
        "cambridge.org",
        "dictionary.net",
        "bing.com/dict",
        "baike.baidu.com/item/recent",
    ]
    return any(marker in text for marker in dictionary_markers)


def _matches_query_topic(result: SearchResult, query: str) -> bool:
    """保留和查询主题大致相关的结果。

    对 AI 新闻类查询，至少要求结果里出现 AI、人工智能、模型、Agent
    等主题词，避免 recent 这类单词页混入。
    """

    lower_query = query.lower()
    if not any(
        marker in lower_query
        for marker in ["ai", "artificial intelligence", "人工智能", "agent"]
    ):
        return True

    text = f"{result.title} {result.snippet}".lower()
    topic_markers = [
        "ai",
        "人工智能",
        "artificial intelligence",
        "agent",
        "智能体",
        "大模型",
        "模型",
        "openai",
        "anthropic",
        "google",
        "microsoft",
        "nvidia",
    ]
    return any(marker in text for marker in topic_markers)


def _is_bing_challenge_page(html: str) -> bool:
    """判断 Bing 是否返回验证码或验证页面。"""

    lower_html = html.lower()
    return (
        "captcha" in lower_html
        or "unusual traffic" in lower_html
        or "verify you are a human" in lower_html
    )


def _extract_snippet(item: Tag, title: str) -> str:
    """从一个搜索结果块中提取摘要文本。"""

    # 1. 优先找 Bing 常见的摘要容器。
    snippet_selector = (
        ".b_caption p, .b_caption, .b_descript, .b_lineclamp, p"
    )
    for node in item.select(snippet_selector):
        text = _clean_text(node.get_text(" ", strip=True))
        if len(text) > 20 and text != title:
            return text

    # 2. 如果没有标准摘要，就从整个结果块文本中切出较长句子。
    #    这样可以覆盖摘要被放进普通 div 的页面结构。
    all_text = _clean_text(item.get_text(" ", strip=True))
    for sentence in re.split(r"[.!?\n。！？]", all_text):
        clean_sentence = _clean_text(sentence)
        if len(clean_sentence) > 20 and clean_sentence != title:
            return clean_sentence

    return ""


def _normalize_bing_url(value: str) -> str:
    """补全 Bing 搜索页中的相对链接或协议相对链接。"""

    clean_value = value.strip()
    if clean_value.startswith("//"):
        return f"https:{clean_value}"
    return urljoin("https://www.bing.com", clean_value)


def _normalize_duckduckgo_url(value: str) -> str:
    """把 DuckDuckGo 跳转链接还原成真实目标链接。"""

    clean_value = value.strip()
    parsed = urlparse(clean_value)
    query = parse_qs(parsed.query)
    uddg = query.get("uddg")
    if uddg:
        return unquote(uddg[0])
    if clean_value.startswith("//"):
        return f"https:{clean_value}"
    return urljoin("https://duckduckgo.com", clean_value)


def _clean_text(value: str) -> str:
    """压缩空白字符，避免前端摘要出现奇怪换行。"""

    return re.sub(r"\s+", " ", value).strip()


def build_bing_search_client() -> BingSearchClient:
    """从全局配置创建 BingSearchClient。"""

    return BingSearchClient(
        api_key=settings.bing_search_api_key,
        endpoint=settings.bing_search_endpoint,
        market=settings.bing_search_market,
        timeout_seconds=settings.search_timeout_seconds,
    )
