# 第三十二章. MCP 工具入列

## 32.1 本章目标
​        第 31 章用确定性接口讲清了 MCP 的角色和流程，但它仍然停留在概念演示层。真正把 MCP 放进 Agent 工作台时，系统要面对的就不只是 Host、Client、Server 这几个名词，而是配置从哪里来、连接怎么创建、工具怎样发现、调用结果如何进入事件流、前端又如何展示这些外部能力。本章的目标，就是把 MCP 从“可以解释”推进到“可以接入”。
​        本章会新增 MCP 配置文件、配置加载器、领域对象、Client 管理器、应用服务、HTTP 接口、`mcp_call` AgentTool 和前端 MCP 面板。完成以后，后端可以读取 `api/config/mcp.yaml`，列出已配置 Server，发现 `demo` Server 暴露的工具，并通过 `/api/mcp/call` 调用工具。Agent 执行计划时，如果任务里出现 MCP 或外部系统相关意图，也可以通过 `mcp_call` 走同一套 `tool_called` 事件链路。
​        这一章仍然保持谨慎的实现边界。`demo` transport 是完整可运行的演示通道；`streamable_http` 和 `stdio` 实现最小 JSON-RPC 的 `tools/list` 与 `tools/call`；`sse` 则明确返回 501，说明它需要长连接会话管理，当前章不假装已经支持完整生命周期。读者要看到的不只是“能调工具”，还要看到一个工程项目在扩展协议能力时怎样把边界写清楚。

## 32.2 最终效果
​        本章结束后，后端会在第 31 章入门接口之外新增三组真实接入接口：

```Plain
GET  /api/mcp/servers
GET  /api/mcp/tools
POST /api/mcp/call
```

​        调用 Server 列表接口时，可以看到配置文件里的 `demo`、`example_stdio` 和 `example_http`。其中 `demo` 默认启用，另外两个只是示例配置，默认关闭。调用工具发现接口时，系统会读取所有已启用 Server，并返回它们暴露的工具。默认情况下，`demo` Server 会返回：

```Plain
demo.mcp_echo
demo.mcp_add_note
```

​        调用工具接口时，可以传入 Server 名称、工具名称和参数：

```Bash
curl -X POST http://localhost:8088/api/mcp/call \
  -H "Content-Type: application/json" \
  -d '{"server_name":"demo","tool_name":"mcp_echo","arguments":{"text":"hello mcp"}}'
```

​        响应会返回 `server_name`、`tool_name`、`arguments` 和 `content`。当 Agent 通过 `mcp_call` 调用工具时，工具输出会被格式化成：

```JSON
{
  "kind": "mcp_tool_result",
  "server_name": "demo",
  "tool_name": "mcp_echo",
  "arguments": {
    "text": "hello mcp"
  },
  "content": [
    {
      "type": "text",
      "text": "echo: hello mcp"
    }
  ]
}
```

​        前端右侧工具预览面板也会发生变化。环境页签里新增 MCP 工具面板，用来展示已配置 Server 和已发现工具；工具页签里如果发现 `kind=mcp_tool_result`，会把输出渲染成 MCP 工具结果卡片，显示 `server.tool`、调用参数和返回内容。这样 MCP 不只是一个后端接口，也进入了工作台的可观察体验。

## 32.3 本章要解决的问题
​        第 31 章已经说明，MCP Host 负责承载 AI 应用，MCP Client 负责连接某个 Server，MCP Server 负责暴露 tools、resources 和 prompts。但在真实项目里，理解角色还不够。一个 Agent 产品必须回答更细的问题：Server 配置是否可以调整，传输方式是否可以扩展，工具发现是否能跨多个 Server，调用失败能否清楚暴露，工具结果是否能进入当前事件流，前端是否能看到外部工具状态。
​        如果这些问题不处理，MCP 接入很容易退化成一个临时接口。比如把 `demo` 工具直接写在路由里，短期能跑；但一旦要接 stdio Server 或 HTTP Server，就会继续复制代码。再比如后端能调用工具，但没有把结果包装成 `tool_called` 输出，用户在工作台里就看不到 Agent 到底调用了什么。又比如前端只展示调用结果，不展示已配置 Server 和工具列表，排查时就不知道问题发生在配置、发现还是调用阶段。
​        因此，本章要做一条完整闭环：配置声明 MCP Server，后端读取并校验配置，Client 管理器按 transport 创建连接对象，应用服务暴露 Server、工具和调用能力，API 路由把能力开放给前端和调试命令，AgentTool 把 MCP 调用放进工具注册表，前端再把 MCP 状态和结果放进工具预览面板。只有这条链路都打通，MCP 才算真正进入项目。

