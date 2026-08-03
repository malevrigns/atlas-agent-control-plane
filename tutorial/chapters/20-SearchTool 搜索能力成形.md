# 第二十章. SearchTool 搜索能力成形

## 20.1 本章目标
​        前面几章已经让 Agent 具备了读写文件、执行 Shell、打开浏览器、截图观察以及查看 VNC 桌面的能力。到这里为止，它已经可以在一个受控环境里完成很多本地任务，但它仍然缺少一种非常基础的外部感知能力：主动搜索公开网页资料。真实的 Agent 不可能只依赖用户输入和已有上下文，它需要在遇到“最新版本”“官方说明”“某个库的使用方式”“某个问题的背景资料”时，把搜索作为一种可调用工具纳入执行流程。
​        本章的目标，就是把搜索能力做成 `search_web` 工具。它不是在模型提示词里简单告诉模型“你可以搜索”，而是在后端明确增加搜索领域模型、Bing Web Search 适配器、工具注册逻辑、ReAct 触发规则和前端预览渲染。这样做完以后，搜索会像 FileTool、ShellTool、BrowserTool 一样进入同一套工具协议：有工具名称，有参数，有输出，有 `tool_called` 事件，也有右侧工具预览面板里的可观察结果。
​        本章完成后，你应该能够理解三件事。第一，搜索工具为什么要通过领域模型隔离供应商返回结构；第二，为什么工具层应该返回稳定 JSON，而不是把 Bing 的原始响应直接塞给前端；第三，为什么搜索结果属于“可观察资料”，而不是模型隐藏推理的一部分。这个边界越清楚，后面接入 MCP、A2A 和多 Agent 协作时，系统越容易扩展。

## 20.2 最终效果
​        本章结束后，当用户输入一个明显需要查资料的任务时，例如“搜索一下 Playwright 最新版本的发布说明”或者“查询某个库的官方文档”，任务计划进入执行阶段后，`ReActAgentService` 会识别文本里的搜索意图，并调用 `search_web` 工具。工具调用完成后，后端会把输出写成 `tool_called` 事件，前端的工具预览面板会把这次输出渲染为搜索结果卡片。
​        从用户视角看，搜索工具的执行链路是这样的：

```Plain
用户任务
  |
  v
Planner 生成计划
  |
  v
ReActAgentService 执行步骤
  |
  v
根据“搜索、查询、最新、资料”等关键词选择 search_web
  |
  v
BingSearchClient 请求 Bing Web Search API
  |
  v
SearchResponse 转成 kind=search_results 的 JSON 字符串
  |
  v
tool_called 事件进入会话事件流
  |
  v
ToolPreviewPanel 展示搜索关键词、供应商、标题、链接和摘要
```

​        如果本地暂时没有配置 `BING_SEARCH_API_KEY`，系统不会伪造真实搜索结果，而是返回一条明确的配置提示。这个提示同样会走完整的工具事件链路，所以即使没有申请 Bing Key，也能验证工具注册、ReAct 选择、事件写入和前端渲染是否打通。它的意义不是让搜索“假装成功”，而是在教学环境里清楚地暴露当前缺少外部凭据，并保留可观察的调试路径。

## 20.3 本章要解决的问题
​        前面的工具更多是在沙箱内部工作。FileTool 操作文件，ShellTool 执行命令，BrowserTool 打开网页和截图，VNC 负责让用户观察浏览器桌面。这些能力解决的是“Agent 如何在环境里行动”的问题，而 SearchTool 要解决的是“Agent 如何获得新的公开资料”的问题。
​        如果没有搜索工具，Agent 面对“最新资料”这类任务时只能依赖模型训练时的旧知识，或者依赖用户提前提供的上下文。这样的 Agent 看起来能回答问题，但工程上并不可靠。搜索能力进入工具系统以后，模型可以把“我需要查资料”变成一次可记录、可复现、可展示的工具调用。后端知道它查了什么，前端知道它返回了什么，用户也能打开结果链接判断资料是否可信。
​        本章还要处理一个产品层面的问题。搜索结果不能只作为后端字符串存在，它需要在右侧工具预览面板里以更适合阅读的形式出现。普通工具输出可以直接放进 `pre` 文本框，但搜索结果更像一组网页条目，应该展示标题、链接和摘要。第 19 章刚整理出统一工具预览面板，本章正好让它承接第一种新工具类型。

