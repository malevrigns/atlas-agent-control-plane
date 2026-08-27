# Contributing / 贡献指南

Thank you for considering a contribution to AtlasAgent. This guide covers development setup, how to run the checks we run, commit conventions, and the pull-request process.
感谢你对 AtlasAgent 的关注与贡献。本文档覆盖开发环境搭建、本地检查、commit 规范与 Pull Request 流程。

---

## English

### 1. Development environment

Prerequisites:

- Git, Docker, and Docker Compose v2
- Python 3.11+ with [uv](https://docs.astral.sh/uv/) (backend / sandbox)
- Node.js 20+ with pnpm (web frontend)
- An OpenAI-compatible LLM API key (optional — demo mode works without one)

Option 1 — full stack with Docker:

```bash
cp .env.example .env
BUILD=true ./scripts/start.sh
```

Option 2 — per-module development (from the repo root):

```bash
docker compose up -d postgres redis
```

| Module | Command | Default address / behavior |
| --- | --- | --- |
| API | `cd backend/api && uv sync && uv run uvicorn app.main:app --reload` | `http://localhost:8000` |
| Web | `cd frontend/web && pnpm install && pnpm dev` | `http://localhost:3000` |
| TUI | `cd frontend/tui && uv sync && ATLAS_API_URL=http://localhost:8000 uv run atlas-tui` | Falls back to demo mode when the backend is unreachable |
| Sandbox | `cd backend/sandbox && docker build -t atlas-sandbox . && docker run -d -p 8100:8100 -p 6080:6080 -e SANDBOX_AUTH_ENABLED=false atlas-sandbox` | `http://localhost:8100` |

### 2. Running the checks

Run the checks for every module you touched before opening a PR:

```bash
# Backend tests
cd backend/api
uv run python -m unittest discover -s tests

# TUI tests
cd ../../frontend/tui
uv run python -m unittest discover -s tests

# Web typecheck & build
cd ../web
pnpm typecheck
pnpm build
```

Root-level production-configuration tests live in `tests/`:

```bash
cd tests && python -m unittest discover -s .
```

### 3. Commit conventions

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
type(scope): subject
```

- `type`: `feat` | `fix` | `docs` | `style` | `refactor` | `perf` | `test` | `chore`
- `scope` (optional): `api` | `web` | `tui` | `sandbox` | `rag` | `memory` | `tool` | `ci`
- `subject`: imperative, ≤ 72 chars, no trailing period. Body lines ≤ 100 chars.

Examples:

```
feat(tool): add duplicate-call guardrail to StepAgentLoop
fix(web): prevent stream duplication when PWA reconnects
docs(README): add English section and star guidance
```

### 4. Pull request process

1. Fork the repo and create a branch off `main` (e.g. `fix/stream-duplication`).
2. Make your change with focused commits following the convention above.
3. Run the checks for the modules you touched (section 2) and verify manually.
4. Open a PR using the [pull request template](.github/PULL_REQUEST_TEMPLATE.md) — fill in the testing section; reviewers use it.
5. Address review feedback with new commits on the same branch (squash-merge is used, so history stays clean).

### 5. Ground rules

- Never commit real `.env` files, model keys, or third-party credentials — even in screenshots and logs.
- Keep changes scoped: one PR, one concern.
- If you change user-facing behavior, update the relevant doc (`README.md`, `docs/`, or the tutorial).
- New tools must go through the unified tool runtime (risk tier, idempotency, audit) — do not add bare handlers.

---

## 中文

### 1. 开发环境

前置条件：

- Git、Docker 与 Docker Compose v2
- Python 3.11+ 与 [uv](https://docs.astral.sh/uv/)（后端 / 沙箱）
- Node.js 20+ 与 pnpm（Web 前端）
- 一个 OpenAI 兼容的大模型 API Key（可选——不配置也能跑演示模式）

方式一 —— Docker 起全套：

```bash
cp .env.example .env
BUILD=true ./scripts/start.sh
```

方式二 —— 分模块开发（仓库根目录）：

```bash
docker compose up -d postgres redis
```

| 模块 | 启动命令 | 默认地址 / 行为 |
| --- | --- | --- |
| API | `cd backend/api && uv sync && uv run uvicorn app.main:app --reload` | `http://localhost:8000` |
| Web | `cd frontend/web && pnpm install && pnpm dev` | `http://localhost:3000` |
| TUI | `cd frontend/tui && uv sync && ATLAS_API_URL=http://localhost:8000 uv run atlas-tui` | 后端不可达时自动进入演示模式 |
| Sandbox | `cd backend/sandbox && docker build -t atlas-sandbox . && docker run -d -p 8100:8100 -p 6080:6080 -e SANDBOX_AUTH_ENABLED=false atlas-sandbox` | `http://localhost:8100` |

### 2. 运行检查

提交 PR 前，请运行所有改动模块对应的检查：

```bash
# 后端测试
cd backend/api
uv run python -m unittest discover -s tests

# TUI 测试
cd ../../frontend/tui
uv run python -m unittest discover -s tests

# Web 类型检查与构建
cd ../web
pnpm typecheck
pnpm build
```

根级生产配置测试位于 `tests/`：

```bash
cd tests && python -m unittest discover -s .
```

### 3. Commit 规范

我们采用 [Conventional Commits](https://www.conventionalcommits.org/)：

```
type(scope): subject
```

- `type`：`feat` | `fix` | `docs` | `style` | `refactor` | `perf` | `test` | `chore`
- `scope`（可选）：`api` | `web` | `tui` | `sandbox` | `rag` | `memory` | `tool` | `ci`
- `subject`：祈使句，不超过 72 字符，句尾不加句号；正文每行不超过 100 字符。

示例：

```
feat(tool): 为 StepAgentLoop 增加重复调用护栏
fix(web): 修复 PWA 重连时流式回答重复
docs(README): 增加英文版与 Star 引导
```

### 4. PR 流程

1. Fork 仓库，从 `main` 创建分支（如 `fix/stream-duplication`）。
2. 按上面的 commit 规范提交聚焦的小提交。
3. 运行改动模块对应的检查（见第 2 节）并手动验证。
4. 使用 [PR 模板](.github/PULL_REQUEST_TEMPLATE.md) 发起 PR，填写测试部分——评审人依赖它。
5. 评审意见在同一分支追加提交回复（合并采用 squash-merge，保持历史整洁）。

### 5. 底线约定

- 任何情况下都不要提交真实 `.env`、模型密钥或第三方凭据——包括截图与日志。
- 保持改动聚焦：一个 PR 只解决一件事。
- 改动用户可见行为时，同步更新对应文档（`README.md`、`docs/` 或教程）。
- 新增工具必须走统一 Tool Runtime（风险分级、幂等、审计）——不要直接加裸 handler。