## 32.4 本章技术方案
​        本章的技术方案分成后端接入线和前端观察线。后端接入线从 `api/config/mcp.yaml` 开始，经过 `McpConfig`、`McpClientManager`、`McpService`、API 路由和 `mcp_call` AgentTool；前端观察线从 `/api/mcp/servers` 与 `/api/mcp/tools` 开始，经过 `mcp-api.ts`、页面状态、`ChatWorkspace`、`ToolPreviewPanel` 和 `McpPanel`，最终展示到右侧工作台。
​        后端不会让路由直接读 YAML，也不会让 AgentTool 直接创建 HTTP 请求。配置加载、传输实现、应用语义和工具注册各有位置。`mcp_config.py` 只负责读取和校验配置；`infrastructure/mcp/client.py` 只负责不同 transport 的连接和 JSON-RPC 消息；`McpService` 只负责向上提供 list servers、list tools、call tool 三个应用能力；`agent_tools/mcp.py` 只负责把 MCP 调用封装成当前 Agent 工具协议能理解的 `mcp_call`。
​        前端也不让 MCP 面板自己到处请求接口。页面层 `page.tsx` 负责加载 MCP Server 和工具状态，`ChatWorkspace` 负责把状态和刷新回调传给右侧工作区，`ToolPreviewPanel` 负责把 MCP 面板放进环境页签，并解析工具调用结果。这样 MCP 的前端展示保持在第 29 章建立的工具预览体系中，不会变成一个孤立的新卡片。

## 32.5 新增和修改的文件
​        本章涉及的文件比较多，但可以按职责分组阅读。配置入口包括：

```Plain
.env.example
docker-compose.yml
api/config/mcp.yaml
api/app/core/config.py
api/app/core/mcp_config.py
```

​        后端 MCP 接入包括：

```Plain
api/app/domain/mcp/__init__.py
api/app/domain/mcp/entities.py
api/app/infrastructure/mcp/__init__.py
api/app/infrastructure/mcp/client.py
api/app/application/mcp_service.py
api/app/schemas/mcp.py
api/app/api/routes/mcp.py
```

​        Agent 工具接入包括：

```Plain
api/app/infrastructure/agent_tools/mcp.py
api/app/infrastructure/agent_tools/builtin.py
api/app/application/react_agent_service.py
```

​        前端展示包括：

```Plain
ui/app/types.ts
ui/app/lib/mcp-api.ts
ui/app/components/mcp-panel.tsx
ui/app/components/tool-preview-panel.tsx
ui/app/components/chat-workspace.tsx
ui/app/page.tsx
```

​        文档说明包括 `README.md`、`api/README.md` 和 `docs/course/chapters/32-mcp-tools.md`。读者读代码时不要被文件数量吓住，本章的核心路径其实只有一条：配置 Server，发现工具，调用工具，注册 AgentTool，展示结果。

## 32.6 实施步骤
​        实施时要从配置文件开始。MCP Server 是外部能力来源，不能继续写死在 Python 函数里。配置文件定义 Server 名称、是否启用、传输方式、命令或 URL，后端再按配置创建对应 Client。这样后续新增外部 Server 时，主项目不用改大量业务代码。

### 32.6.1 配置 MCP Server
​        本章新增 `api/config/mcp.yaml`。它先定义全局 MCP 开关和默认 Server，然后定义多个 Server。

```Yaml
mcp:
  enabled: true
  default_server: demo

servers:
  demo:
    enabled: true
    transport: demo
    description: "内置 MCP 演示 Server，用于第 32 章验证工具发现和调用链路。"

  example_stdio:
    enabled: false
    transport: stdio
    command: "python"
    args:
      - "-m"
      - "your_mcp_server"
    description: "stdio MCP Server 配置示例。启用前需要替换成真实命令。"

  example_http:
    enabled: false
    transport: streamable_http
    url: "http://localhost:8765/mcp"
    description: "Streamable HTTP MCP Server 配置示例。启用前需要替换成真实地址。"
```

​        `demo` 是本章默认启用的内置 Server。它不依赖外部进程，适合验证整个链路。`example_stdio` 和 `example_http` 默认关闭，是为了给读者展示真实 Server 配置形态，但不让一个未替换的示例命令影响本地启动。这个设计很重要：示例配置可以存在，但不能在默认状态下制造失败。
​        `.env.example` 和 Compose 中新增 `MCP_CONFIG_PATH`，默认指向 `config/mcp.yaml`。这样本地开发和容器运行都能读取同一份配置路径。后续私有化部署时，也可以通过环境变量把配置文件换成挂载目录里的版本。

### 32.6.2 读取并校验 MCP 配置
​        `api/app/core/config.py` 先增加 `mcp_config_path`，然后由 `api/app/core/mcp_config.py` 负责读取 YAML。配置模型分成 `McpServerConfig`、`McpDefaults` 和 `McpConfig`。

```Python
McpTransport = Literal["demo", "stdio", "sse", "streamable_http"]


class McpServerConfig(BaseModel):
    enabled: bool = True
    transport: McpTransport
    description: str = ""
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    url: str | None = None
    timeout_seconds: float = Field(default=10.0, gt=0)
```

​        `transport` 决定这个 Server 用哪种方式通信。`demo` 不需要额外字段，`stdio` 需要 `command`，`streamable_http` 和 `sse` 需要 `url`。这些规则在 `validate_transport_fields()` 中显式校验。

```Python
@model_validator(mode="after")
def validate_transport_fields(self) -> "McpServerConfig":
    if self.transport == "stdio" and not self.command:
        raise ValueError("stdio MCP server requires command")
    if self.transport in {"sse", "streamable_http"} and not self.url:
        raise ValueError(f"{self.transport} MCP server requires url")
    return self
```

​        配置文件不存在时，`load_mcp_config()` 会抛出 `AppException`；默认 Server 没有定义时也会抛错。这里不做隐式补齐，因为 MCP 配置属于系统边界，一旦错了就应该让启动或接口调用清楚失败。配置错误被显式暴露，比后面工具发现时返回空列表更容易排查。

