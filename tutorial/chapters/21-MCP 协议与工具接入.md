# 第二十一章. MCP 协议与工具接入

## 21.1 合章说明

​        旧版教程把“MCP 协议初识”与“MCP 工具入列”拆成了相邻两章。两者实际上属于同一条能力链：前者把基础结构立住，后者让它进入可用状态。本章将它们合并为前后两个阶段，保留原来的实现、验证与工程判断，同时减少能力尚未闭环时的章节跳转。

## 21.2 第一阶段：MCP 协议初识

### 21.2.1 本阶段目标
​        前面几章已经把项目内部工具体系做出了一个雏形。FileTool、ShellTool、BrowserTool 和 SearchTool 都是在我们自己的代码里定义、注册、调用和展示的工具。这样的方式适合教学项目的前半段，因为每个工具都能被我们完整控制；但当 Agent 产品开始接入更多外部系统时，问题就会出现。每接一个系统都写一套私有协议，最终会让工具体系变得越来越分散。
​        MCP，也就是 Model Context Protocol，要解决的正是这个问题。它提供一种标准方式，让外部服务把 tools、resources、prompts 等能力暴露给 AI 应用。Host 不需要把所有能力都写进自己的代码仓库，而是通过 MCP Client 连接一个或多个 MCP Server，先发现能力，再按协议调用能力。本阶段的目标不是马上启动真实 MCP Server，而是先把这套角色关系和调用流程讲清楚。
​        本阶段完成后，你应该能清楚区分 MCP Host、MCP Client、MCP Server 三个角色，理解 tools、resources、prompts 三类能力的定位，知道 `tools/list` 和 `tools/call` 分别发生在什么时候，也能通过本地确定性接口看到一次模拟 MCP 工具发现和调用流程。只有先理解这条链路，本章第二阶段接真实 MCP 工具时才不会只是在照抄代码。

### 21.2.2 最终效果
​        本阶段结束后，后端会新增一组 MCP 入门接口。它们不连接真实 MCP Server，也不启动额外进程，而是在主 API 内部返回确定性演示数据。这样做的目的，是让读者在没有外部依赖的情况下先理解协议模型。

```Plain
GET  /api/mcp/concepts
GET  /api/mcp/demo/tools
POST /api/mcp/demo/call
```

​        访问概念接口时，可以看到 MCP 的三个核心角色、三类能力、常见传输方式和协议格式。返回内容会提到 `Host`、`Client`、`Server`、`tools`、`resources`、`prompts`、`stdio`、`Streamable HTTP` 和 `JSON-RPC 2.0 message format`。这些不是为了堆概念，而是为了让后面的代码有明确语言。
​        访问工具发现接口时，会看到一个模拟 MCP Server 暴露的工具列表。本阶段内置了两个演示工具：`mcp_echo` 用来观察参数如何流动，`mcp_add_note` 用来模拟把一条笔记写入外部系统。它们都有工具名称、描述和 `input_schema`，这对应 MCP 工具发现里最常见的工具描述结构。
​        调用工具演示接口时，后端会返回一次模拟调用结果，并带上完整步骤：

```Plain
tools/list -> tool selection -> tools/call -> content response
```

​        这一阶段的最终效果不是“多了三个接口”这么简单，而是项目开始从内部工具体系走向开放工具协议。我们先用可控演示把 MCP 讲清楚，再在本章第二阶段把真实 MCP Client 接进 Agent 工具注册和执行链路。

### 21.2.3 本阶段要解决的问题
​        在第 20 章之前，项目里的工具都是内部工具。内部工具的优点是直接、可控、易调试；缺点是扩展边界有限。假设以后要接 GitHub、Notion、飞书、Sentry、数据库、公司内部工单系统和第三方自动化平台，如果每个系统都在 AtlasAgent 里写一套 client、一套工具定义、一套路由和一套输出解析，主项目会越来越像集成脚本仓库，而不是一个稳定的 Agent Host。
​        MCP 的价值，是把“外部能力如何暴露给 Agent”标准化。外部系统可以运行自己的 MCP Server，Server 对外声明它有哪些 tools、resources 和 prompts；Host 通过 Client 发现这些能力，再按协议调用。这样 Agent Host 可以专注于任务、上下文、工具选择、执行编排和用户体验，外部系统则负责实现自己的能力。
​        本阶段要解决的是认知断层。很多人在第一次接触 MCP 时，会直接跳到“安装某个 MCP Server”“配置某个命令”“调用某个工具”，但没有先搞清楚 Host、Client、Server 谁在发起连接，谁在维护传输，谁在暴露能力，谁在决定调用。这个断层会导致后面排查问题时分不清是协议问题、连接问题、工具参数问题，还是 Host 的工具注册问题。

### 21.2.4 本阶段技术方案
​        本阶段采用“确定性本地演示”的方案。我们不启动真实 MCP Server，也不连接 stdio 或 Streamable HTTP，而是在后端新增 `McpIntroService`，让它返回固定的角色说明、能力说明、工具列表和调用步骤。这样做可以把协议概念和工程实现拆开：本阶段先讲协议模型，本章第二阶段再处理真实连接。
​        这个方案有三个好处。第一，它不依赖外部进程和网络环境，读者只要能启动主 API 就能验证。第二，它能把 MCP 的关键名词映射到当前项目已有对象上，例如 tools 对应当前的 `AgentTool` 和 `tool_called` 事件，resources 对应上下文工程里的文件引用和外部资料，prompts 对应未来的任务模板和业务提示词。第三，它为本章第二阶段预留了同样的 API 形状，后面把 demo 数据替换成真实 MCP Client 返回值时，读者不会觉得结构突变。
​        代码层面，本阶段新增三部分。`api/app/application/mcp_intro_service.py` 负责组织演示数据和模拟调用流程；`api/app/schemas/mcp.py` 负责定义 API 响应模型；`api/app/api/routes/mcp.py` 负责暴露 `/api/mcp` 路由，并把应用服务里的 dataclass 转换成 Pydantic 响应。最后在 `api/app/api/router.py` 中注册 MCP 路由，让它进入主 API。