## 20.4 本章技术方案
​        本章采用“领域模型、供应商适配、工具注册、执行选择、前端解析”五层结构。搜索供应商的原始响应只停留在 `infrastructure/search/bing.py` 里，工具层只接触项目自己的 `SearchResponse`，前端只接触稳定的 `kind=search_results` JSON。每一层都只知道自己需要知道的内容。
​        后端新增的领域结构很小，只包含 `SearchResult` 和 `SearchResponse`。`SearchResult` 表示一条网页结果，最小字段是标题、链接和摘要；`SearchResponse` 表示一次搜索调用，记录原始查询词、供应商名称和结果列表。这个模型不追求覆盖所有搜索引擎字段，它只保留当前 Agent 执行和前端展示真正需要的最小信息。
​        Bing 适配器负责把配置、HTTP 请求、异常转换和响应解析放在一个类里。它通过 `settings.bing_search_api_key`、`settings.bing_search_endpoint`、`settings.bing_search_market` 等配置创建请求，然后把 Bing 返回的 `webPages.value` 压成 `SearchResult` 列表。这样以后如果要换成 Tavily、SerpAPI、自建搜索服务或内网知识库，只需要替换适配层，工具协议和前端展示不必重新设计。
​        工具注册层把搜索能力命名为 `search_web`。这个名字和前面 `browser_open`、`browser_screenshot`、`file_read`、`shell_exec` 一样，是 Agent 工具协议的一部分。工具的输入参数是 `query` 和 `count`，输出是 JSON 字符串。之所以输出字符串，是因为当前工具协议已经把工具结果当作文本输出写入事件；之所以这个字符串内部仍然是 JSON，是为了让前端能够识别它是不是结构化搜索结果。

## 20.5 新增和修改的文件
​        本章的改动跨过后端配置、领域层、基础设施层、工具层、Agent 执行层和前端展示层。它不是一个单点功能，而是一条从用户任务到页面观察的完整通道。涉及的文件如下：

```Plain
.env.example
docker-compose.yml
api/app/core/config.py
api/app/domain/search/__init__.py
api/app/domain/search/entities.py
api/app/infrastructure/search/__init__.py
api/app/infrastructure/search/bing.py
api/app/infrastructure/agent_tools/search.py
api/app/infrastructure/agent_tools/builtin.py
api/app/application/react_agent_service.py
ui/app/components/tool-preview-panel.tsx
README.md
api/README.md
docs/course/chapters/30-search-tool.md
```

​        这些文件可以分成两条线理解。第一条是后端工具线，从配置读取到 Bing 请求，再到 `search_web` 注册和 ReAct 调用；第二条是前端观察线，从 `tool_called` 事件读取输出，再到工具预览面板解析 `search_results` 并展示为搜索卡片。只要这两条线都通了，搜索能力就不是一个孤立函数，而是工作台的一部分。

## 20.6 实施步骤
​        这一章的实施顺序要从配置开始，而不是从工具函数开始。搜索工具依赖外部供应商，外部供应商又依赖 API Key、endpoint、市场语言和超时时间。配置没有定义清楚，工具函数写得再完整也没有稳定运行环境。因此本章先补充配置，再定义领域模型，然后实现 Bing 适配器，最后把工具接入执行链路和前端展示。

### 20.6.1 补充搜索配置
​        `api/app/core/config.py` 是后端应用配置的集中入口。本章在 `Settings` 中新增五个字段，用来描述搜索能力的外部依赖和运行边界。

```Python
bing_search_api_key: str = ""
bing_search_endpoint: str = "https://api.bing.microsoft.com"
bing_search_market: str = "zh-CN"
search_timeout_seconds: float = 10.0
search_max_results: int = 5
```

