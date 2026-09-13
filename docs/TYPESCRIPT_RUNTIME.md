# TypeScript runtime (in progress)

The production control plane is being rewritten from FastAPI to **Hono + Drizzle** without changing the HTTP/SSE/auth contract the web workbench and TUI already speak.

| Python (current default) | TypeScript (this slice) |
|---|---|
| `backend/api` | `backend/api-ts` |
| `app/core` | `src/core` |
| `app/presentation/http/routes` | `src/presentation/http/routes` |
| `app/application` | `src/application` |
| `app/domain` | `src/domain` |
| `app/infrastructure` | `src/infrastructure` |
| Alembic | Drizzle schema + `SQLITE_DDL` (same table names) |

Compose, quickstart, and CI now run the TypeScript API and sandbox. The TypeScript API already covers:

- `GET /api/status`, `GET /api/status/database`
- `POST/DELETE /api/auth/session`, `GET /api/auth/check` (204)
- sessions, messages, events, context snapshot
- session/file uploads, file preview/download
- `POST /api/sessions/{id}/messages/stream` (offline stub, or LLM if `LLM_API_KEY` is set)

## Run it

```bash
cd backend/api-ts
pnpm install
pnpm test
pnpm dev
```

Zero-dependency (SQLite), same idea as `scripts/quickstart.py`:

```bash
cd backend/api-ts
API_AUTH_ENABLED=false DATABASE_URL=file:./var/atlas.db pnpm start
```

Open http://127.0.0.1:8000/api/status.

Point the web app at it with `API_PROXY_URL=http://127.0.0.1:8000/api/:path*` (or run Next with the default rewrite to port 8000).

## What is not in this slice

Tool runtime, the full agent execution machine, acceptance gates, RAG, memory lifecycle, skills, and MCP/A2A are still being ported. Those routes currently return empty `{ items: [] }` so the workbench does not 404. The sandbox HTTP API (files / shell / VNC status) is TypeScript.
