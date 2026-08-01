# 第三十一章. MCP 协议初识

## 31.1 本章目标
​        前面几章已经把项目内部工具体系做出了一个雏形。FileTool、ShellTool、BrowserTool 和 SearchTool 都是在我们自己的代码里定义、注册、调用和展示的工具。这样的方式适合教学项目的前半段，因为每个工具都能被我们完整控制；但当 Agent 产品开始接入更多外部系统时，问题就会出现。每接一个系统都写一套私有协议，最终会让工具体系变得越来越分散。
​        MCP，也就是 Model Context Protocol，要解决的正是这个问题。它提供一种标准方式，让外部服务把 tools、resources、prompts 等能力暴露给 AI 应用。Host 不需要把所有能力都写进自己的代码仓库，而是通过 MCP Client 连接一个或多个 MCP Server，先发现能力，再按协议调用能力。本章的目标不是马上启动真实 MCP Server，而是先把这套角色关系和调用流程讲清楚。
​        本章完成后，你应该能清楚区分 MCP Host、MCP Client、MCP Server 三个角色，理解 tools、resources、prompts 三类能力的定位，知道 `tools/list` 和 `tools/call` 分别发生在什么时候，也能通过本地确定性接口看到一次模拟 MCP 工具发现和调用流程。只有先理解这条链路，第 32 章接真实 MCP 工具时才不会只是在照抄代码。

## 31.2 最终效果
​        本章结束后，后端会新增一组 MCP 入门接口。它们不连接真实 MCP Server，也不启动额外进程，而是在主 API 内部返回确定性演示数据。这样做的目的，是让读者在没有外部依赖的情况下先理解协议模型。

```Plain
GET  /api/mcp/concepts
GET  /api/mcp/demo/tools
POST /api/mcp/demo/call
```

​        访问概念接口时，可以看到 MCP 的三个核心角色、三类能力、常见传输方式和协议格式。返回内容会提到 `Host`、`Client`、`Server`、`tools`、`resources`、`prompts`、`stdio`、`Streamable HTTP` 和 `JSON-RPC 2.0 message format`。这些不是为了堆概念，而是为了让后面的代码有明确语言。
​        访问工具发现接口时，会看到一个模拟 MCP Server 暴露的工具列表。本章内置了两个演示工具：`mcp_echo` 用来观察参数如何流动，`mcp_add_note` 用来模拟把一条笔记写入外部系统。它们都有工具名称、描述和 `input_schema`，这对应 MCP 工具发现里最常见的工具描述结构。
​        调用工具演示接口时，后端会返回一次模拟调用结果，并带上完整步骤：

```Plain
tools/list -> tool selection -> tools/call -> content response
```

​        这一章的最终效果不是“多了三个接口”这么简单，而是项目开始从内部工具体系走向开放工具协议。我们先用可控演示把 MCP 讲清楚，再在下一章把真实 MCP Client 接进 Agent 工具注册和执行链路。

## 31.3 本章要解决的问题
​        在第 30 章之前，项目里的工具都是内部工具。内部工具的优点是直接、可控、易调试；缺点是扩展边界有限。假设以后要接 GitHub、Notion、飞书、Sentry、数据库、公司内部工单系统和第三方自动化平台，如果每个系统都在 AtlasAgent 里写一套 client、一套工具定义、一套路由和一套输出解析，主项目会越来越像集成脚本仓库，而不是一个稳定的 Agent Host。
​        MCP 的价值，是把“外部能力如何暴露给 Agent”标准化。外部系统可以运行自己的 MCP Server，Server 对外声明它有哪些 tools、resources 和 prompts；Host 通过 Client 发现这些能力，再按协议调用。这样 Agent Host 可以专注于任务、上下文、工具选择、执行编排和用户体验，外部系统则负责实现自己的能力。
​        本章要解决的是认知断层。很多人在第一次接触 MCP 时，会直接跳到“安装某个 MCP Server”“配置某个命令”“调用某个工具”，但没有先搞清楚 Host、Client、Server 谁在发起连接，谁在维护传输，谁在暴露能力，谁在决定调用。这个断层会导致后面排查问题时分不清是协议问题、连接问题、工具参数问题，还是 Host 的工具注册问题。