### 21.2.5 新增和修改的文件
​        本阶段主要新增 MCP 入门服务、Schema 和路由，同时更新项目说明文档。涉及文件如下：

```Plain
api/app/application/mcp_intro_service.py
api/app/schemas/mcp.py
api/app/api/routes/mcp.py
api/app/api/router.py
README.md
api/README.md
docs/course/chapters/31-mcp-intro.md
```

​        这些文件的职责很清晰。应用服务保存 MCP 概念和演示流程，Schema 固定对外响应形状，路由负责 HTTP 入口，主路由负责把 MCP 模块挂到统一 API 前缀下。把它们拆开写，是为了保持后端分层一致。即使这一阶段只是入门演示，也不要把概念数据、响应模型和路由函数全部塞进一个文件里。

### 21.2.6 实施步骤
​        本阶段的实施顺序从应用服务开始。原因很简单：MCP 概念和演示流程先在应用层成立，路由层才有东西可以暴露。写完应用服务后，再定义 Pydantic Schema，最后写路由和主路由注册。这个顺序能让代码从内向外展开，而不是一开始就被 HTTP 细节牵着走。

#### 21.2.6.1 定义 MCP 入门领域对象
​        `mcp_intro_service.py` 里先定义几个小的 dataclass，用来承载本阶段需要讲解的概念。它们不是数据库实体，也不是完整 MCP 协议对象，而是服务于教学接口的应用层数据结构。

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
​        `McpCapability` 用来解释 MCP Server 能暴露的能力类型。`tools` 是可调用动作，`resources` 是可读取上下文，`prompts` 是提示词模板。当前项目已经有 AgentTool、上下文工程和任务提示词雏形，所以本阶段会把这三类能力逐一映射到已有模块上。

#### 21.2.6.2 定义工具发现和调用演示对象
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

#### 21.2.6.3 编写 McpIntroService
​        `McpIntroService` 是本阶段的核心。它的 docstring 直接说明当前章节的边界：不启动真实 MCP Server，不连接 stdio，也不连接 Streamable HTTP，只用确定性数据模拟工具发现和工具调用。

```Python
class McpIntroService:
    """第 31 章的 MCP 入门应用服务。

    这一章不启动真实 MCP Server，也不连接 stdio 或 Streamable HTTP。
    这里用确定性数据模拟 MCP 的工具发现和工具调用流程，
    让读者先理解 Host、Client、Server、tools/list、tools/call 的关系。
    """
```

​        这个边界很重要。它不是功能缺失，也不是对真实协议的替代，而是教学顺序上的分层。MCP 的概念如果没有先讲清楚，直接接真实 Server 时会混入太多问题：命令启动、传输协议、进程生命周期、JSON-RPC 消息、工具 schema、异常处理和工具结果转换。本阶段先把角色和流程固定下来，本章第二阶段再处理真实连接。

#### 21.2.6.4 返回 MCP 角色说明
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

#### 21.2.6.5 返回 MCP 能力说明
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
​        这一阶段虽然只演示 tools，但仍然把 resources 和 prompts 放进概念接口，是为了避免读者把 MCP 简化成“远程工具调用协议”。MCP 的价值不只在调用动作，也在让外部系统用标准方式向 Host 提供上下文和提示模板。

#### 21.2.6.6 模拟 tools/list 工具发现
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
​        这里的 `input_schema` 很关键。Agent 调用工具之前，需要知道工具接受什么参数、哪些字段必填、字段类型是什么。项目内部工具已经有 `ToolParameter`，MCP 工具则通常通过 JSON Schema 描述输入。理解了这点，本章第二阶段把 MCP 工具转换成项目内部 `AgentTool` 时就有了方向。

#### 21.2.6.7 模拟 tools/call 工具调用
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

#### 21.2.6.8 定义 MCP API Schema
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

#### 21.2.6.9 新增 MCP 路由
​        `api/app/api/routes/mcp.py` 创建 `/mcp` 路由。路由里先定义 `build_mcp_intro_service()`，当前直接返回 `McpIntroService()`。

```Python
router = APIRouter(prefix="/mcp", tags=["mcp"])

def build_mcp_intro_service() -> McpIntroService:
    return McpIntroService()
```

​        现在这个工厂函数很简单，但它的位置很重要。本章第二阶段接真实 MCP Client 时，这里会变成注入配置、连接管理器或真实服务的入口。先把依赖创建集中起来，后面改动范围就不会扩散到每个路由函数。
​        路由文件还包含一组转换函数，例如 `to_role_response()`、`to_capability_response()`、`to_tool_response()`、`to_step_response()` 和 `to_call_response()`。它们把应用服务对象转换成 API 响应对象。这样路由函数本身可以保持很短，业务数据如何组织由应用服务负责，响应结构如何暴露由 Schema 负责。

#### 21.2.6.10 实现概念接口
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

