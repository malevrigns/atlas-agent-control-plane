# API 架构说明

本文档说明后端 API 服务的当前分层结构。它不是教程步骤，而是后续维护代码时查阅的项目规则。

当前后端不是完整严格 DDD，也不是纯 CSR。更准确的定位是：

```text
简化 Clean Architecture + 领域模块逐步收敛
```

课程前期优先跑通端到端能力。随着 Session、Agent、Tool、Sandbox、MCP 等模块增多，再逐步把边界收敛清楚。

## 目录结构

```text
backend/api/
├── app/
│   ├── main.py                       # 应用入口：创建 FastAPI，注册中间件、异常处理和路由
│   ├── core/                         # 跨层通用能力：配置、异常、日志、配置文件读取
│   ├── presentation/                 # 表现层：把外部请求转换成应用服务调用
│   │   └── http/
│   │       ├── router.py             # 汇总注册所有 HTTP 路由
│   │       ├── sse.py                # SSE 编码辅助
│   │       └── routes/               # FastAPI 路由处理函数
│   │           ├── status.py
│   │           ├── sessions.py
│   │           ├── files.py
│   │           ├── config.py
│   │           ├── llm.py
│   │           ├── mcp.py
│   │           ├── sandboxes.py
│   │           ├── agent_core.py
│   │           └── agent_thinking.py
│   ├── schemas/                      # Pydantic DTO：请求模型和响应模型
│   ├── application/                  # 应用服务：业务用例编排、事务边界、任务流程
│   ├── domain/                       # 领域层：实体、值对象、协议和核心抽象
│   └── infrastructure/               # 基础设施：数据库、Redis、外部服务、工具适配器
├── config/                           # YAML 配置：llm.yaml、mcp.yaml
├── migrations/                       # Alembic 数据库迁移
├── ARCHITECTURE.md                   # 后端架构规则
├── DEPENDENCIES.md                   # 后端依赖说明
└── pyproject.toml
```

如果用更接近通用 FastAPI 项目的说法对照，可以这样理解：

```text
通用示例里的 api/v1/endpoints           -> 本项目 app/presentation/http/routes
通用示例里的 services           -> 本项目 app/application
通用示例里的 models             -> 本项目 app/infrastructure/database/models
通用示例里的 repositories       -> 本项目 app/infrastructure/repositories
通用示例里的 schemas            -> 本项目 app/schemas
通用示例里的 core               -> 本项目 app/core
```

本项目没有把 SQLAlchemy 模型直接放在 `app/models`，是因为它们属于数据库实现细节，所以放在 `infrastructure/database/models`。这样领域层不会被 ORM 绑定。

## 分层职责

### `app/main.py`

应用入口。

负责创建 FastAPI 实例、注册中间件、注册异常处理器、注册 HTTP 路由和启动后台任务生命周期。

不要把业务逻辑写在这里。

### `app/core`

跨层通用基础设施。

适合放：

- 全局配置。
- 日志配置。
- 统一异常。
- 全局异常处理。
- MCP、LLM 等配置读取入口。

不适合放具体业务流程。

### `app/presentation/http`

HTTP 表现层，也就是 FastAPI 路由层。

适合放：

- `router.py`：统一注册所有 HTTP 路由。
- `routes/`：具体接口处理函数。
- `sse.py`：HTTP/SSE 协议编码辅助。

这一层只负责把 HTTP 请求转换成应用服务调用，再把应用服务结果转换成 HTTP 响应。

不要在这里直接写复杂业务逻辑，也不要在这里直接操作数据库模型。

### `app/schemas`

请求和响应 DTO。

适合放：

- Pydantic 请求模型。
- Pydantic 响应模型。
- 统一响应结构。

`schemas` 面向接口输入输出，不等同于数据库模型，也不等同于领域实体。

### `app/application`

应用服务层。

适合放：

- 会话创建、发送消息、生成计划、执行计划等业务用例。
- 多个 Repository、外部 Client、工具调用之间的编排。
- 事务边界控制。

这一层回答“这个业务动作应该按什么顺序完成”。

注意：`SessionService`、`McpService` 这类类名里的 `Service`，目前表示“应用服务”，不是严格 DDD 中的“领域服务”。它们负责用例编排，例如校验输入、调用 Repository、调用外部 Client、提交事务、写事件。

### `app/domain`

领域层。

适合放：

- 领域实体。
- 值对象。
- 领域协议。
- Agent、Tool、MCP、Search 等核心抽象。

这一层应该尽量少依赖 FastAPI、SQLAlchemy、Redis、HTTP Client 等外部框架。

随着项目继续演进，`domain` 会逐步按业务领域收敛，而不是把所有概念放在一个大目录里。

### `app/infrastructure`

基础设施适配层。

适合放：

- SQLAlchemy 模型和数据库 Session。
- Repository 实现。
- Redis 队列实现。
- LLM、Sandbox、Search、MCP 等外部服务 Client。
- AgentTool 的具体注册和适配。

这一层回答“如何和外部系统打交道”。

### `config`

后端配置文件目录。

适合放：

- `llm.yaml`
- `mcp.yaml`

敏感信息不要写进这些 YAML 文件，应该通过环境变量注入。

### `migrations`

Alembic 数据库迁移目录。

数据库表结构变化必须通过迁移文件记录，不能只改 SQLAlchemy 模型。

## Import 方向