### 32.6.3 定义 MCP 领域对象
​        本章新增 `api/app/domain/mcp/entities.py`，用三个 dataclass 表示项目内部的 MCP 概念。

```Python
@dataclass(slots=True)
class McpServerInfo:
    name: str
    enabled: bool
    transport: str
    description: str


@dataclass(slots=True)
class McpTool:
    server_name: str
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(slots=True)
class McpToolResult:
    server_name: str
    tool_name: str
    arguments: dict[str, Any]
    content: list[dict[str, Any]]
```

​        `McpServerInfo` 面向展示和排查，它告诉前端有哪些 Server、是否启用、用什么传输。`McpTool` 表示从 Server 发现到的一项工具能力，除了工具名，还要保留来自哪个 Server。这个字段很关键，因为不同 Server 可能暴露同名工具。`McpToolResult` 统一承载调用结果，后续无论来自 demo、stdio 还是 HTTP，都要压成这个结构再往上返回。

### 32.6.4 编写 McpService
​        `McpService` 是应用层服务。它不关心底层是 HTTP、stdio 还是 demo，只依赖 `McpClientManager` 暴露的统一方法。

```Python
class McpService:
    def __init__(self, manager: McpClientManager | None = None) -> None:
        self.manager = manager or build_mcp_client_manager()

    def list_servers(self) -> list[McpServerInfo]:
        return self.manager.list_servers()

    def list_tools(self, server_name: str | None = None) -> list[McpTool]:
        return self.manager.list_tools(server_name=server_name)

    def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> McpToolResult:
        return self.manager.call_tool(
            server_name=server_name,
            tool_name=tool_name,
            arguments=arguments,
        )
```

​        这一层看起来很薄，但它是必要的边界。路由层不应该直接依赖基础设施 Client，AgentTool 也不应该知道怎么构造 transport。应用层把“列出 Server、发现工具、调用工具”定义成业务能力，基础设施层只负责执行这些能力。

### 32.6.5 抽象传输层 Client
​        `McpTransportClient` 是所有传输实现的基类。它只要求两个方法：`list_tools()` 和 `call_tool()`。

```Python
class McpTransportClient(ABC):
    def __init__(self, server_name: str, config: McpServerConfig) -> None:
        self.server_name = server_name
        self.config = config

    @abstractmethod
    def list_tools(self) -> list[McpTool]:
        pass

    @abstractmethod
    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> McpToolResult:
        pass
```

​        抽象层的价值，是让 `McpClientManager` 和 `McpService` 不关心具体传输。demo、stdio、streamable_http 和 sse 都可以被当成同一种 Client 使用。上层只知道“我要发现工具”和“我要调用工具”，不需要知道底层是启动进程、发 HTTP 请求，还是本地返回演示数据。

### 32.6.6 实现 DemoMcpTransportClient
​        `DemoMcpTransportClient` 是本章最重要的可运行通道。它模拟真实 MCP Server 的 `tools/list` 和 `tools/call`，但不需要外部进程。

```Python
class DemoMcpTransportClient(McpTransportClient):
    def list_tools(self) -> list[McpTool]:
        return [
            McpTool(
                server_name=self.server_name,
                name="mcp_echo",
                description="返回调用方传入的文本。",
                input_schema={...},
            ),
            McpTool(
                server_name=self.server_name,
                name="mcp_add_note",
                description="模拟创建一条外部笔记。",
                input_schema={...},
            ),
        ]
```

​        调用时，它先检查工具名是否存在。不存在就返回 `MCP tool not found`，不会替换成默认工具。`mcp_echo` 要求 `text` 参数，`mcp_add_note` 要求 `title` 和 `content`。参数缺失时都会抛出 `AppException`。
​        这个 demo 不是“假装真实连接”，而是本章的内置 Server。它明确使用 `transport: demo`，前端也会显示它的 transport。读者可以用它验证配置、工具发现、工具调用、AgentTool、事件和 UI 结果，等链路跑通以后再启用真实 stdio 或 HTTP Server。

### 32.6.7 实现 Streamable HTTP 最小客户端
​        `StreamableHttpMcpTransportClient` 使用 HTTP POST 发送 JSON-RPC 请求。本章先实现两个核心方法：`tools/list` 和 `tools/call`。

```Python
def list_tools(self) -> list[McpTool]:
    result = self._send_json_rpc("tools/list", {})
    tools = result.get("tools", [])
    return [
        McpTool(
            server_name=self.server_name,
            name=str(tool.get("name") or ""),
            description=str(tool.get("description") or ""),
            input_schema=dict(tool.get("inputSchema") or {}),
        )
        for tool in tools
    ]
```

​        `_send_json_rpc()` 会构造 JSON-RPC 2.0 请求体，带上递增 id、method 和 params，然后向配置里的 URL 发起 POST。HTTP 请求失败会转换成 `MCP HTTP request failed`，JSON-RPC 返回 error 时会转换成 `MCP JSON-RPC error`。
​        这不是完整生产级 MCP HTTP 客户端。真实 Server 可能涉及初始化、会话、通知和更多生命周期细节。本章先把最关键的工具发现和调用落到项目结构里，确保后续有扩展点，而不是一次性把所有协议细节都压进教学章节。