​        `bing_search_api_key` 保存 Bing Web Search API 的访问凭据，默认值为空。默认留空是为了让项目在没有搜索凭据时仍然能启动，但工具调用会明确返回“尚未配置”的提示结果。`bing_search_endpoint` 默认指向 Bing API 地址，保留成配置项是为了方便后续接入代理、私有网关或者兼容接口。`bing_search_market` 控制搜索市场和语言环境，本章使用 `zh-CN`，这样中文任务更容易返回中文网页摘要。
​        `search_timeout_seconds` 控制 HTTP 请求最长等待时间。搜索是外部网络调用，不应该无限阻塞 Agent 执行。`search_max_results` 控制最大返回条数，避免模型一次请求过多网页摘要，导致事件体和前端展示都变得臃肿。这里的限制是显式配置，不是隐藏降级；用户可以在环境变量中改它，代码会按配置执行。

### 20.6.2 更新环境变量模板和 Compose
​        配置字段加入 `Settings` 以后，还要让 `.env.example` 和 `docker-compose.yml` 能把这些值传进容器。否则本地开发读得到默认值，但容器部署时很容易出现配置遗漏。

```Plain
BING_SEARCH_API_KEY=
BING_SEARCH_ENDPOINT=https://api.bing.microsoft.com
BING_SEARCH_MARKET=zh-CN
SEARCH_TIMEOUT_SECONDS=10
SEARCH_MAX_RESULTS=5
```

​        Compose 中对应的环境变量写法如下：

```Yaml
BING_SEARCH_API_KEY: ${BING_SEARCH_API_KEY:-}
BING_SEARCH_ENDPOINT: ${BING_SEARCH_ENDPOINT:-https://api.bing.microsoft.com}
BING_SEARCH_MARKET: ${BING_SEARCH_MARKET:-zh-CN}
SEARCH_TIMEOUT_SECONDS: ${SEARCH_TIMEOUT_SECONDS:-10}
SEARCH_MAX_RESULTS: ${SEARCH_MAX_RESULTS:-5}
```

​        这一步看起来只是配置抄写，但它保证了文档、开发环境和容器环境使用同一组名字。后面排查搜索问题时，读者只需要检查 `.env`、Compose 环境和 `Settings` 字段是否一致，不需要在不同层之间猜测配置映射。

### 20.6.3 定义搜索领域模型
​        搜索结果先进入领域模型，再进入工具层。这样做的核心目的，是把“搜索结果对本项目意味着什么”从“Bing API 原始 JSON 长什么样”里分离出来。

```Python
from dataclasses import dataclass

@dataclass(slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str

@dataclass(slots=True)
class SearchResponse:
    query: str
    provider: str
    items: list[SearchResult]
```

​        `SearchResult` 只保留三个字段。`title` 用来展示网页标题，`url` 用来让用户打开来源，`snippet` 用来展示搜索引擎返回的摘要。这个最小模型对 Agent 来说已经足够，因为 Agent 执行阶段更需要可读线索和可追溯链接，而不是供应商返回的所有排名、缓存、广告或附加字段。
​        `SearchResponse` 多保存了 `query` 和 `provider`。`query` 能让前端清楚显示这次搜索到底查了什么；`provider` 能让用户知道结果来自 Bing、禁用提示，还是未来的其他搜索供应商。这个字段在当前章看起来不复杂，但它给后续多供应商扩展留下了稳定位置。

### 20.6.4 实现 BingSearchClient
​        `BingSearchClient` 是搜索供应商适配层。它的职责不是注册 Agent 工具，也不是写会话事件，而是单纯完成一次网页搜索，并把供应商响应转换成项目内部结构。

```Python
class BingSearchClient:
    def __init__(
        self,
        api_key: str,
        endpoint: str,
        market: str,
        timeout_seconds: float,
    ) -> None:
        self.api_key = api_key
        self.endpoint = endpoint.rstrip("/")
        self.market = market
        self.timeout_seconds = timeout_seconds
```

