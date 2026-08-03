# Backend

`backend/` 集中存放 AtlasAgent 的服务端代码，并把业务控制平面与高风险执行环境分开。

| 目录 | 服务 | 开发命令 |
| --- | --- | --- |
| `api/` | FastAPI Control Plane、数据库迁移、Agent 与工具编排 | `cd backend/api && uv sync && uv run uvicorn app.main:app --reload` |
| `sandbox/` | 文件、Shell、Playwright 与 VNC 隔离执行环境 | `cd backend/sandbox && uv sync && uv run uvicorn app.main:app --reload --port 8100` |

API 是状态与业务入口；Sandbox 只承载受约束的执行能力。生产环境由根目录 `docker-compose.yml` 编排，并通过 `nginx/` 暴露统一入口。
