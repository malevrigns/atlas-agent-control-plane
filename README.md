# AtlasAgent

AtlasAgent 是一个从 0 到 1 构建的全栈 AI Agent 实战项目。本版已升级为以事件、制品和 Checkpoint 为事实源的 Agent Control Plane，并同时提供 Web、Electron 桌面客户端与键盘优先 TUI。

课程版项目会逐章实现：

- FastAPI 后端 API
- Next.js 前端界面
- Electron 多主题桌面工作台
- Textual 终端客户端
- PostgreSQL 数据库
- Redis 消息队列
- 独立 Sandbox 沙箱服务
- 浏览器自动化与 VNC 远程桌面
- Agent 规划与执行
- 文件、Shell、搜索、MCP、A2A 等工具能力
- 类型化记忆、证据链、失效/替代关系与可解释检索
- Checkpoint DAG、环境指纹、内容寻址 Artifact 和任务状态哈希
- 统一 Tool Runtime：风险、权限、审批、幂等、超时、脱敏、审计
- Docker Compose 与 Nginx 部署

## 当前版本

当前代码是课程 0–68 章之后的 Control Plane 升级版，对应新增教程第 69–73 章。原有 API 和 Web 界面保持可用，新实现集中在以下边界：

- 原始事件与 Artifact 是事实源，任务状态是可重建的物化视图。
- Checkpoint 用父子关系、事件覆盖区间、状态哈希和校验报告保证恢复安全。
- 长期记忆经 Memory Write Gate 进入 candidate/verified/superseded 生命周期，每次注入都返回来源和选中原因。
- Tool Runtime 在 handler 之前统一执行权限与风险策略，并对调用全程留下审计记录。

## 顶层目录

```text
api/       后端 API 服务
ui/        前端应用
desktop/   Electron 桌面客户端（Ink / Dawn / Contrast 三主题）
tui/       Textual 键盘优先终端客户端
sandbox/   沙箱服务
nginx/     生产网关配置
docs/      Control Plane 与客户端运行文档
```

## 课程文档

完整的 0–73 章课程大纲、章节文档和配套图片已收录在 [`tutorial/`](tutorial/README.md)。项目内的运行文档从 [Memory / Tool Control Plane](docs/MEMORY_TOOL_CONTROL_PLANE.md) 与 [客户端指南](docs/CLIENTS.md) 开始。

项目架构和后端依赖说明：

```text
ARCHITECTURE.md
api/ARCHITECTURE.md
api/DEPENDENCIES.md
```

## 运行命令

本地运行 API：

```bash
docker compose up -d postgres redis
cd api
uv venv --python 3.11
uv sync
uv run uvicorn app.main:app --reload
```

本地运行 UI：

```bash
cd ui
pnpm install
pnpm dev
```

本地运行 Electron 桌面客户端：

```bash
cd desktop
npm install
npm run electron:dev
```

构建桌面渲染器：

```bash
cd desktop
npm run build
```

本地运行 TUI：

```bash
cd tui
uv sync
ATLAS_API_URL=http://localhost:8000 uv run atlas-tui
```

后端未启动时，TUI 会自动进入内置演示模式。

## Control Plane 快速验证

```bash
curl -X POST http://localhost:8000/api/control-plane/tasks \
  -H "Content-Type: application/json" \
  -d '{"title":"更新交付物","goal":"完成可验证升级","acceptance_criteria":["测试通过"],"project_id":"atlas"}'

curl http://localhost:8000/api/control-plane/tasks?project_id=atlas
curl http://localhost:8000/api/control-plane/tool-invocations?project_id=atlas
```

工具经统一 Runtime 调用：

```bash
curl -X POST http://localhost:8000/api/agent-core/tools/draft_plan/invoke \
  -H "Content-Type: application/json" \
  -d '{"arguments":{"task":"检查交付质量"},"project_id":"atlas","allowed_permissions":[],"idempotency_key":"demo-001"}'
```

访问：

```text
http://localhost:3000
```

使用 Docker Compose 运行：