​        构造函数只保存配置，不主动发起网络请求。这个细节很重要，因为应用启动时不应该因为外部搜索服务暂时不可用而卡住。真正的网络调用只发生在 `search()` 方法里，也就是 Agent 确实需要搜索的时候。
​        `search()` 方法先清理查询词。如果查询词为空，它会抛出 `AppException`，因为空搜索不是一个有效工具调用。这个错误应该暴露出来，而不是被吞掉后返回空结果。工具系统越往后发展，参数错误越应该在边界处明确失败，否则调试时很难判断是模型传参错误、工具实现错误，还是供应商没有返回数据。

```Python
clean_query = query.strip()
if not clean_query:
    raise AppException(
        message="search query is required",
        code=400,
        status_code=400,
    )
```

​        如果没有配置 `api_key`，适配器会返回一个 `provider="bing-disabled"` 的响应，并在结果条目中提示用户配置 `BING_SEARCH_API_KEY`。这里的关键是“明确提示”，不是静默退化。它不会把占位内容包装成真实搜索结果，也不会让用户误以为已经访问了 Bing。这样做能让没有 Key 的教学环境继续走通事件链路，同时让缺失配置在 UI 上清晰可见。
​        有 Key 时，适配器通过 `httpx.get()` 请求 Bing Web Search API。请求头使用 `Ocp-Apim-Subscription-Key`，参数里传入 `q`、`count`、`mkt` 和 `responseFilter`。其中 `count` 会被限制在 `1` 到 `settings.search_max_results` 之间，避免调用方传入过大值。

```Python
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
```

​        HTTP 状态码错误和网络错误都会被转换成 `AppException`，并使用 `502` 表示上游搜索服务失败。这样 API 层和任务执行层看到的是项目内统一异常，而不是散落的 `httpx` 异常类型。最后，适配器读取 `payload["webPages"]["value"]`，把每个网页条目转换成 `SearchResult`，再组装成 `SearchResponse` 返回。

### 20.6.5 构建 BingSearchClient
​        为了让工具注册层不用知道配置细节，本章新增 `build_bing_search_client()`。它从全局 `settings` 读取搜索配置，然后创建 `BingSearchClient`。

```Python
def build_bing_search_client() -> BingSearchClient:
    return BingSearchClient(
        api_key=settings.bing_search_api_key,
        endpoint=settings.bing_search_endpoint,
        market=settings.bing_search_market,
        timeout_seconds=settings.search_timeout_seconds,
    )
```

​        这个函数很短，但它把“配置如何进入供应商客户端”的路径固定下来。以后如果要在测试里传入假的搜索客户端，可以绕开这个构造函数；如果要在生产里替换 endpoint 或 market，也只需要改环境变量。工具层不需要到处读取配置，这样职责边界更干净。

### 20.6.6 注册 search_web 工具
​        搜索客户端准备好以后，下一步是把它注册成 Agent 可以调用的工具。`api/app/infrastructure/agent_tools/search.py` 中的 `register_search_tools()` 接收一个 `ToolRegistry`，再注册名为 `search_web` 的 `AgentTool`。

```Python
def register_search_tools(
    registry: ToolRegistry,
    client: BingSearchClient | None = None,
) -> None:
    search_client = client or build_bing_search_client()

    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="search_web",
                description="搜索互联网公开网页，返回标题、链接和摘要。",
                parameters=[
                    ToolParameter(
                        name="query",
                        type="string",
                        description="搜索关键词或问题。",
                    ),
                    ToolParameter(
                        name="count",
                        type="integer",
                        description="返回结果数量。",
                        required=False,
                    ),
                ],
            ),
            handler=lambda query, count=5: _format_search_response(
                search_client.search(
                    query=str(query),
                    count=_normalize_count(count),
                )
            ),
        )
    )
```

​        这里有两个设计点。第一，`client` 支持外部传入，这让测试或未来多供应商切换更容易，不必在函数内部强行绑定真实 Bing 客户端。第二，handler 不直接返回 `SearchResponse` 对象，而是调用 `_format_search_response()` 转成 JSON 字符串。当前事件模型会把工具输出保存为文本，所以工具输出必须能作为字符串进入 `tool_called.payload.output`。
​        `_normalize_count()` 会把工具参数中的 `count` 转成整数，并限制在配置允许的范围内。这个函数不是为了掩盖错误，而是因为工具参数来自模型或用户任务，可能是字符串、空值或数字。这里选择把非法数量归一到默认值，是为了让搜索工具对自然语言任务更稳。真正必须失败的情况是空查询词，这个错误已经在适配器里明确抛出。