### 32.6.8 实现 stdio 最小客户端
​        `StdioMcpTransportClient` 通过启动命令、写入一行 JSON-RPC 请求、读取一行响应来模拟 stdio MCP 调用。

```Python
command = [self.config.command, *self.config.args]
completed = subprocess.run(
    command,
    input=json.dumps(request_body, ensure_ascii=False) + "\n",
    capture_output=True,
    check=False,
    encoding="utf-8",
    timeout=self.config.timeout_seconds,
)
```

​        这种实现适合课程理解协议，不适合长连接生产场景。真正的 stdio MCP Client 通常需要长期维护子进程、初始化握手、并处理多条消息。本章刻意写成“每次调用启动一次命令”的最小模型，是为了让读者先看懂 JSON-RPC 输入和输出的关系。
​        命令缺失、启动失败、超时、进程返回非零状态、JSON-RPC error，都会以明确异常返回。这里同样不做静默失败。MCP 是外部能力接入边界，失败原因必须尽早暴露，否则前端只看到“没有工具”时无法判断是命令没配、进程崩了，还是 Server 返回了协议错误。

### 32.6.9 明确 SSE transport 边界
​        代码里也定义了 `SseMcpTransportClient`，但它没有假装实现完整 SSE。它继承自 HTTP 客户端，并重写 `_send_json_rpc()`，直接返回 501。

```Python
raise AppException(
    message="MCP SSE transport requires long-lived session management; use streamable_http or demo in this chapter.",
    code=501,
    status_code=501,
)
```

​        这一步很符合工程实践。早期 SSE 传输需要长连接会话管理和消息端点配合，如果当前章没有实现，就应该明确告诉用户，而不是返回一个看似成功的空结果。对教程来说，这也是一个重要示范：边界可以有限，但必须诚实。

### 32.6.10 编写 McpClientManager
​        `McpClientManager` 读取配置，并按 Server 名称创建对应 transport。它对外提供 `list_servers()`、`list_tools()` 和 `call_tool()`。

```Python
class McpClientManager:
    def __init__(self) -> None:
        self.config = load_mcp_config()

    def list_servers(self) -> list[McpServerInfo]:
        return [
            McpServerInfo(
                name=name,
                enabled=server.enabled,
                transport=server.transport,
                description=server.description,
            )
            for name, server in self.config.servers.items()
        ]
```

​        `list_tools()` 如果传入 `server_name`，就只读取指定 Server；如果没有传入，就读取所有启用的 Server。每个 Server 先经过 `_get_enabled_server()` 校验，确保不存在和未启用这两类错误都能明确返回。然后 `_build_transport()` 根据配置创建具体 Client。

```Python
if server.transport == "demo":
    return DemoMcpTransportClient(server_name, server)
if server.transport == "stdio":
    return StdioMcpTransportClient(server_name, server)
if server.transport == "streamable_http":
    return StreamableHttpMcpTransportClient(server_name, server)
if server.transport == "sse":
    return SseMcpTransportClient(server_name, server)
```

​        这就是本章后端的核心分发点。未来增加新的 transport 或更完整的连接池时，优先改这里，而不是让路由、应用服务和 AgentTool 分别判断 transport。管理器把“按配置找到正确 Client”这件事集中起来，系统边界会更清楚。

### 32.6.11 扩展 MCP API Schema 和路由
​        第 31 章已经有 MCP 概念和 demo 接口。本章继续在 `schemas/mcp.py` 中增加真实接入相关响应。

```Python
class McpServerResponse(BaseModel):
    name: str
    enabled: bool
    transport: str
    description: str


class McpDiscoveredToolResponse(BaseModel):
    server_name: str
    name: str
    description: str
    input_schema: dict[str, Any]


class McpToolInvokeRequest(BaseModel):
    server_name: str = Field(min_length=1, max_length=100)
    tool_name: str = Field(min_length=1, max_length=100)
    arguments: dict[str, Any] = Field(default_factory=dict)
```

​        路由层新增 `/servers`、`/tools` 和 `/call`。`/servers` 返回配置状态，`/tools` 触发工具发现，`/call` 触发工具调用。路由仍然通过转换函数把领域对象转成 API 响应，保持分层一致。

```Python
@router.get("/tools", response_model=ApiResponse[McpDiscoveredToolListResponse])
async def list_mcp_tools(
    server_name: str | None = None,
    service: McpService = Depends(build_mcp_service),
) -> ApiResponse[McpDiscoveredToolListResponse]:
    return ApiResponse(
        data=McpDiscoveredToolListResponse(
            items=[
                to_discovered_tool_response(tool)
                for tool in service.list_tools(server_name=server_name)
            ],
        )
    )
```

​        这组接口让 MCP 能力既能被前端读取，也能被命令行验证。前端不需要知道 YAML 文件位置，也不需要知道 transport 细节，只要请求主 API 即可。

### 32.6.12 注册 mcp_call AgentTool
​        API 接口能调用 MCP 工具以后，还要把 MCP 放进 Agent 执行链路。`api/app/infrastructure/agent_tools/mcp.py` 注册了一个通用工具：`mcp_call`。

