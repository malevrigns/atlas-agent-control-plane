<p align="center">
  <img src="./assets/readme/hero.svg" width="100%" alt="AtlasAgent turns agent tasks into a traceable timeline of evidence-backed memory, permissioned tools, artifacts, and validated checkpoints">
</p>

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-16-000000?logo=nextdotjs&logoColor=white)](https://nextjs.org/)
[![Electron](https://img.shields.io/badge/Electron-43-47848F?logo=electron&logoColor=white)](https://www.electronjs.org/)
[![Textual](https://img.shields.io/badge/TUI-Textual-7B2CBF)](https://textual.textualize.io/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)

[快速开始](#快速开始) · [核心能力](#核心能力) · [运行机制](#运行机制) · [三个客户端](#三个客户端) · [完整教程](tutorial/README.md)

</div>

## 把 Agent 从会话应用升级为可控系统

AtlasAgent 是一套可运行的 AI Agent 控制平面与中文工程教程。它把原始事件、长期记忆、工具调用、Artifact 和 Checkpoint 放进同一条可追溯链路，集中处理五个生产边界：**事实从哪里来、记忆为什么可信、工具何时允许执行、任务如何恢复，以及每一步如何审计。**

它不是只有一张聊天界面：同一套 FastAPI 控制平面同时服务 Next.js Web、Electron 时间线工作台与 Textual TUI，并配有从基础服务到 Memory / Tool Control Plane 的 **0–73 章教程**。

> [!NOTE]
> 当前版本是在课程 0–68 章基础上的 Control Plane 升级版。旧版 API 与 Web 工作流继续可用，新能力对应教程第 69–73 章。

## 已验证的交付基线

| 范围 | 结果 | 验证内容 |
| --- | ---: | --- |
| FastAPI 后端 | **38 项测试** | Memory、Checkpoint、Tool Runtime、兼容接口与边界条件 |
| Textual TUI | **3 项测试** | 启动、布局、审计视图与演示模式 |
| Electron 桌面端 | **构建 + 4 项测试** | 渲染器构建、打包适配与安全壳配置 |
| OpenAPI | **72 条路径** | 应用完整加载并成功生成接口规范 |
| Alembic | **完整迁移链** | 可生成离线 SQL，Control Plane 表结构可追踪 |

测试数量是当前仓库的交付快照，不是性能基准。复现命令见 [开发与验证](#开发与验证)。

## 核心能力

| 控制边界 | AtlasAgent 如何处理 | 关键机制 |
| --- | --- | --- |
| **Evidence-backed Memory** | 只把仍然有效、来源明确且通过门禁的事实注入上下文 | 类型化记忆、Write Gate、证据链、作用域、有效期、替代关系、可解释检索 |
| **Checkpoint DAG** | 为长任务提供可验证的暂停、恢复与回溯点 | 父子 Checkpoint、事件区间、状态哈希、环境指纹、校验报告 |
| **Unified Tool Runtime** | 在 handler 之前统一约束权限与副作用 | 风险分级、审批、幂等、超时、脱敏、大输出制品化、全程审计 |
| **Artifact Store** | 让日志、补丁、截图和报告成为稳定事实源 | SHA-256 内容寻址、来源引用、任务与 Checkpoint 关联 |
| **Multi-client Workspace** | 在浏览器、桌面驻留和 SSH 场景中观察同一运行状态 | Next.js Web、Electron、Textual TUI，共用 FastAPI 接口 |
| **Isolated Sandbox** | 把文件、Shell 与浏览器自动化限制在独立运行边界 | 工作区限制、输出限制、VNC / noVNC、统一网关 |

## 运行机制

```mermaid
flowchart TD
    subgraph Clients["客户端"]
        Web["Web · Next.js"]
        Desktop["Desktop · Electron"]
        TUI["TUI · Textual"]
    end

    Gateway["Nginx Gateway"]
    API["FastAPI Control Plane"]

    subgraph Runtime["Agent Runtime"]
        Planner["Planning & Events"]
        Tools["Tool Runtime"]
        Memory["Memory & Checkpoints"]
    end

    subgraph Data["事实与基础设施"]
        Postgres["PostgreSQL"]
        Redis["Redis"]
        Sandbox["Sandbox & Artifacts"]
    end

    Web --> Gateway
    Desktop --> API
    TUI --> API
    Gateway --> API
    API --> Planner
    API --> Tools
    API --> Memory
    Planner --> Redis
    Tools --> Sandbox
    Memory --> Postgres
```

控制面的事实优先级很明确：**原始事件与 Artifact 是事实源，任务状态是可重建的物化视图，Checkpoint 是经过验证的恢复点。**

一次任务会沿着这条链路推进：

1. 创建带目标和验收标准的结构化任务。
2. 从候选记忆中筛选有来源、未过期且相关的事实。
3. 工具进入统一 Runtime，先经过风险、权限和幂等检查，再执行 handler。
4. 大输出转为内容寻址 Artifact，调用过程写入审计记录。
5. 状态哈希、环境指纹和校验报告共同生成可恢复 Checkpoint。

## 快速开始

需要 Git、Docker 与 Docker Compose v2。

```bash
git clone https://github.com/malevrigns/atlas-agent-control-plane.git
cd atlas-agent-control-plane
cp .env.example .env
BUILD=true ./scripts/start.sh
```

启动后访问：

- Web 工作台：<http://localhost:8088>
- API 健康检查：<http://localhost:8088/api/status>
- 数据库状态：<http://localhost:8088/api/status/database>

Windows PowerShell：

```powershell
Copy-Item .env.example .env
docker compose up -d --build
```

再次启动不需要重新构建：

```bash
./scripts/start.sh
```

停止服务：

```bash
./scripts/stop.sh
```

如需同时清理 PostgreSQL、Redis 与上传文件卷：

```bash
CLEAN_VOLUMES=true ./scripts/stop.sh
```

> [!TIP]
> 默认网关端口为 `8088`。端口冲突时设置 `NGINX_PORT=18088` 后重新启动。

## 三个客户端

| 客户端 | 最适合 | 特色 |
| --- | --- | --- |
| **Web** | 浏览器协作与完整功能体验 | 会话、文件、Sandbox、设置、MCP、A2A 与 Agent 工作流 |
| **Desktop** | 长时间驻留与多面板观察 | Checkpoint 时间线、工具审计、暂停/恢复、Ink / Dawn / Contrast 三主题 |
| **TUI** | SSH、低带宽与键盘工作流 | 任务 / Checkpoint / 审计三栏、快捷键、三套终端主题、离线演示数据 |

桌面端默认启用 `contextIsolation` 并关闭 `nodeIntegration`；主题选择会在本地持久化。TUI 的快捷键与客户端配置见 [客户端指南](docs/CLIENTS.md)。

## Control Plane 最小调用

### 1. 创建结构化任务

```bash
curl -X POST http://localhost:8000/api/control-plane/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "title": "更新交付物",
    "goal": "完成可验证升级",
    "acceptance_criteria": ["测试通过"],
    "project_id": "atlas"
  }'
```

### 2. 通过统一 Runtime 调用工具

```bash
curl -X POST http://localhost:8000/api/agent-core/tools/draft_plan/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "arguments": {"task": "检查交付质量"},
    "project_id": "atlas",
    "allowed_permissions": [],
    "idempotency_key": "demo-001"
  }'
```

### 3. 回读工具审计

```bash
curl "http://localhost:8000/api/control-plane/tool-invocations?project_id=atlas"
```

完整数据模型、生命周期和接口说明见 [Memory 与 Tool Control Plane](docs/MEMORY_TOOL_CONTROL_PLANE.md)。

## 本地开发

先准备 PostgreSQL 与 Redis：

```bash
docker compose up -d postgres redis
```

| 模块 | 启动命令 | 默认地址 / 行为 |
| --- | --- | --- |
| API | `cd api && uv sync && uv run uvicorn app.main:app --reload` | `http://localhost:8000` |
| Web | `cd ui && pnpm install && pnpm dev` | `http://localhost:3000` |
| Desktop | `cd desktop && npm install && npm run electron:dev` | Electron 桌面窗口 |
| TUI | `cd tui && uv sync && ATLAS_API_URL=http://localhost:8000 uv run atlas-tui` | 后端不可达时自动进入演示模式 |

## 项目结构

```text
atlas-agent-control-plane/
├── api/          FastAPI 后端、迁移、Control Plane 与测试
├── ui/           Next.js Web 客户端
├── desktop/      Electron 桌面客户端
├── tui/          Textual 终端客户端
├── sandbox/      文件、Shell、浏览器与 VNC 沙箱服务
├── nginx/        统一网关配置
├── docs/         Control Plane 与客户端专题文档
├── tutorial/     0–73 章中文教程与配套图片
├── scripts/      一键启动和停止脚本
└── docker-compose.yml
```

进一步阅读：

- [整体架构](ARCHITECTURE.md)
- [API 架构](api/ARCHITECTURE.md)
- [API 依赖说明](api/DEPENDENCIES.md)
- [Memory / Tool Control Plane](docs/MEMORY_TOOL_CONTROL_PLANE.md)
- [Web、Desktop 与 TUI 客户端](docs/CLIENTS.md)
- [完整课程目录](tutorial/README.md)

## 开发与验证

```bash
# 后端测试
cd api
uv run python -m unittest discover -s tests

# TUI 测试
cd ../tui
uv run python -m unittest discover -s tests

# Desktop 构建与打包适配测试
cd ../desktop
npm run build
npm run test:sites
```

## 配置与安全

服务端常用配置集中在根目录的 [`.env.example`](.env.example)：

- `LLM_API_KEY`：模型服务密钥；未配置时仍可使用不依赖模型的演示与控制平面能力
- `NGINX_PORT`：统一网关端口，默认 `8088`
- `TOOL_AUTO_APPROVE_RISK`：工具自动批准的最高风险等级
- `TOOL_DEFAULT_TIMEOUT_SECONDS`：工具默认超时
- `TOOL_OUTPUT_INLINE_LIMIT`：大输出转为 Artifact 的阈值

客户端地址分别通过 `VITE_ATLAS_API_BASE`（Electron）和 `ATLAS_API_URL`（TUI）设置。

> [!IMPORTANT]
> 不要提交真实 `.env`、模型密钥或第三方服务凭据。生产环境应收紧 CORS、工具权限、自动审批阈值与 Sandbox 网络策略。

## 教程路线

教程从最小可运行服务逐步演进到完整控制平面：

1. FastAPI、Next.js、PostgreSQL 与 Redis 基础
2. 会话、流式消息、文件与上下文工程
3. Agent 规划执行、工具、MCP、A2A 与多 Agent 协作
4. Sandbox、浏览器自动化、可观测性、安全与 Harness
5. 类型化 Memory、Checkpoint DAG、Tool Runtime、Electron 与 TUI

从 [教程首页](tutorial/README.md) 开始，或直接阅读 [Control Plane 升级说明](docs/MEMORY_TOOL_CONTROL_PLANE.md)。

---

<div align="center">

**AtlasAgent · Build agents that can explain what they know, what they did, and how to recover.**

</div>