### 20.6.7 格式化搜索结果输出
​        `_format_search_response()` 是后端和前端之间的结构约定。它把 `SearchResponse` 转成包含 `kind` 字段的 JSON 字符串。

```Python
def _format_search_response(data: SearchResponse) -> str:
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
```

​        `kind` 是整个设计里最关键的字段。第 19 章的工具预览面板已经可以解析浏览器截图，因为截图输出里有 `kind="browser_screenshot"`。本章延续同样的做法，搜索输出使用 `kind="search_results"`。前端不需要猜工具名称，也不需要解析自然语言，只要 JSON 能解析且 `kind` 匹配，就按搜索结果卡片展示。
​        `ensure_ascii=False` 保证中文标题和摘要不会变成 Unicode 转义。搜索结果本来就是给用户看的，如果输出里全是 `\u4e2d\u6587` 这种转义形式，事件可读性会下降。这里让 JSON 字符串保持中文可读，也方便日志和调试。

### 20.6.8 加入内置工具注册表
​        搜索工具写完以后，还必须进入内置工具注册表。`build_builtin_tool_registry()` 是 ReAct 执行时拿到工具集合的地方，如果这里没有调用 `register_search_tools(registry)`，后面的触发规则即使判断需要搜索，也拿不到 `search_web`。

```Python
def build_builtin_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(summarize_text)
    registry.register(extract_keywords)
    registry.register(draft_plan)
    register_sandbox_file_tools(registry)
    register_sandbox_shell_tools(registry)
    register_sandbox_browser_tools(registry)
    register_search_tools(registry)
    return registry
```

​        这一步也说明了本项目的工具接入方式。每类工具可以在自己的模块里注册一组能力，最后由内置注册表统一汇总。这样工具数量变多以后，`builtin.py` 仍然只负责组装，而不是把所有工具定义都堆在一个文件里。

### 20.6.9 让 ReAct 执行时选择搜索工具
​        工具注册只是让 `search_web` 存在，真正调用它的是 `ReActAgentService`。本章在 `_call_tool_for_step()` 中增加搜索判断，并且把搜索判断放在浏览器判断之前。

```Python
if self._needs_search(text):
    tool = self.registry.get("search_web")
    arguments = {"query": self._extract_search_query(text), "count": 5}
elif self._needs_browser_screenshot(text):
    ...
```

​        搜索判断放在前面，是因为很多任务会同时出现“网页”“资料”“最新”等词。如果先走浏览器判断，系统可能打开一个默认网页，却没有真正查资料。本章的规则还不是最终形态，它只是用关键词让教学项目先拥有可验证的搜索路径。后续接入更完整的模型工具选择后，这种关键词判断会逐步退到兜底位置。
​        `_needs_search()` 使用一组中文关键词识别搜索意图：

```Python
keywords = ["搜索", "检索", "查找", "查询", "资料", "新闻", "最新"]
return any(keyword in text for keyword in keywords)
```

​        `_extract_search_query()` 会从计划文本中去掉常见动作词，保留更接近搜索关键词的内容。当前计划步骤还不是严格的工具参数结构，所以这一步先用简单规则处理。它会把文本压缩到 120 个字符以内，避免把整段计划说明都塞进搜索引擎。

```Python
clean_text = " ".join(text.split())
for keyword in ["搜索", "检索", "查找", "查询", "一下", "资料"]:
    clean_text = clean_text.replace(keyword, " ")
return " ".join(clean_text.split())[:120] or text[:120]
```

​        到这里，后端执行链路已经完整了。用户任务被规划成步骤，步骤文本被 ReAct 读取，ReAct 判断需要搜索，拿到 `search_web` 工具，传入 `query` 和 `count`，工具返回 JSON 字符串，最后统一写成 `tool_called` 事件。

