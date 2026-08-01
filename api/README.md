# API 服务

这里实现 AtlasAgent 的后端 API 服务。

当前章节已经加入：

- FastAPI 应用入口
- `/api/status` 状态检查接口
- API 服务的 Dockerfile
- Docker Compose 中的 `api` 服务配置
- API 容器启动脚本 `api/scripts/start.sh`
- 容器启动时自动执行 Alembic 迁移
- pydantic-settings 配置读取
- 统一响应结构
- 统一异常处理
- CORS
- 基础日志
- SQLAlchemy 异步数据库连接
- Alembic 数据库迁移
- `sessions` 会话表模型
- 会话创建、列表和删除接口
- `session_messages` 消息表模型
- `session_events` 事件表模型
- 会话详情、消息列表、发送消息和事件列表接口
- SSE 消息流式接口
- 会话停止接口
- 清除未读数接口
- `files` 文件元数据表模型
- 文件上传、元数据查询和下载接口
- `session_files` 会话文件关系表模型
- 会话文件上传、列表和文本预览接口
- `FileStorage` 文件存储协议
- `LocalFileStorage` 本地存储实现
- YAML LLM 配置加载
- LLM 配置查询接口
- OpenAI 兼容聊天客户端
- Agent 思维模式说明接口
- Agent 思维模式任务对比接口
- 长期记忆领域模型和 Repository 协议
- `agent_memories` 长期记忆表
- 长期记忆新增、列表、更新、禁用和软删除接口
- 从会话消息和事件中抽取记忆候选
- 长期记忆相关度检索服务
- `MemoryContext` 上下文注入结构
- PlannerAgent 计划生成时注入相关长期记忆
- ReActAgent 工具执行时注入长期记忆提示
- 会话上下文接口返回本次注入的长期记忆
- `AgentRunnerService` 统一 Agent 主执行链路
- SSE 消息流、同步执行接口和 Redis 后台任务复用同一个 Runner
- `ModelToolSelectionService` 模型工具选择服务
- 工具 schema、短期上下文和长期记忆进入工具选择提示词
- 模型 tool call 失败时回退到确定性规则选择
- 工具参数缺失时执行最小参数修复
- 后台任务 `waiting/completed/stopped` 状态
- 失败或停止任务的重试接口
- 按会话恢复最近任务状态接口
- 工具装饰器和工具 schema
- 内置工具注册表
- Agent 核心演示接口
- PlannerAgent 计划生成服务
- `plan_created` 会话事件
- 会话计划接口
- ReActAgent 同步执行服务
- 步骤开始、工具调用、步骤完成和任务完成事件
- Redis Stream Agent 任务队列
- AgentTaskRunner 后台任务消费者
- 计划执行任务启动、查询和取消接口
- 会话上下文快照服务
- 消息裁剪、事件摘要和文件引用接口
- Sandbox 文件客户端
- Sandbox FileTool 工具注册
- Sandbox Shell 客户端
- Sandbox ShellTool 工具注册
- DockerSandbox 管理器
- Sandbox 健康等待和文件/Shell 代理接口
- Sandbox BrowserTool 工具注册
- Bing Search 适配器
- SearchTool 工具注册
- MCP 协议入门说明接口
- MCP tools/list 和 tools/call 演示接口
- MCP YAML 配置加载
- MCP Server 列表接口
- MCP 工具发现和调用接口
- MCP Client 管理器
- MCP AgentTool 工具注册
- `presentation/http` HTTP 表现层目录
- 后端架构说明文档 `ARCHITECTURE.md`
- 后端依赖说明文档 `DEPENDENCIES.md`
- A2A 协议入门说明接口
- A2A Agent Card 示例接口
- A2A message/send 演示接口
- A2A YAML 配置加载
- A2A 远程 Agent 列表接口
- A2A Agent Card 读取接口
- A2A message/send 真实调用接口
- A2A AgentTool 工具注册
- 多 Agent Manager / Worker / Reviewer 协作服务
- 多 Agent 角色列表和协作运行接口
- MultiAgentTool 工具注册
- 应用设置聚合接口
- 设置模块运行时启用/禁用接口
- 设置页运行时集成新增和删除接口
- Agent Harness 固定任务集
- Harness 模拟运行、基础断言和失败回放接口
- 请求 ID 中间件和 `X-Request-ID` 响应头
- 系统诊断清单接口
- 安全边界检查清单接口
- 配置、上传、Sandbox、外部集成和长期记忆风险检查
- 产品体验验收清单接口
- 自然对话、工具预览、记忆、多 Agent、Harness 和部署链路最终验收项
- `agent_tasks` 结构化任务状态与乐观版本控制
- Checkpoint DAG、状态哈希、证据完整性与约束继承校验
- 内容寻址 Artifact 与环境指纹
- 类型化长期记忆的 candidate / verified / superseded 生命周期
- 带 scope、authority、confidence、provenance 和 retrieval trace 的记忆检索
- Tool Runtime 风险、权限、审批、幂等、超时、脱敏、大输出制品化与审计