​        这一阶段只解释传输方式名称，不实现真实连接。`stdio` 常用于本地进程型 Server，`Streamable HTTP` 常用于 HTTP 传输场景。协议格式写成 `JSON-RPC 2.0 message format`，是为了让读者知道 MCP 的数据层不是随意 JSON，而是建立在消息协议之上。本章第二阶段真正接入时，再展开连接和消息细节。

#### 21.2.6.11 实现工具发现和调用接口
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

​        这两个接口都带有 `demo`，是为了避免读者误解它们已经是完整 MCP Client。它们模拟的是协议行为，不是真实连接。真实 MCP 工具接入会在本章第二阶段完成，到时工具发现不再来自固定列表，而是来自外部 MCP Server 返回的 `tools/list` 结果。

#### 21.2.6.12 注册 MCP 路由
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

### 21.2.7 关键理解
​        本阶段最重要的理解，是 MCP 不是单纯的“远程调用工具”。它是一套让 AI 应用发现、理解和调用外部能力的协议。tools 只是其中一类能力，resources 和 prompts 同样重要。把 MCP 只看成工具调用，会忽略它在上下文和提示模板上的价值。
​        第二个关键点是 Host、Client、Server 的边界。Host 负责 AI 应用体验和工具决策，Client 负责连接某个 MCP Server，Server 负责暴露外部能力。AtlasAgent 当前已经具备 Host 雏形，本章第二阶段要补的是 Client 适配层，而不是把 Server 代码硬塞进主 API。
​        第三个关键点是 `tools/list` 先于 `tools/call`。Agent 不能凭空调用外部工具，它必须先知道 Server 暴露了哪些工具、工具需要什么参数、描述是什么，然后才能选择并调用。这个顺序和我们前面内部工具注册表的思路是相通的，只是工具来源从本地代码变成了外部 MCP Server。
​        第四个关键点是内部工具和 MCP 工具最终要汇合到同一条执行链路上。对用户来说，他不关心某个能力是我们在项目里手写的，还是外部 MCP Server 暴露的；他只关心 Agent 是否能正确选择工具、传入参数、拿到结果，并把结果展示在工具预览面板里。因此后续接入 MCP 时，不应该让外部工具绕开现有的 `ToolRegistry`、`tool_called` 事件和预览体系，而应该把 MCP 工具适配成当前项目能理解的工具形态。这样内部工具和外部工具才能共享同一套任务执行、事件记录和用户观察机制。

### 21.2.8 技术难点与亮点
​        本阶段的难点在于控制边界。很多教程一上来就接真实 MCP Server，结果读者同时面对协议概念、进程启动、传输配置、消息格式和工具调用，信息量太大。本阶段选择先做确定性演示，把所有不稳定外部因素拿掉，只保留协议角色和调用流程。这样读者能先建立正确心智模型。
​        另一个亮点是把 MCP 概念映射到当前项目。Host 不再只是抽象名词，而是当前主 API 和前端工作台；tools 不再只是协议字段，而是可以类比到 `AgentTool` 和 `tool_called`；resources 可以类比上下文工程，prompts 可以类比未来的任务模板。通过这种映射，MCP 不再像外部知识点，而是自然接到本项目的下一层能力。
​        第三个亮点是显式错误。`call_demo_tool()` 遇到不存在的工具名会抛 404，缺少必填参数会抛 400。演示代码也应该暴露错误，而不是悄悄替换工具或返回空结果。只有这样，本章第二阶段接真实 Server 时，错误边界才不会变得含糊。
​        还有一个容易忽略的亮点，是本阶段把“可验证范围”控制得很窄。验证概念接口时，只看角色和能力是否返回；验证工具发现时，只看工具描述和 `input_schema`；验证工具调用时，只看参数、content 和步骤顺序。每一步都有明确观察点，失败时也能快速定位到服务、Schema、路由或主路由注册中的某一层。这种验证方式比只说“启动后试一下 MCP”更适合工程教程。

### 21.2.9 面试考点
​        如果面试官问“MCP Host、Client、Server 分别是什么”，可以回答：Host 是承载 AI 应用和工具决策的地方，Client 是 Host 内部负责连接某个 MCP Server 的适配层，Server 是暴露 tools、resources、prompts 的能力提供方。在本项目中，主 API 和前端工作台构成 Host 体验，本章第二阶段要实现 Client 适配层，外部工具服务才是 Server。
​        如果被问到“tools/list 和 tools/call 的关系”，重点说明 Host 需要先通过 Client 获取 Server 暴露的工具列表，理解工具名称、描述和输入参数，再根据任务选择工具并发起 `tools/call`。这和本项目内部 `ToolRegistry.list_tools()` 再调用具体工具的思路类似，只是工具来源不同。
​        如果被问到“为什么本阶段不直接接真实 MCP Server”，可以说明本阶段是协议入门层，先用确定性接口讲清角色、能力和调用流程，避免把真实连接的复杂度提前混进来。本章第二阶段会在这个认知基础上再实现真实 MCP Client。
​        如果被问到“resources 和 prompts 有什么意义”，可以回答：resources 用来让 Server 暴露可读取上下文，例如文件、数据库记录或网页内容；prompts 用来让 Server 提供提示词模板，帮助 Host 构造更稳定任务输入。它们让 MCP 不只是动作调用协议，也能承载上下文和任务模板。

### 21.2.10 运行验证
​        本阶段的验证重点是三个接口是否能返回预期结构，以及错误是否清晰暴露。因为本阶段没有真实 MCP Server，所以不需要配置外部进程，也不需要申请凭据。

