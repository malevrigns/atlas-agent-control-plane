# AtlasAgent 整体架构说明

本文档说明项目整体架构。它面向长期维护，不替代课程章节。

课程章节负责解释“为什么现在这样演进、如何一步步实现”；本文档负责沉淀“当前项目整体怎么分层、各服务负责什么、后续应该如何继续扩展”。

## 总体结构

先看项目目录地图：

```text
atlas-agents/
├── frontend/
│   ├── web/                 # Next.js 浏览器工作台
│   ├── desktop/             # Electron Checkpoint 时间线客户端
│   └── tui/                 # Textual 键盘优先终端客户端
├── backend/
│   ├── api/                 # FastAPI 主服务
│   │   ├── app/
│   │   │   ├── main.py      # FastAPI 应用入口
│   │   │   ├── core/        # 配置、异常、日志等跨层能力
│   │   │   ├── presentation/# HTTP/FastAPI 路由与 SSE 编码
│   │   │   ├── schemas/     # 请求和响应 DTO
│   │   │   ├── application/ # 业务用例编排与事务边界
│   │   │   ├── domain/      # 领域实体、协议和核心抽象
│   │   │   └── infrastructure/ # 数据库、外部服务与工具适配器
│   │   ├── config/          # LLM、Embedding、MCP、A2A 配置
│   │   └── migrations/      # Alembic 数据库迁移
│   └── sandbox/             # 文件、Shell、浏览器与 VNC 隔离环境
├── nginx/                   # 统一网关配置
├── docs/                    # 架构与客户端专题文档
├── tutorial/                # 0–56 章中文工程教程
├── scripts/                 # 启停与运行时配置脚本
├── docker-compose.yml       # 本地多服务编排
└── README.md
```

再看运行时调用关系：

```text
Web / Electron / TUI
  |
  v
Nginx Gateway / FastAPI
  |
  +-- UI Service
  |
  +-- API Service
  |     |
  |     +-- PostgreSQL (+ pgvector)
  |     +-- Redis
  |     +-- Qdrant (可选向量后端)
  |     +-- Sandbox Service
  |     +-- LLM Provider
  |     +-- Embedding Provider
  |     +-- Search Provider
  |     +-- MCP Server
  |     +-- A2A Remote Agent
  |
  +-- Sandbox VNC / Browser
```

## Agent Control Plane

升级版将 Agent 运行中的可变状态和可追溯事实分开：

```text
会话事件 / Tool Invocation
            |
            +----> Content-addressed Artifact
            |
            v
      Agent Task State
            |
            v
      Checkpoint DAG
            |
            +----> Environment Snapshot
            |
            v
   Typed Verified Memory
```

- 事件、工具审计和 Artifact 是事实源。
- `agent_tasks` 是可重建的物化状态，用版本号和状态哈希保护。
- Checkpoint 是带父关系、事件范围和校验报告的恢复点。
- 长期记忆必须通过 Write Gate，并保留作用域、证据、时效和替代关系。
- 工具调用统一经 Tool Runtime 执行权限、风险、审批、幂等、超时、脱敏和审计。

详细契约见 `docs/MEMORY_TOOL_CONTROL_PLANE.md`。

## 知识库与技能注册中心

除记忆之外，还有两类需要治理的上下文注入物：

```text
KnowledgeBase (冻结 embedding 配置)
      |
      +-- KnowledgeDocument (原文 + 摄取状态 + 内容指纹)
              |
              +-- KnowledgeChunk (检索正文事实源，带字符区间)
                      |
                      +-- Vector (VectorStore 协议：pgvector / Qdrant)

Skill (skill_key + semver)
      |
      +-- draft -> published(冻结) -> deprecated
              |
              +-- enabled 开关（与 status 正交，用于线上止血）
```

- 知识库在建库时冻结 embedding 模型与切分参数；换模型必须建新库重灌。
- 向量存储只保存 embedding 与回链 id，正文永远以 `knowledge_chunks` 为准。
- 检索只命中 `ready` 文档，命中结果带编号引用，可回溯到原文字符位置。
- 技能 `published` 后内容冻结，改内容必须派生新版本，保证行为可回溯到确定版本。
- 两者的检索/选择都写入可解释评分，RAG 检索复用 `retrieval_traces` 审计表。

详细契约见 `docs/RAG_AND_SKILLS.md`。

## 服务职责

### `backend/api`

后端主服务。

负责：

- 会话、消息、事件、文件等业务数据。
- Agent 规划、执行、任务状态和事件流。
- 工具注册和工具调用编排。
- 知识库摄取、切分、向量化与带引用检索。
- 技能注册中心的版本治理与上下文注入。
- LLM、Embedding、Search、MCP、A2A 等外部能力适配。
- Sandbox 创建、等待、代理和清理。

API 服务是系统的大脑，但不直接执行高风险命令，也不直接承载前端页面。

### `frontend/web`

前端工作台。

负责：

- 会话列表。
- AI 对话输入和消息时间线。
- 计划、步骤、任务状态展示。
- 文件、Shell、浏览器、搜索、MCP、A2A 等工具结果预览。
- 设置面板和运行状态观察。