## 31.4 本章技术方案
​        本章采用“确定性本地演示”的方案。我们不启动真实 MCP Server，也不连接 stdio 或 Streamable HTTP，而是在后端新增 `McpIntroService`，让它返回固定的角色说明、能力说明、工具列表和调用步骤。这样做可以把协议概念和工程实现拆开：第 31 章先讲协议模型，第 32 章再处理真实连接。
​        这个方案有三个好处。第一，它不依赖外部进程和网络环境，读者只要能启动主 API 就能验证。第二，它能把 MCP 的关键名词映射到当前项目已有对象上，例如 tools 对应当前的 `AgentTool` 和 `tool_called` 事件，resources 对应上下文工程里的文件引用和外部资料，prompts 对应未来的任务模板和业务提示词。第三，它为下一章预留了同样的 API 形状，后面把 demo 数据替换成真实 MCP Client 返回值时，读者不会觉得结构突变。
​        代码层面，本章新增三部分。`api/app/application/mcp_intro_service.py` 负责组织演示数据和模拟调用流程；`api/app/schemas/mcp.py` 负责定义 API 响应模型；`api/app/api/routes/mcp.py` 负责暴露 `/api/mcp` 路由，并把应用服务里的 dataclass 转换成 Pydantic 响应。最后在 `api/app/api/router.py` 中注册 MCP 路由，让它进入主 API。

## 31.5 新增和修改的文件
​        本章主要新增 MCP 入门服务、Schema 和路由，同时更新项目说明文档。涉及文件如下：

```Plain
api/app/application/mcp_intro_service.py
api/app/schemas/mcp.py
api/app/api/routes/mcp.py
api/app/api/router.py
README.md
api/README.md
docs/course/chapters/31-mcp-intro.md
```

​        这些文件的职责很清晰。应用服务保存 MCP 概念和演示流程，Schema 固定对外响应形状，路由负责 HTTP 入口，主路由负责把 MCP 模块挂到统一 API 前缀下。把它们拆开写，是为了保持后端分层一致。即使这一章只是入门演示，也不要把概念数据、响应模型和路由函数全部塞进一个文件里。

## 31.6 实施步骤
​        本章的实施顺序从应用服务开始。原因很简单：MCP 概念和演示流程先在应用层成立，路由层才有东西可以暴露。写完应用服务后，再定义 Pydantic Schema，最后写路由和主路由注册。这个顺序能让代码从内向外展开，而不是一开始就被 HTTP 细节牵着走。

### 31.6.1 定义 MCP 入门领域对象
​        `mcp_intro_service.py` 里先定义几个小的 dataclass，用来承载本章需要讲解的概念。它们不是数据库实体，也不是完整 MCP 协议对象，而是服务于教学接口的应用层数据结构。

```Python
@dataclass(slots=True)
class McpRole:
    name: str
    responsibility: str
    example: str


@dataclass(slots=True)
class McpCapability:
    name: str
    description: str
    system_mapping: str
```

​        `McpRole` 用来解释 Host、Client 和 Server。`name` 是角色名称，`responsibility` 说明它在 MCP 架构中负责什么，`example` 把这个角色映射到 AtlasAgent 项目中能理解的位置。这样读者不会只记住抽象概念，而能把它和当前项目的主 API、前端工作台、未来的连接适配层联系起来。
​        `McpCapability` 用来解释 MCP Server 能暴露的能力类型。`tools` 是可调用动作，`resources` 是可读取上下文，`prompts` 是提示词模板。当前项目已经有 AgentTool、上下文工程和任务提示词雏形，所以本章会把这三类能力逐一映射到已有模块上。

### 31.6.2 定义工具发现和调用演示对象
​        MCP 入门不只讲概念，还要模拟一次工具发现和工具调用。因此服务里继续定义 `McpToolDemo`、`McpCallStep` 和 `McpToolCallDemo`。

```Python
@dataclass(slots=True)
class McpToolDemo:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(slots=True)
class McpCallStep:
    index: int
    action: str
    detail: str


@dataclass(slots=True)
class McpToolCallDemo:
    tool_name: str
    arguments: dict[str, Any]
    content: list[dict[str, str]]
    steps: list[McpCallStep]
```