```Python
registry.register(
    AgentTool(
        definition=ToolDefinition(
            name="mcp_call",
            description="调用一个已配置 MCP Server 暴露的工具。",
            parameters=[
                ToolParameter(name="server_name", type="string", description="MCP Server 名称，例如 demo。"),
                ToolParameter(name="tool_name", type="string", description="MCP 工具名，例如 mcp_echo。"),
                ToolParameter(name="arguments_json", type="string", description="工具参数 JSON 字符串。", required=False),
            ],
        ),
        handler=lambda server_name, tool_name, arguments_json="{}": _format_mcp_result(
            mcp_service.call_tool(
                server_name=str(server_name),
                tool_name=str(tool_name),
                arguments=_parse_arguments(arguments_json),
            )
        ),
    )
)
```

​        本章先使用一个通用 `mcp_call`，而不是把每个发现到的 MCP 工具都动态展开成独立 AgentTool。原因是当前项目的工具选择还处在教学阶段，动态工具 schema、模型选择和权限控制会在后面增强。先用 `server_name + tool_name + arguments_json` 打通通用入口，更容易验证链路。
​        `_format_mcp_result()` 会把 `McpToolResult` 转成前端可识别的 JSON 字符串，其中 `kind` 固定为 `mcp_tool_result`。这延续了前面浏览器截图和搜索结果的设计：事件层保存字符串，前端通过 `kind` 判断如何渲染。

### 32.6.13 接入内置工具注册表和 ReAct
​        `build_builtin_tool_registry()` 中加入 `register_mcp_tools(registry)`，这样 `mcp_call` 会出现在 Agent 可用工具列表里。随后 `ReActAgentService` 增加 `_needs_mcp()`，当步骤文本包含 `MCP`、`mcp`、`外部工具` 或 `外部系统` 时，选择 `mcp_call`。

```Python
if self._needs_mcp(text):
    tool = self.registry.get("mcp_call")
    arguments = {
        "server_name": "demo",
        "tool_name": "mcp_echo",
        "arguments_json": '{"text":"来自 MCP 工具的演示响应"}',
    }
```

​        这一章的 ReAct 参数仍然是教学型固定参数。它的作用是让用户在前端发一个包含 MCP 意图的任务时，能稳定看到一次 MCP 工具调用事件。后续模型工具选择增强后，`server_name`、`tool_name` 和参数应该由模型根据工具 schema 生成，而不是写死在规则里。现在先把执行链路打通，是合理的阶段性选择。

### 32.6.14 前端读取 MCP Server 和工具
​        前端新增 `ui/app/lib/mcp-api.ts`，封装两个请求：

```TypeScript
export function fetchMcpServers(): Promise<McpServerListData> {
  return requestApi<McpServerListData>("/api/mcp/servers");
}

export function fetchMcpTools(): Promise<McpToolListData> {
  return requestApi<McpToolListData>("/api/mcp/tools");
}
```

​        `types.ts` 中新增 `McpServerItem`、`McpServerListData`、`McpToolItem` 和 `McpToolListData`。页面层 `page.tsx` 在 `loadStatus()` 中同时请求 API、数据库、沙箱、VNC、MCP Server 和 MCP 工具。刷新 MCP 时，只重新请求 Server 和工具列表，不影响会话消息。
​        这种状态管理方式延续了前面 Sandbox 和 VNC 的处理：数据加载留在页面层，展示组件只接收 `LoadState` 和刷新回调。这样 MCP 面板不会自己散落请求逻辑，后续要改接口或错误处理时也更集中。

### 32.6.15 新增 McpPanel
​        `McpPanel` 展示已配置 Server 和已发现工具。它接收 `servers`、`tools` 和 `onRefresh`，内部按 loading、error、ready 三种状态渲染。

```TypeScript
export function McpPanel({ onRefresh, servers, tools }: McpPanelProps) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-base font-semibold text-slate-950">
            <Plug size={17} aria-hidden="true" />
            MCP 工具
          </h2>
          <p className="mt-1 text-sm leading-5 text-slate-500">
            查看已配置 Server 和发现到的外部工具
          </p>
        </div>
      </div>
      <div className="mt-4 grid gap-4">
        <ServerList state={servers} />
        <ToolList state={tools} />
      </div>
    </div>
  );
}
```

​        Server 列表显示名称、transport 和描述；工具列表显示 `server_name.name` 与工具说明。这个面板放在工具预览的环境页签中，和 Sandbox、VNC 一起构成“执行环境观察区”。用户在执行任务前就能看到当前有哪些外部工具可用，执行任务后又能在工具页签看到具体调用结果。

### 32.6.16 渲染 MCP 工具结果
​        `ToolPreviewPanel` 新增 `McpToolResultPayload` 类型和 `parseMcpToolResult()`。只有当工具输出能解析为 JSON，且 `kind` 等于 `mcp_tool_result` 时，前端才把它当成 MCP 工具结果展示。

```TypeScript
type McpToolResultPayload = {
  kind: "mcp_tool_result";
  server_name: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  content: Array<Record<string, unknown>>;
};
```

​        工具详情渲染顺序也相应扩展：先看浏览器截图，再看搜索结果，再看 MCP 结果，最后才回退到普通文本。MCP 结果卡片会展示 `server.tool`、MCP 参数和 MCP 返回内容。工具摘要图标也把 `mcp_` 开头的工具和 `mcp_tool_result` 识别为 Plug 图标。
​        这样做以后，BrowserTool、SearchTool 和 MCP Tool 都遵循同一种前端模式：后端输出 `kind`，前端解析 `kind`，展示对应的结构化视图。工具类型越来越多时，UI 仍然有统一扩展方式。