#### 21.2.10.1 检查后端代码
​        先确认 MCP 入门服务、Schema 和路由都存在：

```PowerShell
rg -n "McpIntroService|McpConceptsResponse|/demo/tools|/demo/call" api/app
```

​        输出中应该能看到 `mcp_intro_service.py`、`schemas/mcp.py` 和 `routes/mcp.py` 里的关键类和接口。再检查主路由是否引入并注册了 `mcp.router`，否则接口文件存在也不会对外暴露。

#### 21.2.10.2 启动服务
​        启动后端和网关：

```PowerShell
docker compose up --build
```

​        如果本地已经有服务在运行，可以只重建 API 容器，但要确保新路由已经被加载。路由注册类改动通常需要重启后端进程。

#### 21.2.10.3 验证 MCP 概念接口
​        调用概念接口：

```Bash
curl http://localhost:8088/api/mcp/concepts
```

​        响应里应该包含 `roles`、`capabilities`、`transports` 和 `protocol`。`roles` 中应该有 Host、Client、Server，`capabilities` 中应该有 tools、resources、prompts。看到这些字段，说明概念服务和 Schema 转换都已经打通。

#### 21.2.10.4 验证工具发现接口
​        调用工具发现接口：

```Bash
curl http://localhost:8088/api/mcp/demo/tools
```

​        响应中应该看到 `mcp_echo` 和 `mcp_add_note`，并且每个工具都有 `input_schema`。这一步模拟的就是真实 MCP Client 发起 `tools/list` 后拿到的工具描述。

#### 21.2.10.5 验证工具调用接口
​        调用 `mcp_echo`：

```Bash
curl -X POST http://localhost:8088/api/mcp/demo/call \
  -H "Content-Type: application/json" \
  -d '{"tool_name":"mcp_echo","arguments":{"text":"hello mcp"}}'
```

​        响应中应该看到 `content` 里包含 `echo: hello mcp`，steps 中依次出现 `tools/list`、`tool selection`、`tools/call` 和 `content response`。这说明模拟调用流程已经完整。

#### 21.2.10.6 验证错误暴露
​        再故意传入不存在的工具名：

```Bash
curl -X POST http://localhost:8088/api/mcp/demo/call \
  -H "Content-Type: application/json" \
  -d '{"tool_name":"missing_tool","arguments":{}}'
```

​        这时应该返回工具不存在的错误，而不是悄悄调用其他工具。再调用 `mcp_echo` 但不传 `text`，也应该看到参数缺失错误。这个验证能证明演示服务没有把调用错误吞掉。

### 21.2.11 阶段小结
​        本阶段用确定性后端接口完成了 MCP 入门。我们新增了 `McpIntroService`，解释 Host、Client、Server 三个角色和 tools、resources、prompts 三类能力；又用 `mcp_echo` 和 `mcp_add_note` 模拟了工具发现与工具调用；最后通过 `/api/mcp/concepts`、`/api/mcp/demo/tools` 和 `/api/mcp/demo/call` 把这些内容暴露出来。
​        这章真正重要的不是代码量，而是边界感。Host 负责 AI 应用体验和工具选择，Client 负责连接 MCP Server，Server 负责暴露能力。`tools/list` 让 Host 发现工具，`tools/call` 让 Host 调用工具，content response 让结果回到 Agent 执行和观察体系。理解了这些，本章第二阶段接真实 MCP 工具时就会顺很多。
​        也就是说，本阶段是在为后面的真实接入建立统一语言。读者现在已经知道外部能力不会直接越过 Host 进入页面，而是要先被 Client 发现，再被转换成项目内部可以执行和观察的工具。这个认识会贯穿后面的 MCP 工具接入、A2A 工具接入以及多 Agent 协作编排。

### 21.2.12 代码索引
​        本阶段源码可以按顺序阅读 `api/app/application/mcp_intro_service.py`、`api/app/schemas/mcp.py`、`api/app/api/routes/mcp.py` 和 `api/app/api/router.py`。第一份文件解释 MCP 入门概念并模拟流程，第二份文件固定 API 响应模型，第三份文件提供 HTTP 入口，第四份文件把 MCP 路由挂进主 API。这个阅读顺序和本阶段叙述一致，从应用服务到对外接口，能更清楚地看到一条入门演示链路是如何落到代码里的。

## 21.3 第二阶段：MCP 工具入列

### 21.3.1 本阶段目标
​        本章第一阶段用确定性接口讲清了 MCP 的角色和流程，但它仍然停留在概念演示层。真正把 MCP 放进 Agent 工作台时，系统要面对的就不只是 Host、Client、Server 这几个名词，而是配置从哪里来、连接怎么创建、工具怎样发现、调用结果如何进入事件流、前端又如何展示这些外部能力。本阶段的目标，就是把 MCP 从“可以解释”推进到“可以接入”。
​        本阶段会新增 MCP 配置文件、配置加载器、领域对象、Client 管理器、应用服务、HTTP 接口、`mcp_call` AgentTool 和前端 MCP 面板。完成以后，后端可以读取 `api/config/mcp.yaml`，列出已配置 Server，发现 `demo` Server 暴露的工具，并通过 `/api/mcp/call` 调用工具。Agent 执行计划时，如果任务里出现 MCP 或外部系统相关意图，也可以通过 `mcp_call` 走同一套 `tool_called` 事件链路。
​        这一阶段仍然保持谨慎的实现边界。`demo` transport 是完整可运行的演示通道；`streamable_http` 和 `stdio` 实现最小 JSON-RPC 的 `tools/list` 与 `tools/call`；`sse` 则明确返回 501，说明它需要长连接会话管理，当前章不假装已经支持完整生命周期。读者要看到的不只是“能调工具”，还要看到一个工程项目在扩展协议能力时怎样把边界写清楚。