推荐方向：

```text
presentation/http -> application -> domain
application       -> domain
infrastructure    -> domain
application       -> infrastructure
```

需要避免：

```text
domain -> presentation/http
domain -> infrastructure
domain -> FastAPI
domain -> SQLAlchemy
```

领域层越干净，后续替换数据库、HTTP 框架或外部服务时成本越低。

## 领域划分规划

当前项目会逐步形成下面几类领域边界。

这些边界不是要求每个领域立刻都有完整的 `entities/services/repositories` 目录，而是后续新增代码时的归属方向。

### Session Domain

对应当前：

```text
app/domain/sessions
app/application/session_service.py
```

负责：

- 会话。
- 消息。
- 事件。
- 会话文件关联。
- 未读数。
- 会话状态。

会话不是技术基础层，而是业务领域。它承载用户与 Agent 的交互上下文，所以几乎所有任务都会关联会话。

### Agent Runtime Domain

对应当前：

```text
app/domain/agent_core
app/application/planner_service.py
app/application/react_agent_service.py
app/application/agent_task_runner.py
```

负责：

- Planner。
- ReAct。
- TaskRunner。
- 计划和步骤。
- 任务状态。
- Agent 运行事件。

这是后续最需要继续收敛的领域。最终 Runner 对齐时，会把任务执行循环、事件输出、工具调用和停止/恢复逻辑整理得更清楚。

### Tool Domain

对应当前：

```text
app/domain/agent_core/tools.py
app/infrastructure/agent_tools
```

负责：

- 工具定义。
- 工具参数。
- 工具注册。
- 工具调用。
- 工具结果格式。

File、Shell、Browser、Search、MCP、A2A 最终都应该以统一工具协议进入 Agent Runtime。

### Sandbox Domain

对应当前：

```text
app/infrastructure/sandbox
app/presentation/http/routes/sandboxes.py
```

负责：

- 沙箱实例。
- 沙箱健康等待。
- 文件、Shell、Browser 代理。
- 沙箱生命周期。

当前 Sandbox 更多还是基础设施适配。后续如果支持多沙箱、多任务隔离、生命周期策略，可以把领域对象进一步提升到 `domain/sandbox`。

### File Domain

对应当前：

```text
app/domain/files
app/infrastructure/storage
app/application/file_service.py
```

负责：

- 上传文件。
- 会话附件。
- 文件元数据。
- 文件预览。
- 本地存储和对象存储适配。

文件既是用户输入，也可能是工具产物。

### Integration Domain

对应当前：

```text
app/domain/llm
app/domain/search
app/domain/mcp
app/infrastructure/llm
app/infrastructure/search
app/infrastructure/mcp
```

负责：

- LLM Provider。
- Search Provider。
- MCP Server。
- 后续 A2A Remote Agent。

这些模块的共同点是“连接外部能力”。它们通常会有 domain 协议和 infrastructure 适配实现。

### Configuration Domain

对应当前：

```text
app/core/config.py
app/core/mcp_config.py
config/llm.yaml
config/mcp.yaml
```

负责：

- 应用环境变量。
- LLM 配置。
- MCP 配置。
- 后续 A2A 配置。

当前配置仍放在 `core` 和 `config` 中。第 36 章设置面板会继续整理配置读写边界。

## 和 DDD 的关系

DDD 通常会围绕限界上下文划分模块，例如订单、支付、库存、用户。

当前项目的业务不是电商类固定流程，而是 Agent 执行平台。它的核心限界上下文更像：

```text
会话上下文
Agent 运行上下文
工具上下文
沙箱执行上下文
外部集成上下文
```

因此本项目不会机械套用“每个业务都有一套 controller/service/repository/model”的目录。

更合适的做法是：

```text
先保持清晰依赖方向
再在领域复杂度上来时按上下文收敛
```

这也是为什么本章先重命名 `presentation/http`，再通过文档明确后续领域拆分方向。

## 新增功能放哪里

- 新增接口：放到 `app/presentation/http/routes/`。
- 新增请求/响应模型：放到 `app/schemas/`。
- 新增业务流程：放到 `app/application/`。
- 新增领域概念或协议：放到 `app/domain/`。
- 新增数据库表模型：放到 `app/infrastructure/database/models/`。
- 新增 Repository 实现：放到 `app/infrastructure/repositories/`。
- 新增外部服务 Client：放到 `app/infrastructure/` 下对应子目录。
- 新增工具适配：放到 `app/infrastructure/agent_tools/`。

## 常见错误

不要在 Route 里直接写复杂业务逻辑。

不要让 SQLAlchemy 模型穿透到前端响应。

不要把 HTTP 请求对象传进领域层。

不要让领域实体依赖 FastAPI、Pydantic Settings 或数据库 Session。

不要为了省文件把多个不同职责的代码堆到一个模块里。

## 为什么使用 `presentation/http`

外层 `backend/api/` 是 monorepo 中的后端服务目录。

旧目录 `backend/api/app/api/` 在技术上可用，但容易让读者混淆“服务目录”和“HTTP 接口层”。

现在改为：

```text
backend/api/app/presentation/http/
```

含义更明确：

- `backend/api/`：后端服务。
- `presentation/http/`：后端应用的 HTTP 表现层。

后续如果新增 CLI、WebSocket 或其他入口，也可以放到 `presentation/` 下的其他目录中。