## 32.7 关键理解
​        本章最重要的理解，是 MCP 接入不是把外部工具接口硬塞进项目，而是把外部工具适配到已有 Agent 工具体系里。配置文件声明 Server，Client 管理器负责连接，应用服务暴露能力，AgentTool 统一执行，事件流记录输出，前端工具预览负责观察。这条链路完整以后，外部工具才真正变成 Agent 的一部分。
​        第二个关键点是 transport 要有清晰边界。`demo` 是本章稳定验证通道，`streamable_http` 和 `stdio` 是最小 JSON-RPC 实现，`sse` 只识别配置并明确返回未支持。有限支持不可怕，假装支持才会制造调试成本。尤其是 MCP 这种跨进程或跨网络协议，一旦错误被吞掉，排查会非常困难。
​        第三个关键点是 `mcp_call` 是阶段性设计。本章先用一个通用工具打通链路，避免过早引入动态工具展开、权限策略和模型工具选择。等后面模型能基于工具 schema 选择工具时，再把 MCP Server 发现到的工具展开成更细粒度的可选项。工程上先闭环，再增强智能选择。
​        第四个关键点是 MCP 工具要同时满足“机器可调用”和“用户可观察”。只让 Agent 能调用外部工具还不够，用户需要知道当前配置了哪些 Server、哪些 Server 被启用、发现到了哪些工具、具体一次调用传入了什么参数、Server 返回了什么 content。否则 MCP 能力会变成后端黑盒，任务失败时只能猜测。第 29 章搭好的工具预览面板在这里发挥了作用，它把环境状态和调用结果分开展示，让用户既能在执行前看可用能力，也能在执行后看调用证据。
​        第五个关键点是配置和运行时行为要保持一致。`api/config/mcp.yaml` 不是写给文档看的，它真实决定了 `/api/mcp/servers`、`/api/mcp/tools` 和 `mcp_call` 的行为。启用一个 Server，就意味着工具发现会尝试连接它；禁用一个 Server，就意味着它不会进入默认工具列表。这个关系越直接，后续部署时越容易把问题定位到配置文件，而不是在代码里到处找硬编码。

## 32.8 技术难点与亮点
​        本章的第一个难点是分层。配置、传输、应用服务、API 路由、AgentTool 和前端展示都参与了 MCP 接入，如果没有清晰边界，很容易出现一个文件知道所有事情的情况。当前实现把每层职责压得比较窄：配置负责声明，Client 负责通信，Service 负责语义，Tool 负责接入 Agent，Panel 负责展示。
​        第二个难点是错误暴露。配置文件缺失、默认 Server 未定义、Server 未启用、工具不存在、stdio 命令缺失、HTTP 请求失败、JSON-RPC error、SSE 未实现，这些都需要明确失败。对于外部工具协议来说，空结果往往比错误更危险，因为它让用户误以为没有工具，而不是配置或连接出了问题。
​        第三个亮点是前后端 `kind` 协议的延续。第 27 章的浏览器截图、第 30 章的搜索结果、本章的 MCP 工具结果，都使用结构化 JSON 字符串承载工具输出。事件模型保持简单，前端又能做富展示。这个模式后续还能支持更多外部工具结果类型。
​        第四个亮点是可验证路径完整。即使没有真实 MCP Server，读者也能用 `demo` transport 完成从配置读取到前端展示的完整验证。这个内置 Server 不隐藏自己的身份，也不模拟生产能力，只为验证链路服务。等链路成立后，再替换成真实 stdio 或 HTTP Server，排查成本会低很多。
​        第五个难点是工具发现的时机。本章的 `/api/mcp/tools` 会主动读取已启用 Server 的工具列表，这意味着前端刷新 MCP 面板时，后端确实会触发工具发现。这个设计能让用户看到当前可用工具的真实状态，但也要求外部 Server 不可用时错误要清楚返回。后续如果 Server 数量变多，可以再考虑缓存、异步刷新或按 Server 分批发现；本章先保持同步路径，目的是让行为和代码更容易对应。
​        第六个亮点是没有把 MCP 接入做成“只给后端调试用”的能力。很多项目在接外部工具时，会先停在 curl 能调用接口的阶段，然后前端和 Agent 执行链路迟迟没有接上。本章直接把 MCP Server 状态、工具发现、AgentTool 输出和工具结果卡片一起打通，读者能在同一个工作台里看到外部能力从配置到调用的完整路径。
​        第七个难点是命名和冲突。MCP 工具来自不同 Server，单独看工具名可能会重复，所以本章所有工具展示和结果输出都保留 `server_name`。前端展示成 `demo.mcp_echo`，后端调用也要求同时传 `server_name` 和 `tool_name`。这个细节看起来小，但它能避免后续多个 Server 都暴露 `search`、`read_file`、`create_issue` 这类常见工具名时产生歧义。