### 20.6.10 前端解析搜索结果
​        第 19 章已经有 `ToolPreviewPanel`，本章在它里面增加搜索结果类型和解析函数。搜索结果的前端类型与后端 JSON 对齐。

```TypeScript
type SearchResultsPayload = {
  kind: "search_results";
  provider: string;
  query: string;
  items: Array<{
    title: string;
    url: string;
    snippet: string;
  }>;
};
```

​        `parseSearchResults()` 会尝试把工具输出解析成 JSON。只有当 `kind` 等于 `search_results`，并且 `provider`、`query`、`items` 的基本形状正确时，函数才返回结构化结果。其他工具输出继续走普通文本展示。

```TypeScript
function parseSearchResults(value: string): SearchResultsPayload | null {
  try {
    const payload = JSON.parse(value) as Partial<SearchResultsPayload>;
    if (
      payload.kind === "search_results" &&
      typeof payload.provider === "string" &&
      typeof payload.query === "string" &&
      Array.isArray(payload.items)
    ) {
      return {
        kind: "search_results",
        provider: payload.provider,
        query: payload.query,
        items: payload.items.map((item) => ({
          title: getString(item.title),
          url: getString(item.url),
          snippet: getString(item.snippet),
        })),
      };
    }
  } catch {
    return null;
  }
  return null;
}
```

​        这个函数里的 `catch` 不是为了隐藏错误，而是因为工具预览面板会处理多种工具输出。Shell 输出、文件读取输出、普通摘要输出本来就不是 JSON，它们不能因为解析失败就让整个面板报错。解析失败返回 `null`，意思是“这不是搜索结果”，而不是“搜索失败”。真正的搜索失败会在后端工具输出或事件错误里体现。

### 20.6.11 展示搜索结果卡片
​        搜索结果解析成功后，`ToolCallDetail` 会把输出交给 `SearchResultsPreview`。这样最近一次搜索调用不再显示成一大段 JSON，而是显示成带链接的网页条目。

```TypeScript
{screenshot ? (
  <ScreenshotPreview screenshot={screenshot} />
) : searchResults ? (
  <SearchResultsPreview results={searchResults} />
) : (
  <pre>{output || "<no output>"}</pre>
)}
```

​        搜索结果组件先展示查询词和供应商，再逐条渲染标题、URL 和摘要。每条结果都是一个新窗口打开的链接，并带有 `rel="noreferrer"`。这样用户可以直接从工具预览面板进入网页来源，检查 Agent 看到的资料是否可靠。

```TypeScript
function SearchResultsPreview({ results }: { results: SearchResultsPayload }) {
  return (
    <div className="mt-3 rounded-md border border-slate-200 bg-white">
      <div className="border-b border-slate-200 px-3 py-2">
        <div className="text-xs font-medium text-slate-500">搜索结果</div>
        <div className="mt-1 text-sm font-semibold text-slate-950">
          {results.query}
        </div>
        <div className="mt-1 text-xs text-slate-500">
          provider: {results.provider}
        </div>
      </div>
      <div className="grid gap-2 p-3">
        {results.items.map((item) => (
          <a href={item.url} key={`${item.title}-${item.url}`} target="_blank">
            <div>{item.title || item.url}</div>
            <div>{item.url}</div>
            <p>{item.snippet || "暂无摘要"}</p>
          </a>
        ))}
      </div>
    </div>
  );
}
```

​        为了让工具列表里的图标也能区分搜索调用，`getToolIcon()` 会在发现 `searchResults` 或工具名以 `search_` 开头时返回搜索图标。这样用户即使只看最近工具调用列表，也能快速辨认这一步是搜索，而不是浏览器、Shell 或文件工具。