​        `McpToolDemo` 对应 `tools/list` 返回的一条工具描述。它包含工具名、描述和输入参数 Schema。这个结构和前面项目内部的 `ToolDefinition` 很像，但它代表的是外部 MCP Server 暴露出来的能力，而不是我们在本项目里手写注册的工具。
​        `McpCallStep` 和 `McpToolCallDemo` 用来让调用流程可观察。真实 MCP 调用里，Host 不只是“调用一个函数”，而是先发现工具，再选择工具，再发送 `tools/call` 请求，最后收到 content 数组。把这些步骤放进响应里，能让读者看到协议动作之间的顺序关系。

### 31.6.3 编写 McpIntroService
​        `McpIntroService` 是本章的核心。它的 docstring 直接说明当前章节的边界：不启动真实 MCP Server，不连接 stdio，也不连接 Streamable HTTP，只用确定性数据模拟工具发现和工具调用。

```Python
class McpIntroService:
    """第 31 章的 MCP 入门应用服务。

    这一章不启动真实 MCP Server，也不连接 stdio 或 Streamable HTTP。
    这里用确定性数据模拟 MCP 的工具发现和工具调用流程，
    让读者先理解 Host、Client、Server、tools/list、tools/call 的关系。
    """
```

​        这个边界很重要。它不是功能缺失，也不是对真实协议的替代，而是教学顺序上的分层。MCP 的概念如果没有先讲清楚，直接接真实 Server 时会混入太多问题：命令启动、传输协议、进程生命周期、JSON-RPC 消息、工具 schema、异常处理和工具结果转换。本章先把角色和流程固定下来，下一章再处理真实连接。

### 31.6.4 返回 MCP 角色说明
​        `list_roles()` 返回 Host、Client 和 Server 三个角色。每个角色都有职责描述和本项目中的类比位置。

```Python
def list_roles(self) -> list[McpRole]:
    return [
        McpRole(
            name="Host",
            responsibility="承载 AI 应用，负责组织对话、上下文和工具调用决策。",
            example="AtlasAgent 的主 API 和前端工作台共同组成 Host 体验。",
        ),
        McpRole(
            name="Client",
            responsibility="由 Host 创建，负责和某一个 MCP Server 建立连接并发送协议请求。",
            example="第 32 章会在主 API 中实现 MCP Client 适配层。",
        ),
        McpRole(
            name="Server",
            responsibility="对外暴露 tools、resources、prompts 等能力。",
            example="文件系统 MCP Server、浏览器 MCP Server 或第三方业务 MCP Server。",
        ),
    ]
```

​        Host 是承载 AI 应用的地方。在本项目中，前端工作台和主 API 一起提供 Host 体验：前端接收用户任务，后端组织会话、上下文、计划和工具调用。Client 是 Host 内部创建的连接适配层，它负责和某一个 MCP Server 通信。Server 则是能力提供方，它可以是文件系统服务、浏览器服务、业务系统服务，也可以是后续我们自己写的工具服务。
​        理解这三个角色以后，很多问题会自然清楚。工具选择通常属于 Host 或 Agent 执行层；连接维护属于 Client；工具真实实现属于 Server。不要把三者混在一起，否则调试时会把“工具没有注册”“连接没有建立”“Server 没有返回结果”混成同一个问题。

### 31.6.5 返回 MCP 能力说明
​        `list_capabilities()` 返回 MCP Server 通常能暴露的三类能力。它们分别是 tools、resources 和 prompts。

```Python
def list_capabilities(self) -> list[McpCapability]:
    return [
        McpCapability(
            name="tools",
            description="可被模型或 Agent 调用的动作，例如搜索、读文件、创建工单。",
            system_mapping="对应当前项目里的 AgentTool 和 tool_called 事件。",
        ),
        McpCapability(
            name="resources",
            description="可读取的上下文资源，例如文件、数据库记录、网页内容。",
            system_mapping="对应上下文工程中的文件引用、消息摘要和外部资料。",
        ),
        McpCapability(
            name="prompts",
            description="Server 提供的提示词模板，帮助 Host 生成更稳定的任务输入。",
            system_mapping="后续可用于预置任务模板、工具使用说明和业务流程提示词。",
        ),
    ]
```