### 21.3.2 最终效果
​        本阶段结束后，后端会在本章第一阶段入门接口之外新增三组真实接入接口：

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

### 21.3.3 本阶段要解决的问题
​        本章第一阶段已经说明，MCP Host 负责承载 AI 应用，MCP Client 负责连接某个 Server，MCP Server 负责暴露 tools、resources 和 prompts。但在真实项目里，理解角色还不够。一个 Agent 产品必须回答更细的问题：Server 配置是否可以调整，传输方式是否可以扩展，工具发现是否能跨多个 Server，调用失败能否清楚暴露，工具结果是否能进入当前事件流，前端是否能看到外部工具状态。
​        如果这些问题不处理，MCP 接入很容易退化成一个临时接口。比如把 `demo` 工具直接写在路由里，短期能跑；但一旦要接 stdio Server 或 HTTP Server，就会继续复制代码。再比如后端能调用工具，但没有把结果包装成 `tool_called` 输出，用户在工作台里就看不到 Agent 到底调用了什么。又比如前端只展示调用结果，不展示已配置 Server 和工具列表，排查时就不知道问题发生在配置、发现还是调用阶段。
​        因此，本阶段要做一条完整闭环：配置声明 MCP Server，后端读取并校验配置，Client 管理器按 transport 创建连接对象，应用服务暴露 Server、工具和调用能力，API 路由把能力开放给前端和调试命令，AgentTool 把 MCP 调用放进工具注册表，前端再把 MCP 状态和结果放进工具预览面板。只有这条链路都打通，MCP 才算真正进入项目。

### 21.3.4 本阶段技术方案
​        本阶段的技术方案分成后端接入线和前端观察线。后端接入线从 `api/config/mcp.yaml` 开始，经过 `McpConfig`、`McpClientManager`、`McpService`、API 路由和 `mcp_call` AgentTool；前端观察线从 `/api/mcp/servers` 与 `/api/mcp/tools` 开始，经过 `mcp-api.ts`、页面状态、`ChatWorkspace`、`ToolPreviewPanel` 和 `McpPanel`，最终展示到右侧工作台。
​        后端不会让路由直接读 YAML，也不会让 AgentTool 直接创建 HTTP 请求。配置加载、传输实现、应用语义和工具注册各有位置。`mcp_config.py` 只负责读取和校验配置；`infrastructure/mcp/client.py` 只负责不同 transport 的连接和 JSON-RPC 消息；`McpService` 只负责向上提供 list servers、list tools、call tool 三个应用能力；`agent_tools/mcp.py` 只负责把 MCP 调用封装成当前 Agent 工具协议能理解的 `mcp_call`。
​        前端也不让 MCP 面板自己到处请求接口。页面层 `page.tsx` 负责加载 MCP Server 和工具状态，`ChatWorkspace` 负责把状态和刷新回调传给右侧工作区，`ToolPreviewPanel` 负责把 MCP 面板放进环境页签，并解析工具调用结果。这样 MCP 的前端展示保持在第 19 章建立的工具预览体系中，不会变成一个孤立的新卡片。

### 21.3.5 新增和修改的文件
​        本阶段涉及的文件比较多，但可以按职责分组阅读。配置入口包括：

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

​        文档说明包括 `README.md`、`api/README.md` 和 `docs/course/chapters/32-mcp-tools.md`。读者读代码时不要被文件数量吓住，本阶段的核心路径其实只有一条：配置 Server，发现工具，调用工具，注册 AgentTool，展示结果。

### 21.3.6 实施步骤
​        实施时要从配置文件开始。MCP Server 是外部能力来源，不能继续写死在 Python 函数里。配置文件定义 Server 名称、是否启用、传输方式、命令或 URL，后端再按配置创建对应 Client。这样后续新增外部 Server 时，主项目不用改大量业务代码。

#### 21.3.6.1 配置 MCP Server
​        本阶段新增 `api/config/mcp.yaml`。它先定义全局 MCP 开关和默认 Server，然后定义多个 Server。

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

​        `demo` 是本阶段默认启用的内置 Server。它不依赖外部进程，适合验证整个链路。`example_stdio` 和 `example_http` 默认关闭，是为了给读者展示真实 Server 配置形态，但不让一个未替换的示例命令影响本地启动。这个设计很重要：示例配置可以存在，但不能在默认状态下制造失败。
​        `.env.example` 和 Compose 中新增 `MCP_CONFIG_PATH`，默认指向 `config/mcp.yaml`。这样本地开发和容器运行都能读取同一份配置路径。后续私有化部署时，也可以通过环境变量把配置文件换成挂载目录里的版本。

#### 21.3.6.2 读取并校验 MCP 配置
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

#### 21.3.6.3 定义 MCP 领域对象
​        本阶段新增 `api/app/domain/mcp/entities.py`，用三个 dataclass 表示项目内部的 MCP 概念。

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

#### 21.3.6.4 编写 McpService
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

#### 21.3.6.5 抽象传输层 Client
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

#### 21.3.6.6 实现 DemoMcpTransportClient
​        `DemoMcpTransportClient` 是本阶段最重要的可运行通道。它模拟真实 MCP Server 的 `tools/list` 和 `tools/call`，但不需要外部进程。

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
​        这个 demo 不是“假装真实连接”，而是本阶段的内置 Server。它明确使用 `transport: demo`，前端也会显示它的 transport。读者可以用它验证配置、工具发现、工具调用、AgentTool、事件和 UI 结果，等链路跑通以后再启用真实 stdio 或 HTTP Server。