## 20.7 关键理解
​        本章最重要的理解，是搜索能力不应该被做成一个独立接口演示，而应该进入 Agent 工具体系。只要它进入工具体系，搜索就会天然拥有工具定义、参数、输出、事件和前端预览。后续无论模型怎样选择工具，搜索结果都能被同一套观察机制捕获。
​        第二个关键点是供应商隔离。Bing 的原始 JSON 不应该扩散到工具层和前端层。工具层只关心 `SearchResponse`，前端只关心 `kind=search_results`。这种隔离让项目可以在保持业务结构稳定的前提下替换底层供应商。Agent 产品做得越久，越会遇到供应商变更、配额限制、私有化部署和内网检索等问题，早一点把边界划清楚，会减少后续重构成本。
​        第三个关键点是可观察性。搜索结果不是模型内部想法，它是工具调用产生的外部资料。它应该被保存进事件流，也应该展示给用户看。用户能够看到搜索词、供应商、标题、链接和摘要，才有可能判断 Agent 的回答是不是建立在合理资料上。这个设计也为后面的引用体系、最终回答来源标注和任务回放打下基础。

## 20.8 技术难点与亮点
​        本章的难点不在于调用 Bing API，而在于把外部搜索放进已有架构时不破坏边界。最容易写坏的方式，是在 `ReActAgentService` 里直接发 HTTP 请求，然后把返回字符串塞进事件。这样短期能跑，但工具注册表、工具协议、前端预览和未来多供应商扩展都会被绕开。本章没有这么做，而是让 Bing 只出现在基础设施层，让 `search_web` 作为工具暴露给 Agent。
​        第二个难点是输出结构。工具协议当前保存的是字符串，如果直接返回自然语言，前端无法稳定渲染；如果直接返回复杂对象，事件序列化又会变得不统一。本章选择“字符串外壳 + JSON 内核”的方案。对事件系统来说，它仍然是文本；对前端工具预览来说，它又可以被解析成结构化数据。这个方案与浏览器截图输出保持一致，后续接入更多富媒体工具时也能沿用。
​        第三个亮点是教学环境下的显式配置提示。没有 Bing Key 时，搜索适配器返回 `bing-disabled` 的提示结果，而不是吞掉错误或返回空列表。这样用户能清楚知道功能没有真实访问外部搜索服务，同时仍然能看到完整的工具调用事件和前端展示效果。对于实战教程来说，这比“没有 Key 就整章无法验证”更友好，也比“静默返回空结果”更透明。

## 20.9 面试考点
​        如果面试官问“为什么要定义 `SearchResult` 和 `SearchResponse`，而不是直接使用 Bing JSON”，可以回答：这是为了隔离供应商结构。业务层只需要标题、链接、摘要、查询词和供应商名称，Bing 的原始字段属于基础设施细节。隔离以后，替换搜索供应商时不需要改 Agent 工具协议和前端展示。
​        如果被问到“为什么 SearchTool 输出 JSON 字符串”，重点要说明当前工具事件模型把输出当作文本保存，所以工具层需要返回字符串；但前端又需要结构化展示搜索结果，因此字符串内容采用 JSON，并用 `kind=search_results` 作为类型标识。这是一种兼容现有事件模型的结构化输出方式。
​        如果被问到“为什么搜索判断放在浏览器判断之前”，可以说搜索任务经常包含网页、资料、最新等词，如果先判断浏览器打开，很可能把需要检索的任务误分配给 `browser_open`。当前关键词规则只是教学阶段的工具选择策略，后续可以被模型结构化工具选择替代，但在这一章需要先让搜索链路稳定可验证。
​        如果被问到“没有配置 API Key 时为什么不直接报错”，要强调这里返回的是明确的禁用提示结果，`provider` 也标记为 `bing-disabled`，并没有把它伪装成真实搜索。这样既暴露配置缺失，也能在没有外部凭据的开发环境中验证工具事件和 UI 渲染链路。

## 20.10 运行验证
​        本章验证时不要只看后端函数是否能调用，还要看完整链路。搜索能力真正完成，应该同时满足配置可读、工具可注册、ReAct 会选择、事件会写入、前端能解析展示这几个条件。

### 20.10.1 检查配置字段
​        先确认后端配置里已经包含搜索字段：

```PowerShell
rg -n "bing_search|search_" api/app/core/config.py
```

​        输出中应该能看到 `bing_search_api_key`、`bing_search_endpoint`、`bing_search_market`、`search_timeout_seconds` 和 `search_max_results`。接着检查 `.env.example` 和 Compose 环境变量，确认容器启动时也能拿到同样的配置名。