​        tools 最容易理解，它们对应可执行动作。我们前面写的 FileTool、ShellTool、BrowserTool 和 SearchTool，都可以被看成项目内部工具体系里的 tools。resources 更偏上下文，它们不一定会改变外部系统状态，而是给 Host 提供可读取内容，例如文件、数据库记录或网页内容。prompts 则是 Server 提供的提示模板，可以帮助 Host 生成更稳定的任务输入。
​        这一章虽然只演示 tools，但仍然把 resources 和 prompts 放进概念接口，是为了避免读者把 MCP 简化成“远程工具调用协议”。MCP 的价值不只在调用动作，也在让外部系统用标准方式向 Host 提供上下文和提示模板。

### 31.6.6 模拟 tools/list 工具发现
​        `list_demo_tools()` 返回两个演示工具。它模拟的是 MCP Client 向 Server 发送 `tools/list` 后拿到的工具描述列表。

```Python
def list_demo_tools(self) -> list[McpToolDemo]:
    return [
        McpToolDemo(
            name="mcp_echo",
            description="返回调用方传入的文本，用来观察 MCP tools/call 的参数流动。",
            input_schema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "需要原样返回的文本。",
                    }
                },
                "required": ["text"],
            },
        ),
        McpToolDemo(
            name="mcp_add_note",
            description="模拟把一条笔记写入外部系统，并返回笔记摘要。",
            input_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "笔记标题。"},
                    "content": {"type": "string", "description": "笔记正文。"},
                },
                "required": ["title", "content"],
            },
        ),
    ]
```

​        `mcp_echo` 的意义是观察参数传递。调用方传入 `text`，Server 返回 `echo: text`。这个工具没有业务复杂度，适合验证工具发现和调用流程。`mcp_add_note` 稍微接近真实业务，它要求 `title` 和 `content`，模拟把笔记写入外部系统，再返回创建摘要。
​        这里的 `input_schema` 很关键。Agent 调用工具之前，需要知道工具接受什么参数、哪些字段必填、字段类型是什么。项目内部工具已经有 `ToolParameter`，MCP 工具则通常通过 JSON Schema 描述输入。理解了这点，下一章把 MCP 工具转换成项目内部 `AgentTool` 时就有了方向。

### 31.6.7 模拟 tools/call 工具调用
​        `call_demo_tool()` 根据工具名和参数模拟一次 MCP 工具调用。它先确认工具名存在，如果不存在就抛出 `AppException`。

```Python
tool_names = {tool.name for tool in self.list_demo_tools()}
if tool_name not in tool_names:
    raise AppException(
        message=f"mcp demo tool not found: {tool_name}",
        code=404,
        status_code=404,
    )
```

​        这里不做静默兜底。工具名不存在就是调用错误，应该清楚返回 404。真实 MCP 接入时也是一样，Host 如果调用了 Server 没有暴露的工具，问题应该被显式暴露，而不是自动替换成另一个工具。
​        函数随后组装 `steps`，把一次工具调用拆成四个可观察动作：`tools/list`、`tool selection`、`tools/call` 和 `content response`。这些步骤不是协议日志的完整复刻，而是教学视角下最关键的顺序。

```Python
steps = [
    McpCallStep(index=1, action="tools/list", detail="Host 先通过 MCP Client 向 Server 获取可用工具列表。"),
    McpCallStep(index=2, action="tool selection", detail=f"Agent 根据任务选择工具 {tool_name}，并整理调用参数。"),
    McpCallStep(index=3, action="tools/call", detail="MCP Client 把工具名和参数发送给 MCP Server。"),
    McpCallStep(index=4, action="content response", detail="MCP Server 返回 content 数组，Host 再把结果写入工具事件。"),
]
```

​        最后函数根据工具名生成 content。`mcp_echo` 要求 `text`，缺失时返回 400；`mcp_add_note` 要求 `title` 和 `content`，缺失时同样返回 400。调用成功后，结果使用 `content` 数组承载，这和 MCP 工具结果的常见结构保持一致。

### 31.6.8 定义 MCP API Schema
​        应用服务里的 dataclass 不直接作为 HTTP 响应。`api/app/schemas/mcp.py` 定义 Pydantic 模型，让 API 响应形状稳定下来。