UI 不直接访问数据库，也不直接访问 Docker 网络里的服务。浏览器统一经过 Nginx 网关访问。

### `backend/sandbox`

隔离执行环境。

负责：

- 文件读写。
- Shell 命令执行。
- Playwright 浏览器自动化。
- VNC 远程桌面画面。

Sandbox 是执行工具能力的环境边界。API 通过 HTTP 调用 Sandbox，不把高风险执行逻辑放在主 API 进程里。

### `nginx`

统一入口。

负责：

- `/` 转发到 UI。
- `/api` 转发到 API。
- `/sandbox-api` 转发到 Sandbox。
- `/sandbox-vnc` 转发 VNC/WebSocket。

浏览器只需要记住一个入口地址。

### `postgres`

结构化数据存储。

保存会话、消息、事件、文件元数据、任务状态等长期数据。

### `redis`

任务队列和运行时状态基础设施。

用于 Agent 后台任务、事件流和运行中状态协作。

## 后端架构定位

后端不是纯 CSR，也不是完整严格 DDD。

当前采用的是：

```text
简化 Clean Architecture + 领域模块逐步收敛
```

原因是 Agent 项目既有普通业务接口，也有很多跨领域能力：

- 会话和消息。
- Agent 计划和执行。
- 工具协议。
- 沙箱执行。
- 文件系统。
- 外部协议 MCP/A2A。
- 模型调用和上下文工程。

如果一开始强行做完整 DDD，目录会很重，读者也不容易理解。

所以课程前期先按能力闭环推进，后续在复杂度出现后逐步收敛边界。

当前后端详细规则见：

```text
backend/api/ARCHITECTURE.md
```

## 当前核心领域

后端后续会逐步收敛成这些核心领域模块：

```text
Session Domain
Agent Runtime Domain
Tool Domain
Sandbox Domain
File Domain
Integration Domain
Configuration Domain
```

### Session Domain

会话领域。

负责：

- 会话基本信息。
- 用户消息。
- 系统事件。
- 会话文件关联。
- 未读数和会话状态。

它是很多流程的基础，但不是“底层工具”。它是用户与 Agent 发生交互的业务边界。

### Agent Runtime Domain

Agent 运行领域。

负责：

- Planner。
- ReAct。
- TaskRunner。
- 任务状态。
- 步骤执行。
- Done、Wait、Error、Stop 等事件。

它是系统最核心的任务执行领域。

### Tool Domain

工具领域。

负责：

- 工具定义。
- 工具参数 schema。
- 工具注册表。
- 工具调用结果。
- 工具错误和重试边界。

File、Shell、Browser、Search、MCP、A2A 最终都要进入统一工具协议。

### Sandbox Domain

沙箱领域。

负责：

- 沙箱实例。
- 健康检查。
- 文件/Shell/Browser 代理。
- VNC 观察能力。
- 沙箱生命周期。

它解决“Agent 在哪里执行动作”的问题。

### File Domain

文件领域。

负责：

- 上传文件。
- 文件元数据。
- 文件预览。
- 文件下载。
- 本地存储和后续对象存储扩展。

它既服务用户附件，也服务工具执行产物。

### Integration Domain

外部集成领域。

负责：

- LLM Provider。
- Search Provider。
- MCP Server。
- A2A Remote Agent。

它解决“如何连接外部能力”的问题。

### Configuration Domain

配置领域。

负责：

- LLM 配置。
- MCP 配置。
- A2A 配置。
- 前端设置面板对应的配置读取和更新。

## 为什么 Session 不是“基础层”

会话确实被很多流程使用，但它不是技术基础设施。

技术基础设施是：

```text
数据库
Redis
HTTP Client
配置读取
日志
异常处理
```

会话是业务概念。

用户每次打开一个任务、发送消息、查看事件，都是围绕会话发生的。所以它应该属于 Session Domain，而不是放进 `core` 或基础设施层。

## 后续演进原则

### 先跑通闭环，再收敛边界

课程早期允许使用较简单的模块划分，让读者先看到结果。

当某类代码开始变多，例如工具、沙箱、外部集成，再把它收敛成更明确的领域模块。

### 不为架构而架构

如果一个模块只有一个文件，不急着拆成很多层。

当它开始承担多种职责，再拆分：

```text
entities
services
repositories
adapters
schemas
```

### 保持依赖方向清晰

越靠近业务核心，越少依赖框架。

越靠近外部世界，越负责适配框架、数据库、HTTP、Redis、Docker 等细节。

### 前端必须跟随产品形态收敛

早期演示 UI 不能一直堆在首页。

最终工作台要收敛为：

```text
左侧：会话
中间：AI 对话、计划、步骤、工具调用
右侧：工具预览、文件、浏览器、VNC、上下文、配置
```

## 文档维护规则

涉及整体架构变化时，更新：

```text
ARCHITECTURE.md
docs/course/outline.md
对应章节教程
```

涉及后端分层变化时，更新：

```text
backend/api/ARCHITECTURE.md
```

涉及后端依赖变化时，更新：

```text
backend/api/DEPENDENCIES.md
backend/api/pyproject.toml
backend/api/uv.lock
```

涉及前端交互最终形态时，更新：

```text
docs/course/outline.md
相关章节教程
```
