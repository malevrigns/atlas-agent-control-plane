# Frontend

`frontend/` 集中存放 AtlasAgent 的三个客户端。它们共享同一套 FastAPI 协议，不直接访问 PostgreSQL、Redis、Sandbox 容器或 MCP Server。

| 目录 | 客户端 | 开发命令 |
| --- | --- | --- |
| `web/` | Next.js 浏览器工作台 | `cd frontend/web && pnpm install && pnpm dev` |
| `desktop/` | Electron Checkpoint 时间线 | `cd frontend/desktop && npm install && npm run electron:dev` |
| `tui/` | Textual 键盘优先终端 | `cd frontend/tui && uv sync && uv run atlas-tui` |

Web 通过 Nginx 网关访问 API；Desktop 与 TUI 使用 `ATLAS_API_URL` 连接同一后端。认证统一使用浏览器会话或 `X-Atlas-API-Key`，客户端代码不保存服务端密钥。