```Python
class McpConceptsResponse(BaseModel):
    roles: list[McpRoleResponse]
    capabilities: list[McpCapabilityResponse]
    transports: list[str]
    protocol: str


class McpToolDemoResponse(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]


class McpToolCallRequest(BaseModel):
    tool_name: str = Field(min_length=1, max_length=100)
    arguments: dict[str, Any] = Field(default_factory=dict)
```

​        `McpConceptsResponse` 把角色、能力、传输方式和协议格式放在一起。`McpToolDemoResponse` 对应工具发现结果。`McpToolCallRequest` 则是调用演示接口的请求体，其中 `tool_name` 有长度限制，`arguments` 默认为空字典。
​        Schema 单独放在 `schemas` 目录，是为了保持 API 层边界清晰。应用服务可以使用 dataclass 表达内部概念，路由层对外返回 Pydantic 模型。以后真实 MCP 接入后，内部对象可能变化，但 HTTP 响应模型可以尽量保持稳定。

### 31.6.9 新增 MCP 路由
​        `api/app/api/routes/mcp.py` 创建 `/mcp` 路由。路由里先定义 `build_mcp_intro_service()`，当前直接返回 `McpIntroService()`。

```Python
router = APIRouter(prefix="/mcp", tags=["mcp"])


def build_mcp_intro_service() -> McpIntroService:
    return McpIntroService()
```

​        现在这个工厂函数很简单，但它的位置很重要。第 32 章接真实 MCP Client 时，这里会变成注入配置、连接管理器或真实服务的入口。先把依赖创建集中起来，后面改动范围就不会扩散到每个路由函数。
​        路由文件还包含一组转换函数，例如 `to_role_response()`、`to_capability_response()`、`to_tool_response()`、`to_step_response()` 和 `to_call_response()`。它们把应用服务对象转换成 API 响应对象。这样路由函数本身可以保持很短，业务数据如何组织由应用服务负责，响应结构如何暴露由 Schema 负责。

### 31.6.10 实现概念接口
​        概念接口暴露在 `GET /api/mcp/concepts`。它调用 `list_roles()` 和 `list_capabilities()`，再补充传输方式和协议格式。

```Python
@router.get("/concepts", response_model=ApiResponse[McpConceptsResponse])
async def get_mcp_concepts(
    service: McpIntroService = Depends(build_mcp_intro_service),
) -> ApiResponse[McpConceptsResponse]:
    return ApiResponse(
        data=McpConceptsResponse(
            roles=[to_role_response(role) for role in service.list_roles()],
            capabilities=[
                to_capability_response(capability)
                for capability in service.list_capabilities()
            ],
            transports=["stdio", "Streamable HTTP"],
            protocol="JSON-RPC 2.0 message format",
        )
    )
```

​        这一章只解释传输方式名称，不实现真实连接。`stdio` 常用于本地进程型 Server，`Streamable HTTP` 常用于 HTTP 传输场景。协议格式写成 `JSON-RPC 2.0 message format`，是为了让读者知道 MCP 的数据层不是随意 JSON，而是建立在消息协议之上。下一章真正接入时，再展开连接和消息细节。

### 31.6.11 实现工具发现和调用接口
​        工具发现接口暴露在 `GET /api/mcp/demo/tools`。它返回 `McpToolListResponse`，内部 items 来自 `service.list_demo_tools()`。

```Python
@router.get("/demo/tools", response_model=ApiResponse[McpToolListResponse])
async def list_mcp_demo_tools(
    service: McpIntroService = Depends(build_mcp_intro_service),
) -> ApiResponse[McpToolListResponse]:
    return ApiResponse(
        data=McpToolListResponse(
            items=[to_tool_response(tool) for tool in service.list_demo_tools()],
        )
    )
```

​        工具调用接口暴露在 `POST /api/mcp/demo/call`。它接收工具名和参数，调用应用服务，再把结果转换成响应。

```Python
@router.post("/demo/call", response_model=ApiResponse[McpToolCallResponse])
async def call_mcp_demo_tool(
    payload: McpToolCallRequest,
    service: McpIntroService = Depends(build_mcp_intro_service),
) -> ApiResponse[McpToolCallResponse]:
    demo = service.call_demo_tool(
        tool_name=payload.tool_name,
        arguments=payload.arguments,
    )
    return ApiResponse(data=to_call_response(demo))
```

