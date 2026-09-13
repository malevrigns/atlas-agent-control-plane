# Backend

`backend/` 集中存放 AtlasAgent 的服务端代码，并把业务控制平面与高风险执行环境分开。

| 目录 | 服务 | 开发命令 |
| --- | --- | --- |
| `api-ts/` | TypeScript Hono 控制平面 | `cd backend/api-ts && pnpm install && pnpm dev` |
| `sandbox-ts/` | 文件、Shell 与 VNC 隔离执行环境 | `cd backend/sandbox-ts && pnpm install && pnpm dev` |

`api/` 与 `sandbox/` 是已停用的 Python 实现，不再作为运行时。

API 是状态与业务入口；Sandbox 只承载受约束的执行能力。生产环境由根目录 `docker-compose.yml` 编排，并通过 `nginx/` 暴露统一入口。