## 32.9 面试考点
​        如果面试官问“为什么 MCP Server 要放到 YAML 配置里”，可以回答：外部工具服务不应该写死在代码里。配置化以后，可以通过启用、禁用、修改 transport、命令或 URL 来接入不同 Server，而不必改 Agent 执行逻辑。配置加载器还可以在边界处校验必填字段，提前暴露错误。
​        如果被问到“为什么要有 McpTransportClient 抽象”，重点说明上层只需要 `list_tools` 和 `call_tool`，不应该关心底层是 demo、stdio 还是 HTTP。传输抽象让应用服务和 AgentTool 保持稳定，新增 transport 时主要改基础设施层和管理器。
​        如果被问到“为什么本章用通用 `mcp_call` 而不是动态注册每个 MCP 工具”，可以回答：当前阶段先验证 MCP 工具调用闭环，通用工具更容易接入已有 ReAct 规则。动态工具展开需要更完整的 schema 转换、权限管理、模型工具选择和冲突处理，适合后续增强。
​        如果被问到“为什么 SSE transport 返回 501”，要强调这是显式边界。SSE 需要长连接会话管理，本章没有实现完整生命周期，所以应该明确告诉调用方当前不支持，而不是返回空结果或假装成功。
​        如果被问到“MCP 结果如何在前端展示”，可以回答：AgentTool 把 `McpToolResult` 格式化成带 `kind=mcp_tool_result` 的 JSON 字符串，事件流保存这个字符串，`ToolPreviewPanel` 解析 `kind` 后渲染 MCP 结果卡片，展示 Server、工具名、参数和 content。

## 32.10 运行验证
​        本章验证要分后端配置、接口、AgentTool 和前端四层进行。只验证 `/api/mcp/call` 成功还不够，因为 MCP 的目标是进入 Agent 工作台。

### 32.10.1 检查配置文件
​        先确认配置路径和 YAML 文件存在：

```PowerShell
rg -n "MCP_CONFIG_PATH|mcp_config_path" .env.example docker-compose.yml api/app/core/config.py
Get-Content api/config/mcp.yaml
```

​        配置里应该能看到 `demo` Server 启用，`example_stdio` 和 `example_http` 关闭。默认 Server 应该是 `demo`。

### 32.10.2 检查后端代码
​        再确认核心类和接口存在：

```PowerShell
rg -n "McpClientManager|McpService|register_mcp_tools|mcp_tool_result" api/app
```

​        输出中应该能看到 Client 管理器、应用服务、AgentTool 注册和结果格式化逻辑。如果 `register_mcp_tools` 没有进入 `builtin.py`，Agent 执行时就找不到 `mcp_call`。

### 32.10.3 启动服务
​        启动项目：

```PowerShell
docker compose up --build
```

​        如果改过 `api/config/mcp.yaml` 或环境变量，需要重启 API 容器。`load_mcp_config()` 使用缓存读取配置，运行中的进程不会自动重新加载文件。

### 32.10.4 验证 Server 列表
​        调用 Server 列表接口：

```Bash
curl http://localhost:8088/api/mcp/servers
```

​        响应中应该能看到 `demo`、`example_stdio` 和 `example_http`，并能看到每个 Server 的 enabled、transport 和 description。这个接口验证的是配置加载和响应转换。

### 32.10.5 验证工具发现
​        调用工具发现接口：

```Bash
curl http://localhost:8088/api/mcp/tools
```

​        默认情况下，响应里应该有 `demo.mcp_echo` 和 `demo.mcp_add_note`。如果这里失败，优先检查 `demo` 是否启用、`transport` 是否为 `demo`、配置路径是否正确。

### 32.10.6 验证工具调用
​        调用 demo 工具：

```Bash
curl -X POST http://localhost:8088/api/mcp/call \
  -H "Content-Type: application/json" \
  -d '{"server_name":"demo","tool_name":"mcp_echo","arguments":{"text":"hello mcp"}}'
```

​        响应中的 content 应该包含 `echo: hello mcp`。再故意传入不存在的工具名，应看到明确的工具不存在错误。这样能证明调用错误没有被吞掉。

### 32.10.7 验证 AgentTool
​        打开 Agent Core 工具列表，确认 `mcp_call` 已经注册：

```Bash
curl http://localhost:8088/api/agent-core/tools
```

​        然后在前端发送包含 MCP 或外部系统字样的任务，例如：

```Plain
请调用 MCP 外部工具做一次演示。
```

​        执行计划后，事件流里应该出现 `tool_called`，工具名为 `mcp_call`，输出中包含 `kind=mcp_tool_result`。

### 32.10.8 验证前端展示
​        打开前端页面，进入右侧工具预览面板的“环境”页签，应该看到 MCP 工具面板。它会列出 Server 和已发现工具。执行包含 MCP 的任务后，工具页签中应该出现 MCP 工具结果卡片，展示 `demo.mcp_echo`、参数和返回 content。

## 32.11 常见问题
### 32.11.1 为什么 demo Server 也放进 MCP 配置
​        因为本章要验证真实接入链路，而不是继续使用第 31 章的概念接口。把 demo Server 放进配置后，它和真实 Server 一样经过配置加载、Client 管理器、应用服务、API 路由和前端展示。这样验证的是同一条接入路径，而不是一个旁路演示函数。