​        这两个接口都带有 `demo`，是为了避免读者误解它们已经是完整 MCP Client。它们模拟的是协议行为，不是真实连接。真实 MCP 工具接入会在第 32 章完成，到时工具发现不再来自固定列表，而是来自外部 MCP Server 返回的 `tools/list` 结果。

### 31.6.12 注册 MCP 路由
​        最后，在主 API 路由中注册 MCP 模块。

```Python
from app.api.routes import (
    agent_core,
    agent_thinking,
    config,
    files,
    llm,
    mcp,
    sandboxes,
    sessions,
    status,
)

api_router.include_router(mcp.router)
```

​        这一步完成后，MCP 入门接口就会随着主 API 一起挂载到 `/api/mcp/...`。如果忘记注册，单独写好的路由文件不会生效。这个错误在后端开发中很常见，所以每次新增路由都要检查主路由汇总文件。

## 31.7 关键理解
​        本章最重要的理解，是 MCP 不是单纯的“远程调用工具”。它是一套让 AI 应用发现、理解和调用外部能力的协议。tools 只是其中一类能力，resources 和 prompts 同样重要。把 MCP 只看成工具调用，会忽略它在上下文和提示模板上的价值。
​        第二个关键点是 Host、Client、Server 的边界。Host 负责 AI 应用体验和工具决策，Client 负责连接某个 MCP Server，Server 负责暴露外部能力。AtlasAgent 当前已经具备 Host 雏形，下一章要补的是 Client 适配层，而不是把 Server 代码硬塞进主 API。
​        第三个关键点是 `tools/list` 先于 `tools/call`。Agent 不能凭空调用外部工具，它必须先知道 Server 暴露了哪些工具、工具需要什么参数、描述是什么，然后才能选择并调用。这个顺序和我们前面内部工具注册表的思路是相通的，只是工具来源从本地代码变成了外部 MCP Server。
​        第四个关键点是内部工具和 MCP 工具最终要汇合到同一条执行链路上。对用户来说，他不关心某个能力是我们在项目里手写的，还是外部 MCP Server 暴露的；他只关心 Agent 是否能正确选择工具、传入参数、拿到结果，并把结果展示在工具预览面板里。因此后续接入 MCP 时，不应该让外部工具绕开现有的 `ToolRegistry`、`tool_called` 事件和预览体系，而应该把 MCP 工具适配成当前项目能理解的工具形态。这样内部工具和外部工具才能共享同一套任务执行、事件记录和用户观察机制。

## 31.8 技术难点与亮点
​        本章的难点在于控制边界。很多教程一上来就接真实 MCP Server，结果读者同时面对协议概念、进程启动、传输配置、消息格式和工具调用，信息量太大。本章选择先做确定性演示，把所有不稳定外部因素拿掉，只保留协议角色和调用流程。这样读者能先建立正确心智模型。
​        另一个亮点是把 MCP 概念映射到当前项目。Host 不再只是抽象名词，而是当前主 API 和前端工作台；tools 不再只是协议字段，而是可以类比到 `AgentTool` 和 `tool_called`；resources 可以类比上下文工程，prompts 可以类比未来的任务模板。通过这种映射，MCP 不再像外部知识点，而是自然接到本项目的下一层能力。
​        第三个亮点是显式错误。`call_demo_tool()` 遇到不存在的工具名会抛 404，缺少必填参数会抛 400。演示代码也应该暴露错误，而不是悄悄替换工具或返回空结果。只有这样，下一章接真实 Server 时，错误边界才不会变得含糊。
​        还有一个容易忽略的亮点，是本章把“可验证范围”控制得很窄。验证概念接口时，只看角色和能力是否返回；验证工具发现时，只看工具描述和 `input_schema`；验证工具调用时，只看参数、content 和步骤顺序。每一步都有明确观察点，失败时也能快速定位到服务、Schema、路由或主路由注册中的某一层。这种验证方式比只说“启动后试一下 MCP”更适合工程教程。