```bash
./scripts/start.sh
curl http://localhost:8088/api/status
curl http://localhost:8088/api/status/database
curl http://localhost:8088/api/sessions
curl http://localhost:8088/api/a2a/agents
curl http://localhost:8088/api/a2a/agents/demo_researcher/card
curl http://localhost:8088/api/multi-agent/roles
curl http://localhost:8088/api/config/app
curl http://localhost:8088/api/harness/cases
curl http://localhost:8088/api/acceptance/checks
curl http://localhost:8088/api/observability/checks
curl http://localhost:8088/api/security/checks
curl http://localhost:8088/api/memories
curl http://localhost:8088
docker compose ps
```

如果本机还没有 API 和 UI 镜像，可以执行完整构建：

```bash
BUILD=true ./scripts/start.sh
```

统一入口：

```text
http://localhost:8088
```

如果本机 `8088` 端口被占用：

```bash
NGINX_PORT=18088 docker compose up -d --no-build nginx
curl http://localhost:18088/api/status
```

停止服务：

```bash
./scripts/stop.sh
```

如果需要连数据库、Redis 和上传文件卷一起清理：

```bash
CLEAN_VOLUMES=true ./scripts/stop.sh
```

发送消息接口：

```bash
curl -N -X POST http://localhost:8088/api/sessions/{session_id}/messages/stream \
  -H "Content-Type: application/json" \
  -d '{"content":"帮我规划一个学习任务"}'
```

A2A 远程 Agent 调用接口：

```bash
curl -X POST http://localhost:8088/api/a2a/message/send \
  -H "Content-Type: application/json" \
  -d '{"agent_key":"demo_researcher","message":"请远程研究 Agent 帮我整理 A2A 工具接入要点"}'
```

多 Agent 协作接口：

```bash
curl http://localhost:8088/api/multi-agent/roles
curl -X POST http://localhost:8088/api/multi-agent/run \
  -H "Content-Type: application/json" \
  -d '{"task":"请让多个 Agent 分工协作，帮我制定一个功能上线计划并评审风险"}'
```

设置接口：

```bash
curl http://localhost:8088/api/config/app
curl -X PATCH http://localhost:8088/api/config/modules/mcp \
  -H "Content-Type: application/json" \
  -d '{"enabled":false}'
curl -X POST http://localhost:8088/api/config/integrations \
  -H "Content-Type: application/json" \
  -d '{"kind":"mcp","name":"custom_mcp","description":"本地新增的运行时集成","endpoint":"https://example.com/mcp"}'
```

Agent Harness 接口：

```bash
curl http://localhost:8088/api/harness/cases
curl -X POST http://localhost:8088/api/harness/cases/browser_observation/run \
  -H "Content-Type: application/json" \
  -d '{"mode":"simulate"}'
curl http://localhost:8088/api/harness/runs/{run_id}/replay
```

系统诊断接口：

```bash
curl -i http://localhost:8088/api/status
curl http://localhost:8088/api/observability/checks
```

长期记忆接口：

```bash
curl http://localhost:8088/api/memories
curl -X POST http://localhost:8088/api/memories \
  -H "Content-Type: application/json" \
  -d '{"kind":"user_preference","content":"用户希望代码保留详细分步注释","importance":5}'
curl -X POST http://localhost:8088/api/memories/extract \
  -H "Content-Type: application/json" \
  -d '{"session_id":"{session_id}"}'
curl http://localhost:8088/api/sessions/{session_id}/context
```

会话控制接口：

```bash
curl -X POST http://localhost:8088/api/sessions/{session_id}/stop
curl -X POST http://localhost:8088/api/sessions/{session_id}/read
```

上传文件接口：

```bash
curl -F "upload=@README.md" http://localhost:8088/api/files
curl http://localhost:8088/api/files/{file_id}
curl -OJ http://localhost:8088/api/files/{file_id}/download
curl http://localhost:8088/api/files/{file_id}/preview
curl -F "upload=@README.md" http://localhost:8088/api/sessions/{session_id}/files
curl http://localhost:8088/api/sessions/{session_id}/files
```

LLM 配置和调用接口：

```bash
curl http://localhost:8088/api/config/llm
curl -X POST http://localhost:8088/api/llm/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"你好"}]}'
```

Agent 思维模型接口：

