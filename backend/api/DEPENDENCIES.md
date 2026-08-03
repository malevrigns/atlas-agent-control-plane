# API 依赖说明

本文档说明后端 `pyproject.toml` 中主要依赖的用途。新增依赖时，需要同步更新本文档。

## 运行时依赖

### `fastapi`

后端 Web 框架。

用于定义 HTTP 路由、依赖注入、请求体验证和响应模型。

### `uvicorn[standard]`

ASGI 服务器。

本地开发和容器运行时用它启动 FastAPI 应用。

### `pydantic-settings`

配置读取工具。

用于从环境变量和默认值中构建 `Settings` 对象。

### `sqlalchemy[asyncio]`

数据库 ORM 和异步数据库访问基础。

用于定义数据库连接、异步 Session、SQLAlchemy 查询和 Repository 实现。

### `asyncpg`

PostgreSQL 异步驱动。

SQLAlchemy 异步连接 PostgreSQL 时会使用它。

### `alembic`

数据库迁移工具。

用于记录表结构变化，例如创建 `sessions`、`session_messages`、`session_events` 等表。

### `redis`

Redis 客户端。

用于连接 Redis Stream，支撑 Agent 后台任务队列。

### `httpx`

HTTP 客户端。

用于调用 LLM、Sandbox、Search、MCP Streamable HTTP 等外部服务。

### `python-multipart`

表单和文件上传解析依赖。

FastAPI 处理 `UploadFile` 时需要它。

### `pyyaml`

YAML 配置解析。

用于读取 `config/llm.yaml`、`config/mcp.yaml` 等配置文件。

## 依赖管理规则

新增依赖前先确认是否真的需要。

如果标准库、现有依赖或项目已有封装能解决问题，不要轻易增加第三方包。

新增依赖时至少检查三件事：

- 是否只在开发环境使用。
- 是否会影响 Docker 构建速度。
- 是否需要在教程中解释安装和用途。

新增运行时依赖后，需要同步更新：

```text
backend/api/pyproject.toml
backend/api/uv.lock
backend/api/DEPENDENCIES.md
相关章节教程
```

## 不应放进后端依赖的内容

前端依赖不要放进 `backend/api/pyproject.toml`。

Sandbox 专用依赖不要放进 `backend/api/pyproject.toml`。

仅用于本地临时调试的工具不要默认加入运行时依赖。