## 31.9 面试考点
​        如果面试官问“MCP Host、Client、Server 分别是什么”，可以回答：Host 是承载 AI 应用和工具决策的地方，Client 是 Host 内部负责连接某个 MCP Server 的适配层，Server 是暴露 tools、resources、prompts 的能力提供方。在本项目中，主 API 和前端工作台构成 Host 体验，第 32 章要实现 Client 适配层，外部工具服务才是 Server。
​        如果被问到“tools/list 和 tools/call 的关系”，重点说明 Host 需要先通过 Client 获取 Server 暴露的工具列表，理解工具名称、描述和输入参数，再根据任务选择工具并发起 `tools/call`。这和本项目内部 `ToolRegistry.list_tools()` 再调用具体工具的思路类似，只是工具来源不同。
​        如果被问到“为什么第 31 章不直接接真实 MCP Server”，可以说明本章是协议入门层，先用确定性接口讲清角色、能力和调用流程，避免把真实连接的复杂度提前混进来。第 32 章会在这个认知基础上再实现真实 MCP Client。
​        如果被问到“resources 和 prompts 有什么意义”，可以回答：resources 用来让 Server 暴露可读取上下文，例如文件、数据库记录或网页内容；prompts 用来让 Server 提供提示词模板，帮助 Host 构造更稳定任务输入。它们让 MCP 不只是动作调用协议，也能承载上下文和任务模板。

## 31.10 运行验证
​        本章的验证重点是三个接口是否能返回预期结构，以及错误是否清晰暴露。因为本章没有真实 MCP Server，所以不需要配置外部进程，也不需要申请凭据。

### 31.10.1 检查后端代码
​        先确认 MCP 入门服务、Schema 和路由都存在：

```PowerShell
rg -n "McpIntroService|McpConceptsResponse|/demo/tools|/demo/call" api/app
```

​        输出中应该能看到 `mcp_intro_service.py`、`schemas/mcp.py` 和 `routes/mcp.py` 里的关键类和接口。再检查主路由是否引入并注册了 `mcp.router`，否则接口文件存在也不会对外暴露。

### 31.10.2 启动服务
​        启动后端和网关：

```PowerShell
docker compose up --build
```

​        如果本地已经有服务在运行，可以只重建 API 容器，但要确保新路由已经被加载。路由注册类改动通常需要重启后端进程。

### 31.10.3 验证 MCP 概念接口
​        调用概念接口：

```Bash
curl http://localhost:8088/api/mcp/concepts
```

​        响应里应该包含 `roles`、`capabilities`、`transports` 和 `protocol`。`roles` 中应该有 Host、Client、Server，`capabilities` 中应该有 tools、resources、prompts。看到这些字段，说明概念服务和 Schema 转换都已经打通。

### 31.10.4 验证工具发现接口
​        调用工具发现接口：

```Bash
curl http://localhost:8088/api/mcp/demo/tools
```

​        响应中应该看到 `mcp_echo` 和 `mcp_add_note`，并且每个工具都有 `input_schema`。这一步模拟的就是真实 MCP Client 发起 `tools/list` 后拿到的工具描述。

### 31.10.5 验证工具调用接口
​        调用 `mcp_echo`：

```Bash
curl -X POST http://localhost:8088/api/mcp/demo/call \
  -H "Content-Type: application/json" \
  -d '{"tool_name":"mcp_echo","arguments":{"text":"hello mcp"}}'
```

​        响应中应该看到 `content` 里包含 `echo: hello mcp`，steps 中依次出现 `tools/list`、`tool selection`、`tools/call` 和 `content response`。这说明模拟调用流程已经完整。

### 31.10.6 验证错误暴露
​        再故意传入不存在的工具名：

```Bash
curl -X POST http://localhost:8088/api/mcp/demo/call \
  -H "Content-Type: application/json" \
  -d '{"tool_name":"missing_tool","arguments":{}}'
```

​        这时应该返回工具不存在的错误，而不是悄悄调用其他工具。再调用 `mcp_echo` 但不传 `text`，也应该看到参数缺失错误。这个验证能证明演示服务没有把调用错误吞掉。