```bash
curl http://localhost:8088/api/agent-thinking/modes
curl -X POST http://localhost:8088/api/agent-thinking/compare \
  -H "Content-Type: application/json" \
  -d '{"task":"帮我从 0 到 1 实现一个 AI Agent 项目"}'
```

MCP 入门接口：

```bash
curl http://localhost:8088/api/mcp/concepts
curl http://localhost:8088/api/mcp/demo/tools
curl -X POST http://localhost:8088/api/mcp/demo/call \
  -H "Content-Type: application/json" \
  -d '{"tool_name":"mcp_echo","arguments":{"text":"hello mcp"}}'
```

MCP 工具接入接口：

```bash
curl http://localhost:8088/api/mcp/servers
curl http://localhost:8088/api/mcp/tools
curl -X POST http://localhost:8088/api/mcp/call \
  -H "Content-Type: application/json" \
  -d '{"server_name":"demo","tool_name":"mcp_echo","arguments":{"text":"hello mcp"}}'
```

A2A 入门接口：

```bash
curl http://localhost:8088/api/a2a/concepts
curl http://localhost:8088/api/a2a/demo/agent-card
curl -X POST http://localhost:8088/api/a2a/demo/message \
  -H "Content-Type: application/json" \
  -d '{"message":"请远程研究 Agent 帮我整理 A2A 协议要点"}'
```

Agent 核心演示接口：

```bash
curl http://localhost:8088/api/agent-core/tools
curl -X POST http://localhost:8088/api/agent-core/demo \
  -H "Content-Type: application/json" \
  -d '{"task":"帮我拆解一个 Agent 工具调用流程","tool_name":"draft_plan"}'
curl -X POST http://localhost:8088/api/agent-core/demo \
  -H "Content-Type: application/json" \
  -d '{"task":"AI Agent latest news","tool_name":"search_web"}'
```

会话计划接口：

```bash
curl -X POST http://localhost:8088/api/sessions/{session_id}/plan \
  -H "Content-Type: application/json" \
  -d '{"task":"帮我规划一个 AI Agent 项目"}'
curl -X POST http://localhost:8088/api/sessions/{session_id}/plan/execute
curl -X POST http://localhost:8088/api/sessions/{session_id}/plan/tasks
curl http://localhost:8088/api/sessions/tasks/{task_id}
curl -X POST http://localhost:8088/api/sessions/tasks/{task_id}/cancel
curl http://localhost:8088/api/sessions/{session_id}/context
```

Sandbox 服务接口：

```bash
curl http://localhost:8088/sandbox-api/status
curl http://localhost:8088/sandbox-api/supervisor/services
curl http://localhost:8088/sandbox-api/files
curl -X POST http://localhost:8088/sandbox-api/files/write \
  -H "Content-Type: application/json" \
  -d '{"path":"notes/hello.txt","content":"hello sandbox"}'
curl "http://localhost:8088/sandbox-api/files/read?path=notes/hello.txt"
curl -X POST http://localhost:8088/sandbox-api/shell/sessions \
  -H "Content-Type: application/json" \
  -d '{"command":"pwd && ls -la"}'
curl http://localhost:8088/api/sandboxes/current
curl http://localhost:8088/api/agent-core/tools
curl http://localhost:8088/sandbox-api/browser/status
curl -X POST http://localhost:8088/sandbox-api/browser/session
curl -X POST http://localhost:8088/sandbox-api/browser/page/navigate \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com"}'
curl -X POST http://localhost:8088/sandbox-api/browser/page/screenshot \
  -H "Content-Type: application/json" \
  -d '{"full_page":true}'
curl -X POST http://localhost:8088/api/sandboxes/current/wait \
  -H "Content-Type: application/json" \
  -d '{"retries":3,"interval_seconds":1}'
curl -X POST http://localhost:8088/api/sandboxes/current/shell/run \
  -H "Content-Type: application/json" \
  -d '{"command":"pwd && ls -la"}'
curl http://localhost:8088/api/agent-core/tools
curl -X POST http://localhost:8088/api/agent-core/demo \
  -H "Content-Type: application/json" \
  -d '{"task":"pwd && ls -la","tool_name":"shell_run"}'
```

停止服务：

```bash
docker compose down
```