#### 21.3.6.7 实现 Streamable HTTP 最小客户端
​        `StreamableHttpMcpTransportClient` 使用 HTTP POST 发送 JSON-RPC 请求。本阶段先实现两个核心方法：`tools/list` 和 `tools/call`。

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
​        这不是完整生产级 MCP HTTP 客户端。真实 Server 可能涉及初始化、会话、通知和更多生命周期细节。本阶段先把最关键的工具发现和调用落到项目结构里，确保后续有扩展点，而不是一次性把所有协议细节都压进教学章节。

#### 21.3.6.8 实现 stdio 最小客户端
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

​        这种实现适合课程理解协议，不适合长连接生产场景。真正的 stdio MCP Client 通常需要长期维护子进程、初始化握手、并处理多条消息。本阶段刻意写成“每次调用启动一次命令”的最小模型，是为了让读者先看懂 JSON-RPC 输入和输出的关系。
​        命令缺失、启动失败、超时、进程返回非零状态、JSON-RPC error，都会以明确异常返回。这里同样不做静默失败。MCP 是外部能力接入边界，失败原因必须尽早暴露，否则前端只看到“没有工具”时无法判断是命令没配、进程崩了，还是 Server 返回了协议错误。

#### 21.3.6.9 明确 SSE transport 边界
​        代码里也定义了 `SseMcpTransportClient`，但它没有假装实现完整 SSE。它继承自 HTTP 客户端，并重写 `_send_json_rpc()`，直接返回 501。

```Python
raise AppException(
    message="MCP SSE transport requires long-lived session management; use streamable_http or demo in this chapter.",
    code=501,
    status_code=501,
)
```

​        这一步很符合工程实践。早期 SSE 传输需要长连接会话管理和消息端点配合，如果当前章没有实现，就应该明确告诉用户，而不是返回一个看似成功的空结果。对教程来说，这也是一个重要示范：边界可以有限，但必须诚实。

#### 21.3.6.10 编写 McpClientManager
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

​        这就是本阶段后端的核心分发点。未来增加新的 transport 或更完整的连接池时，优先改这里，而不是让路由、应用服务和 AgentTool 分别判断 transport。管理器把“按配置找到正确 Client”这件事集中起来，系统边界会更清楚。

#### 21.3.6.11 扩展 MCP API Schema 和路由
​        本章第一阶段已经有 MCP 概念和 demo 接口。本阶段继续在 `schemas/mcp.py` 中增加真实接入相关响应。

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

#### 21.3.6.12 注册 mcp_call AgentTool
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

​        本阶段先使用一个通用 `mcp_call`，而不是把每个发现到的 MCP 工具都动态展开成独立 AgentTool。原因是当前项目的工具选择还处在教学阶段，动态工具 schema、模型选择和权限控制会在后面增强。先用 `server_name + tool_name + arguments_json` 打通通用入口，更容易验证链路。
​        `_format_mcp_result()` 会把 `McpToolResult` 转成前端可识别的 JSON 字符串，其中 `kind` 固定为 `mcp_tool_result`。这延续了前面浏览器截图和搜索结果的设计：事件层保存字符串，前端通过 `kind` 判断如何渲染。

#### 21.3.6.13 接入内置工具注册表和 ReAct
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

​        这一阶段的 ReAct 参数仍然是教学型固定参数。它的作用是让用户在前端发一个包含 MCP 意图的任务时，能稳定看到一次 MCP 工具调用事件。后续模型工具选择增强后，`server_name`、`tool_name` 和参数应该由模型根据工具 schema 生成，而不是写死在规则里。现在先把执行链路打通，是合理的阶段性选择。

#### 21.3.6.14 前端读取 MCP Server 和工具
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

#### 21.3.6.15 新增 McpPanel
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

#### 21.3.6.16 渲染 MCP 工具结果
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

### 21.3.7 关键理解
​        本阶段最重要的理解，是 MCP 接入不是把外部工具接口硬塞进项目，而是把外部工具适配到已有 Agent 工具体系里。配置文件声明 Server，Client 管理器负责连接，应用服务暴露能力，AgentTool 统一执行，事件流记录输出，前端工具预览负责观察。这条链路完整以后，外部工具才真正变成 Agent 的一部分。
​        第二个关键点是 transport 要有清晰边界。`demo` 是本阶段稳定验证通道，`streamable_http` 和 `stdio` 是最小 JSON-RPC 实现，`sse` 只识别配置并明确返回未支持。有限支持不可怕，假装支持才会制造调试成本。尤其是 MCP 这种跨进程或跨网络协议，一旦错误被吞掉，排查会非常困难。
​        第三个关键点是 `mcp_call` 是阶段性设计。本阶段先用一个通用工具打通链路，避免过早引入动态工具展开、权限策略和模型工具选择。等后面模型能基于工具 schema 选择工具时，再把 MCP Server 发现到的工具展开成更细粒度的可选项。工程上先闭环，再增强智能选择。
​        第四个关键点是 MCP 工具要同时满足“机器可调用”和“用户可观察”。只让 Agent 能调用外部工具还不够，用户需要知道当前配置了哪些 Server、哪些 Server 被启用、发现到了哪些工具、具体一次调用传入了什么参数、Server 返回了什么 content。否则 MCP 能力会变成后端黑盒，任务失败时只能猜测。第 19 章搭好的工具预览面板在这里发挥了作用，它把环境状态和调用结果分开展示，让用户既能在执行前看可用能力，也能在执行后看调用证据。
​        第五个关键点是配置和运行时行为要保持一致。`api/config/mcp.yaml` 不是写给文档看的，它真实决定了 `/api/mcp/servers`、`/api/mcp/tools` 和 `mcp_call` 的行为。启用一个 Server，就意味着工具发现会尝试连接它；禁用一个 Server，就意味着它不会进入默认工具列表。这个关系越直接，后续部署时越容易把问题定位到配置文件，而不是在代码里到处找硬编码。