### 20.10.2 检查工具注册
​        再确认搜索工具已经接入内置注册表：

```PowerShell
rg -n "register_search_tools|search_web" api/app/infrastructure/agent_tools api/app/application/react_agent_service.py
```

​        这里应该能看到 `register_search_tools(registry)`、`name="search_web"`，以及 `ReActAgentService` 里通过 `self.registry.get("search_web")` 取工具的代码。少了任何一处，搜索工具都可能处在“代码存在但执行链路不通”的状态。

### 20.10.3 启动服务
​        配置确认以后，启动整套服务：

```PowerShell
docker compose up --build
```

​        如果已经有旧容器在运行，并且刚刚修改了环境变量，需要重新创建 API 容器，确保新的搜索配置进入进程。搜索 Key 属于运行时配置，改 `.env` 后不重建容器，旧进程通常不会自动感知。

### 20.10.4 查看工具列表
​        后端运行后，可以通过已有 Agent Core 接口检查工具列表。页面侧也可以通过一次任务执行观察 `tool_called` 事件。关键是确认工具名为：

```Plain
search_web
```

​        如果工具列表里没有这个名字，问题一般在 `build_builtin_tool_registry()`；如果工具存在但任务没有调用它，问题一般在 `_needs_search()` 或计划步骤文本没有包含搜索意图。

### 20.10.5 创建搜索任务
​        在前端新建会话，然后发送一个明确包含搜索意图的任务，例如：

```Plain
搜索一下 Playwright 最新版本的发布说明，并总结主要变化。
```

​        执行后，事件流中应该出现 `tool_called`，payload 里应该能看到 `tool_name` 为 `search_web`，arguments 中包含 `query` 和 `count`，output 中包含 `kind=search_results`。如果没有配置 Bing Key，output 里会出现 `bing-disabled` 和“尚未配置 Bing API Key”的提示结果。

### 20.10.6 页面验证
​        最后看右侧工具预览面板。工具页签中最近一次工具调用应该显示搜索图标，详情区域应该展示搜索词、provider、结果标题、链接和摘要。点击链接时会在新窗口打开网页。这个验证能证明后端工具输出和前端解析约定是一致的。
​        如果页面只显示一段 JSON 文本，说明 `parseSearchResults()` 没有识别输出结构，需要检查 `kind` 是否为 `search_results`。如果页面完全没有工具调用，说明问题更靠前，应该回到 ReAct 执行和事件写入链路排查。

## 20.11 本章小结
​        本章把网页搜索接入了 Agent 工具体系。后端新增了搜索配置、领域模型、Bing 适配器和 `search_web` 工具注册；执行层让 ReAct 在识别搜索意图时调用工具；前端则在工具预览面板里解析 `kind=search_results`，并把结果展示为可点击的网页卡片。
​        这章的重点不是 Bing 本身，而是搜索能力的工程化边界。供应商响应被限制在基础设施层，工具层返回项目自己的稳定结构，事件层记录可观察输出，前端按 `kind` 渲染不同工具结果。这个模式会在后面的 MCP、A2A、多 Agent 协作和最终引用体系中反复出现。

## 20.12 代码索引
​        本章对应源码集中在 `atlas-agents-30` 目录下。阅读时可以先看 `api/app/domain/search/entities.py`，理解搜索结果在项目内部的最小形态；再看 `api/app/infrastructure/search/bing.py`，理解供应商适配层如何把 Bing 响应转换成领域对象；然后看 `api/app/infrastructure/agent_tools/search.py` 和 `api/app/application/react_agent_service.py`，理解搜索能力如何成为 Agent 工具并被执行；最后看 `ui/app/components/tool-preview-panel.tsx`，理解前端如何把搜索输出从普通 JSON 变成可读的搜索结果卡片。

---

[← 第十九章. VNC 远程桌面与工具预览](19-VNC%20远程桌面与工具预览.md) · [返回目录](../README.md) · [第二十一章. MCP 协议与工具接入 →](21-MCP%20协议与工具接入.md)