## 31.11 常见问题
### 31.11.1 MCP 和我们自己写的 ToolRegistry 是什么关系
​        当前项目的 `ToolRegistry` 是内部工具注册机制，工具定义来自本项目代码。MCP 则是外部工具服务的协议。下一章要做的事情，就是让 MCP Server 暴露出来的工具能够被转换成项目内部可调用的工具形态。可以把 MCP 看成外部工具来源，把 `ToolRegistry` 看成当前 Agent 执行层使用工具的统一入口。

### 31.11.2 为什么本章接口叫 demo
​        因为它们不是完整 MCP Client，只是模拟 MCP 的关键行为。`/demo/tools` 模拟 `tools/list`，`/demo/call` 模拟 `tools/call`，返回数据来自本地确定性服务。这样命名可以避免读者误以为本章已经连接了真实 MCP Server。

### 31.11.3 为什么要单独解释 resources 和 prompts
​        虽然本章只演示 tools，但 MCP 不只有工具调用。resources 可以给 Host 提供可读取上下文，prompts 可以提供提示模板。后面的长期记忆、上下文注入、业务流程模板都可能和这两类能力发生关系，所以入门时就要建立完整视角。

### 31.11.4 为什么要把调用步骤返回给前端或接口调用方
​        本章返回 steps 是为了教学可观察。真实协议里这些动作可能散落在日志、连接层和工具调用层，如果不显式展示，读者很难理解一次调用内部发生了哪些阶段。把步骤放进响应里，可以让 `tools/list`、工具选择、`tools/call` 和结果返回的顺序一眼可见。

### 31.11.5 为什么不用真实 MCP Server 做第一章 MCP 内容
​        真实 MCP Server 会带来进程启动、传输协议、依赖安装、连接生命周期和异常处理。对于第一次接触 MCP 的读者，这些会掩盖协议本身的角色关系。本章先用确定性接口讲清楚流程，下一章再接真实 Server，学习成本更低，排查边界也更清楚。

### 31.11.6 MCP 接入后是不是就不需要内部工具了
​        不是。内部工具适合项目强绑定、稳定可控的能力，例如会话文件、沙箱 Shell、浏览器截图和项目私有逻辑。MCP 适合接入外部系统和标准化工具服务。成熟的 Agent 产品通常会同时使用内部工具和 MCP 工具，关键是让它们在执行层拥有统一的调用和观察方式。

## 31.12 本章小结
​        本章用确定性后端接口完成了 MCP 入门。我们新增了 `McpIntroService`，解释 Host、Client、Server 三个角色和 tools、resources、prompts 三类能力；又用 `mcp_echo` 和 `mcp_add_note` 模拟了工具发现与工具调用；最后通过 `/api/mcp/concepts`、`/api/mcp/demo/tools` 和 `/api/mcp/demo/call` 把这些内容暴露出来。
​        这章真正重要的不是代码量，而是边界感。Host 负责 AI 应用体验和工具选择，Client 负责连接 MCP Server，Server 负责暴露能力。`tools/list` 让 Host 发现工具，`tools/call` 让 Host 调用工具，content response 让结果回到 Agent 执行和观察体系。理解了这些，第 32 章接真实 MCP 工具时就会顺很多。
​        也就是说，本章是在为后面的真实接入建立统一语言。读者现在已经知道外部能力不会直接越过 Host 进入页面，而是要先被 Client 发现，再被转换成项目内部可以执行和观察的工具。这个认识会贯穿后面的 MCP 工具接入、A2A 工具接入以及多 Agent 协作编排。

## 31.13 下一章预告
​        下一章会在本章概念基础上继续前进，把 MCP 工具真正接入项目。到那时，我们不再只返回固定 demo 数据，而是实现 MCP Client 适配层，把外部 Server 暴露的工具转换成项目内部可注册、可调用、可观察的工具。第 31 章解决“理解协议”，第 32 章开始解决“接入协议”。

## 31.14 代码索引
​        本章源码可以按顺序阅读 `api/app/application/mcp_intro_service.py`、`api/app/schemas/mcp.py`、`api/app/api/routes/mcp.py` 和 `api/app/api/router.py`。第一份文件解释 MCP 入门概念并模拟流程，第二份文件固定 API 响应模型，第三份文件提供 HTTP 入口，第四份文件把 MCP 路由挂进主 API。这个阅读顺序和本章叙述一致，从应用服务到对外接口，能更清楚地看到一条入门演示链路是如何落到代码里的。