## 架构文档

后端分层规则见：

```text
api/ARCHITECTURE.md
```

后端依赖用途见：

```text
api/DEPENDENCIES.md
```

## 本地运行

```bash
docker compose up -d postgres redis
cd api
uv venv --python 3.11
uv sync
uv run uvicorn app.main:app --reload
```

访问：

```text
http://localhost:8000/api/status
http://localhost:8000/api/status/database
http://localhost:8000/api/acceptance/checks
http://localhost:8000/api/security/checks
http://localhost:8000/api/sessions
http://localhost:8000/api/sessions/{session_id}/messages
http://localhost:8000/api/sessions/{session_id}/messages/stream
http://localhost:8000/api/sessions/{session_id}/events
http://localhost:8000/api/sessions/{session_id}/stop
http://localhost:8000/api/sessions/{session_id}/read
http://localhost:8000/api/files
http://localhost:8000/api/files/{file_id}
http://localhost:8000/api/files/{file_id}/download
http://localhost:8000/api/files/{file_id}/preview
http://localhost:8000/api/sessions/{session_id}/files
http://localhost:8000/api/config/llm
http://localhost:8000/api/llm/chat
http://localhost:8000/api/agent-thinking/modes
http://localhost:8000/api/agent-thinking/compare
http://localhost:8000/api/mcp/concepts
http://localhost:8000/api/mcp/demo/tools
http://localhost:8000/api/mcp/demo/call
http://localhost:8000/api/mcp/servers
http://localhost:8000/api/mcp/tools
http://localhost:8000/api/mcp/call
http://localhost:8000/api/a2a/concepts
http://localhost:8000/api/a2a/demo/agent-card
http://localhost:8000/api/a2a/demo/message
http://localhost:8000/api/a2a/agents
http://localhost:8000/api/a2a/agents/demo_researcher/card
http://localhost:8000/api/a2a/message/send
http://localhost:8000/api/multi-agent/roles
http://localhost:8000/api/multi-agent/run
http://localhost:8000/api/config/app
http://localhost:8000/api/config/modules/{module_key}
http://localhost:8000/api/config/integrations
http://localhost:8000/api/harness/cases
http://localhost:8000/api/harness/cases/{case_id}/run
http://localhost:8000/api/harness/runs/{run_id}
http://localhost:8000/api/harness/runs/{run_id}/replay
http://localhost:8000/api/observability/checks
http://localhost:8000/api/memories
http://localhost:8000/api/memories/extract
http://localhost:8000/api/sessions/{session_id}/context
http://localhost:8000/api/agent-core/tools
http://localhost:8000/api/agent-core/tools/{tool_name}/invoke
http://localhost:8000/api/control-plane/tasks
http://localhost:8000/api/control-plane/tasks/{task_id}
http://localhost:8000/api/control-plane/tasks/{task_id}/checkpoints
http://localhost:8000/api/control-plane/artifacts
http://localhost:8000/api/control-plane/environment
http://localhost:8000/api/control-plane/tool-invocations
http://localhost:8000/api/memories/{memory_id}/verify
http://localhost:8000/api/agent-core/demo
http://localhost:8000/api/sessions/{session_id}/plan
http://localhost:8000/api/sessions/{session_id}/plan/execute
http://localhost:8000/api/sessions/{session_id}/plan/tasks
http://localhost:8000/api/sessions/{session_id}/tasks/latest
http://localhost:8000/api/sessions/tasks/{task_id}
http://localhost:8000/api/sessions/tasks/{task_id}/cancel
http://localhost:8000/api/sessions/tasks/{task_id}/retry
http://localhost:8000/api/sessions/{session_id}/context
http://localhost:8000/api/agent-core/tools
```

本地开发时执行数据库迁移：

```bash
uv run alembic upgrade head
```

Docker Compose 运行时，API 容器会通过 `api/scripts/start.sh` 默认执行：

```text
uv run alembic upgrade head
```

如果排查问题时需要临时跳过容器启动迁移，可以设置：

```bash
RUN_MIGRATIONS=false docker compose up -d api
```