### 21.3.8 技术难点与亮点
​        本阶段的第一个难点是分层。配置、传输、应用服务、API 路由、AgentTool 和前端展示都参与了 MCP 接入，如果没有清晰边界，很容易出现一个文件知道所有事情的情况。当前实现把每层职责压得比较窄：配置负责声明，Client 负责通信，Service 负责语义，Tool 负责接入 Agent，Panel 负责展示。
​        第二个难点是错误暴露。配置文件缺失、默认 Server 未定义、Server 未启用、工具不存在、stdio 命令缺失、HTTP 请求失败、JSON-RPC error、SSE 未实现，这些都需要明确失败。对于外部工具协议来说，空结果往往比错误更危险，因为它让用户误以为没有工具，而不是配置或连接出了问题。
​        第三个亮点是前后端 `kind` 协议的延续。第 18 章的浏览器截图、第 20 章的搜索结果、本阶段的 MCP 工具结果，都使用结构化 JSON 字符串承载工具输出。事件模型保持简单，前端又能做富展示。这个模式后续还能支持更多外部工具结果类型。
​        第四个亮点是可验证路径完整。即使没有真实 MCP Server，读者也能用 `demo` transport 完成从配置读取到前端展示的完整验证。这个内置 Server 不隐藏自己的身份，也不模拟生产能力，只为验证链路服务。等链路成立后，再替换成真实 stdio 或 HTTP Server，排查成本会低很多。
​        第五个难点是工具发现的时机。本阶段的 `/api/mcp/tools` 会主动读取已启用 Server 的工具列表，这意味着前端刷新 MCP 面板时，后端确实会触发工具发现。这个设计能让用户看到当前可用工具的真实状态，但也要求外部 Server 不可用时错误要清楚返回。后续如果 Server 数量变多，可以再考虑缓存、异步刷新或按 Server 分批发现；本阶段先保持同步路径，目的是让行为和代码更容易对应。
​        第六个亮点是没有把 MCP 接入做成“只给后端调试用”的能力。很多项目在接外部工具时，会先停在 curl 能调用接口的阶段，然后前端和 Agent 执行链路迟迟没有接上。本阶段直接把 MCP Server 状态、工具发现、AgentTool 输出和工具结果卡片一起打通，读者能在同一个工作台里看到外部能力从配置到调用的完整路径。
​        第七个难点是命名和冲突。MCP 工具来自不同 Server，单独看工具名可能会重复，所以本阶段所有工具展示和结果输出都保留 `server_name`。前端展示成 `demo.mcp_echo`，后端调用也要求同时传 `server_name` 和 `tool_name`。这个细节看起来小，但它能避免后续多个 Server 都暴露 `search`、`read_file`、`create_issue` 这类常见工具名时产生歧义。

### 21.3.9 面试考点
​        如果面试官问“为什么 MCP Server 要放到 YAML 配置里”，可以回答：外部工具服务不应该写死在代码里。配置化以后，可以通过启用、禁用、修改 transport、命令或 URL 来接入不同 Server，而不必改 Agent 执行逻辑。配置加载器还可以在边界处校验必填字段，提前暴露错误。
​        如果被问到“为什么要有 McpTransportClient 抽象”，重点说明上层只需要 `list_tools` 和 `call_tool`，不应该关心底层是 demo、stdio 还是 HTTP。传输抽象让应用服务和 AgentTool 保持稳定，新增 transport 时主要改基础设施层和管理器。
​        如果被问到“为什么本阶段用通用 `mcp_call` 而不是动态注册每个 MCP 工具”，可以回答：当前阶段先验证 MCP 工具调用闭环，通用工具更容易接入已有 ReAct 规则。动态工具展开需要更完整的 schema 转换、权限管理、模型工具选择和冲突处理，适合后续增强。
​        如果被问到“为什么 SSE transport 返回 501”，要强调这是显式边界。SSE 需要长连接会话管理，本阶段没有实现完整生命周期，所以应该明确告诉调用方当前不支持，而不是返回空结果或假装成功。
​        如果被问到“MCP 结果如何在前端展示”，可以回答：AgentTool 把 `McpToolResult` 格式化成带 `kind=mcp_tool_result` 的 JSON 字符串，事件流保存这个字符串，`ToolPreviewPanel` 解析 `kind` 后渲染 MCP 结果卡片，展示 Server、工具名、参数和 content。

### 21.3.10 运行验证
​        本阶段验证要分后端配置、接口、AgentTool 和前端四层进行。只验证 `/api/mcp/call` 成功还不够，因为 MCP 的目标是进入 Agent 工作台。

#### 21.3.10.1 检查配置文件
​        先确认配置路径和 YAML 文件存在：

```PowerShell
rg -n "MCP_CONFIG_PATH|mcp_config_path" .env.example docker-compose.yml api/app/core/config.py
Get-Content api/config/mcp.yaml
```