### 32.11.2 为什么 example_stdio 和 example_http 默认关闭
​        它们只是配置形态示例，还没有替换成真实可运行的 Server。如果默认启用，项目启动或工具发现时就会因为示例命令和示例 URL 失败。默认关闭可以让读者先用 demo 跑通闭环，再按自己的环境启用真实 Server。

### 32.11.3 为什么不完整实现 SSE
​        SSE MCP 传输需要长连接会话管理和消息端点处理，本章没有实现这部分生命周期。代码选择返回 501，是为了让调用方清楚知道当前不支持，而不是误以为 SSE 已经能用。后续如果要支持 SSE，应单独实现连接管理，而不是在当前最小客户端里硬凑。

### 32.11.4 mcp_call 的 arguments_json 为什么是字符串
​        当前 AgentTool 参数模型更适合基础类型，工具事件也把输出保存为字符串。`arguments_json` 用字符串承载任意 MCP 工具参数，可以先打通通用入口。后续如果把 MCP 工具动态展开成独立工具，就可以把每个工具的 JSON Schema 转换成更明确的参数定义。

### 32.11.5 为什么 MCP 工具结果还要格式化成 JSON 字符串
​        这是为了复用现有工具事件模型。事件层只需要保存工具输出字符串，前端再通过 `kind=mcp_tool_result` 判断如何渲染。这个模式已经用于浏览器截图和搜索结果，可以保持工具输出展示方式一致。

### 32.11.6 为什么前端把 MCP 面板放在环境页签
​        MCP Server 和工具发现结果属于执行环境状态，而不是某一次具体工具调用。环境页签展示当前可用的外部能力，工具页签展示某次调用的结果。这样用户既能在任务前检查可用工具，也能在任务后查看调用详情。
### 32.11.7 工具发现失败应该先查哪里
​        先查 `/api/mcp/servers`，确认配置文件是否被读到、Server 是否启用、transport 是否正确。再查 `/api/mcp/tools?server_name=具体名称`，把问题缩小到单个 Server。如果 demo 能发现工具，但 stdio 或 HTTP 失败，说明主链路是通的，问题更可能在命令、URL、超时或 Server 自身协议响应。这样分层排查比直接看前端空列表更有效。

### 32.11.8 为什么结果里一直带 server_name
​        MCP 工具来自外部 Server，不同 Server 可能暴露同名工具。只保存 `tool_name` 会让事件记录和前端展示失去来源信息，也会让后续任务回放无法确认当时调用的是哪个 Server。本章从领域对象、API 响应、AgentTool 输出到前端卡片都保留 `server_name`，就是为了让工具来源始终可追踪。
### 32.11.9 为什么不把工具发现结果直接缓存到前端
​        本章让前端刷新时重新请求 `/api/mcp/tools`，是为了保持教学阶段的行为直接可见。配置改动、Server 启停和工具变更都应该先通过后端接口体现出来，再由前端展示。等后续 Server 数量增多或工具发现成本变高，再考虑后端缓存、增量刷新或按 Server 局部刷新会更合适。

## 32.12 本章小结
​        本章完成了 MCP 工具接入的最小闭环。后端从 YAML 配置读取 MCP Server，使用 `McpClientManager` 按 transport 创建 Client，通过 `McpService` 暴露 Server、工具和调用能力，再通过 API 路由和 `mcp_call` AgentTool 接入现有执行链路。前端新增 MCP 状态读取、MCP 面板和 MCP 工具结果渲染，让外部工具既能被调用，也能被观察。
​        更重要的是，本章建立了一个可扩展模式。外部能力先被配置声明，再被 Client 发现，最后被适配成当前 Agent 能理解的工具输出。这个模式会继续支撑后面的 A2A 接入、多 Agent 协作和更复杂的工具选择策略。
​        和第 31 章相比，本章最大的变化是 MCP 不再只是概念说明。第 31 章的 demo 接口帮助读者理解协议流程，第 32 章则让配置、发现、调用、AgentTool、事件和前端观察真正串起来。此后再接新的外部工具时，应该优先思考它落在这条链路的哪一层，而不是直接在业务代码里临时写一次调用。
​        这也是后续工程扩展的底座：先让外部能力进入统一工具协议，再讨论更复杂的调度、权限和模型选择。统一入口越稳定，后面替换 Server、增加工具或调整前端展示时，改动范围就越可控。

## 32.13 下一章预告
​        下一章会进入后端分层框架重构。到目前为止，项目功能已经快速增长，API、应用服务、基础设施、工具注册和前端状态都在持续扩展。第 33 章会开始整理后端结构，让后续 A2A、多 Agent、长期记忆和复杂任务恢复有更稳的工程基础。

## 32.14 代码索引
​        本章源码可以按这条顺序阅读：先看 `api/config/mcp.yaml` 和 `api/app/core/mcp_config.py`，理解 Server 如何声明和校验；再看 `api/app/domain/mcp/entities.py`、`api/app/infrastructure/mcp/client.py` 和 `api/app/application/mcp_service.py`，理解工具发现与调用如何进入应用层；然后看 `api/app/infrastructure/agent_tools/mcp.py`、`builtin.py` 和 `react_agent_service.py`，理解 MCP 如何成为 AgentTool；最后看 `ui/app/lib/mcp-api.ts`、`ui/app/components/mcp-panel.tsx`、`tool-preview-panel.tsx` 和 `page.tsx`，理解前端如何展示 MCP 状态和结果。