​        配置里应该能看到 `demo` Server 启用，`example_stdio` 和 `example_http` 关闭。默认 Server 应该是 `demo`。

#### 21.3.10.2 检查后端代码
​        再确认核心类和接口存在：

```PowerShell
rg -n "McpClientManager|McpService|register_mcp_tools|mcp_tool_result" api/app
```

​        输出中应该能看到 Client 管理器、应用服务、AgentTool 注册和结果格式化逻辑。如果 `register_mcp_tools` 没有进入 `builtin.py`，Agent 执行时就找不到 `mcp_call`。

#### 21.3.10.3 启动服务
​        启动项目：

```PowerShell
docker compose up --build
```

​        如果改过 `api/config/mcp.yaml` 或环境变量，需要重启 API 容器。`load_mcp_config()` 使用缓存读取配置，运行中的进程不会自动重新加载文件。

#### 21.3.10.4 验证 Server 列表
​        调用 Server 列表接口：

```Bash
curl http://localhost:8088/api/mcp/servers
```

​        响应中应该能看到 `demo`、`example_stdio` 和 `example_http`，并能看到每个 Server 的 enabled、transport 和 description。这个接口验证的是配置加载和响应转换。

#### 21.3.10.5 验证工具发现
​        调用工具发现接口：

```Bash
curl http://localhost:8088/api/mcp/tools
```

​        默认情况下，响应里应该有 `demo.mcp_echo` 和 `demo.mcp_add_note`。如果这里失败，优先检查 `demo` 是否启用、`transport` 是否为 `demo`、配置路径是否正确。

#### 21.3.10.6 验证工具调用
​        调用 demo 工具：

```Bash
curl -X POST http://localhost:8088/api/mcp/call \
  -H "Content-Type: application/json" \
  -d '{"server_name":"demo","tool_name":"mcp_echo","arguments":{"text":"hello mcp"}}'
```

​        响应中的 content 应该包含 `echo: hello mcp`。再故意传入不存在的工具名，应看到明确的工具不存在错误。这样能证明调用错误没有被吞掉。

#### 21.3.10.7 验证 AgentTool
​        打开 Agent Core 工具列表，确认 `mcp_call` 已经注册：

```Bash
curl http://localhost:8088/api/agent-core/tools
```

​        然后在前端发送包含 MCP 或外部系统字样的任务，例如：

```Plain
请调用 MCP 外部工具做一次演示。
```

​        执行计划后，事件流里应该出现 `tool_called`，工具名为 `mcp_call`，输出中包含 `kind=mcp_tool_result`。

#### 21.3.10.8 验证前端展示
​        打开前端页面，进入右侧工具预览面板的“环境”页签，应该看到 MCP 工具面板。它会列出 Server 和已发现工具。执行包含 MCP 的任务后，工具页签中应该出现 MCP 工具结果卡片，展示 `demo.mcp_echo`、参数和返回 content。

### 21.3.11 阶段小结
​        本阶段完成了 MCP 工具接入的最小闭环。后端从 YAML 配置读取 MCP Server，使用 `McpClientManager` 按 transport 创建 Client，通过 `McpService` 暴露 Server、工具和调用能力，再通过 API 路由和 `mcp_call` AgentTool 接入现有执行链路。前端新增 MCP 状态读取、MCP 面板和 MCP 工具结果渲染，让外部工具既能被调用，也能被观察。
​        更重要的是，本阶段建立了一个可扩展模式。外部能力先被配置声明，再被 Client 发现，最后被适配成当前 Agent 能理解的工具输出。这个模式会继续支撑后面的 A2A 接入、多 Agent 协作和更复杂的工具选择策略。
​        和本章第一阶段相比，本阶段最大的变化是 MCP 不再只是概念说明。本章第一阶段的 demo 接口帮助读者理解协议流程，本阶段则让配置、发现、调用、AgentTool、事件和前端观察真正串起来。此后再接新的外部工具时，应该优先思考它落在这条链路的哪一层，而不是直接在业务代码里临时写一次调用。
​        这也是后续工程扩展的底座：先让外部能力进入统一工具协议，再讨论更复杂的调度、权限和模型选择。统一入口越稳定，后面替换 Server、增加工具或调整前端展示时，改动范围就越可控。

### 21.3.12 代码索引
​        本阶段源码可以按这条顺序阅读：先看 `api/config/mcp.yaml` 和 `api/app/core/mcp_config.py`，理解 Server 如何声明和校验；再看 `api/app/domain/mcp/entities.py`、`api/app/infrastructure/mcp/client.py` 和 `api/app/application/mcp_service.py`，理解工具发现与调用如何进入应用层；然后看 `api/app/infrastructure/agent_tools/mcp.py`、`builtin.py` 和 `react_agent_service.py`，理解 MCP 如何成为 AgentTool；最后看 `ui/app/lib/mcp-api.ts`、`ui/app/components/mcp-panel.tsx`、`tool-preview-panel.tsx` 和 `page.tsx`，理解前端如何展示 MCP 状态和结果。

## 21.4 本章小结

​        完成“MCP 协议初识”和“MCP 工具入列”两个阶段后，这条能力链已经形成闭环。读者仍然可以在每个阶段结束时单独运行验证，但理解上应把两者视作一个连续决策：先建立可靠边界，再让上层能力真正依赖它。

---

[← 第二十章. SearchTool 搜索能力成形](20-SearchTool%20搜索能力成形.md) · [返回目录](../README.md) · [第二十二章. 后端分层框架再造 →](22-后端分层框架再造.md)
