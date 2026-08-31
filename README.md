<div align="center">
<img src="./assets/readme/hero-editorial-50.webp" width="92%" alt="AtlasAgent" />
<br><br>

<a href="https://github.com/malevrigns/atlas-agent-control-plane/stargazers"><img src="https://img.shields.io/github/stars/malevrigns/atlas-agent-control-plane?style=flat&color=2b6cb0&labelColor=f6f8fa&label=%E2%98%85" alt="Stars"></a>&nbsp;
<a href="https://github.com/malevrigns/atlas-agent-control-plane/actions"><img src="https://img.shields.io/github/actions/workflow/status/malevrigns/atlas-agent-control-plane/ci.yml?style=flat&labelColor=f6f8fa&label=CI" alt="CI"></a>&nbsp;
<a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-2b6cb0?style=flat&labelColor=f6f8fa" alt="MIT"></a>

[English](#english) · [中文](#中文) · [📖 完整教程](tutorial/README.md)

</div>

---

<a id="english"></a>

### Why I built this

When I deployed OpenClaw for the first time, the experience was unlike anything before. But a question followed me for weeks: these general agents are already this strong — is there any point in building another one?

The answer I settled on: a general agent is a good knife; a vertical agent is a machine assembled for one workflow. They don't compete. So this project is my attempt to build the machine — not a chat shell wired to an LLM, but a system that plans a task, executes it step by step, calls tools, observes results, and answers with evidence it can point to.

Along the way I kept running into the same wall: the demos were impressive, but the moment you ask *"where did this fact come from?"* or *"what did the agent do while I was asleep?"* — nothing holds up. AtlasAgent is what that wall looks like when you take it seriously. Every fact carries its source. Every tool call passes a gate before it runs. Every long task leaves behind checkpoints you can resume from. And when a task claims it's done, an acceptance command has to exit 0 before the system believes it.

One more thing: the whole system is paired with a [64-chapter tutorial](tutorial/README.md) that rebuilds it from an empty directory — because reading source code tells you *what*, but rarely *why*. The trade-offs, the dead ends, the reasons things are the way they are: that's what the tutorial keeps. [写在前面](tutorial/README.md) has the full story, in my own words.

<br>

<img src="./assets/readme/evidence-chain.webp" width="100%" alt="Evidence chain" />

### Six boundaries, taken as first principles

| | |
|:--|:--|
| **Memory with provenance** | Facts pass a write gate before they reach the model — source, scope, expiry. Then Ebbinghaus decay, consolidation, conflict resolution, and a typed memory graph. A memory should be able to forget. |
| **RAG that cites its work** | Query rewriting, multi-query RRF fusion, parent-document retrieval, LLM reranking with a lexical fallback. Every citation carries a confidence score; every query leaves a retrieval trace. |
| **A tool runtime with a gate** | Risk tier → approval → idempotency → timeout → redaction → artifact. The handler runs only after the gate says yes. Add result caching, dependency-aware batching, retries with fallback, per-step budgets. |
| **A task must earn "done"** | Before a task completes, three gates run in order: the acceptance command (exit 0 or it isn't done), a scope audit (only files the plan declared), and an LLM coverage review of the tests. Three gates, one shared retry budget — no infinite arguing with the model. |
| **Checkpoints over restarts** | State hashes and environment fingerprints. A task that dies at step 38 resumes from step 17. |
| **Events are the only truth** | Task state is a rebuildable view; checkpoints are verified recovery points. Everything the agent ever did is a queryable record. |

<br>

<img src="./assets/readme/checkpoint-recovery.webp" width="100%" alt="Checkpoint recovery" />

### Run it

Just Python 3.11+ — no Docker, no PostgreSQL, no Redis:

```bash
git clone https://github.com/malevrigns/atlas-agent-control-plane.git
cd atlas-agent-control-plane
python scripts/quickstart.py
```

That's SQLite plus an in-process queue, swapped in through two environment variables. Same application, same models, same routes, same migration chain as production. Open <http://localhost:8000/docs>.

For the full stack — Web workbench, Postgres, Redis, Nginx, sandbox container — you need Git, Docker and Docker Compose v2:

```bash
cp .env.example .env
BUILD=true ./scripts/start.sh
```

Open <http://localhost:8088> — the Web workbench. The start script prints the API key you'll log in with. No LLM key? Everything still boots; a local hash embedding powers offline mode, and any OpenAI-compatible endpoint (DeepSeek, Qwen, DashScope, Ollama…) plugs in via one line in `backend/api/config/llm.yaml`.

<details>
<summary>Calling the control plane directly</summary>

```bash
ATLAS_KEY="$(sed -n 's/^ATLAS_API_KEY=//p' .env)"

# a structured task, with its acceptance command declared up front
curl -X POST http://localhost:8088/api/control-plane/tasks \
  -H "X-Atlas-API-Key: ${ATLAS_KEY}" -H "Content-Type: application/json" \
  -d '{"title": "Upgrade deps", "goal": "A verifiable upgrade",
       "acceptance_criteria": ["pytest exits 0"], "project_id": "atlas"}'

# a tool call — risk, approval and idempotency are checked before the handler runs
curl -X POST http://localhost:8088/api/agent-core/tools/draft_plan/invoke \
  -H "X-Atlas-API-Key: ${ATLAS_KEY}" -H "Content-Type: application/json" \
  -d '{"arguments": {"task": "Check delivery quality"}, "project_id": "atlas",
       "idempotency_key": "demo-001"}'

# every invocation left a record you can query
curl -H "X-Atlas-API-Key: ${ATLAS_KEY}" \
  "http://localhost:8088/api/control-plane/tool-invocations?project_id=atlas"
```

More: [Memory & Tool Control Plane](docs/MEMORY_TOOL_CONTROL_PLANE.md) · [RAG & Skills](docs/RAG_AND_SKILLS.md) · [Architecture](ARCHITECTURE.md)

</details>

<details>
<summary>Configuration, security, and local development</summary>

**Key settings** (see [.env.example](.env.example) for the rest): `LLM_API_KEY` (optional), `ATLAS_API_KEY` (auto-generated), `RAG_VECTOR_BACKEND=pgvector|qdrant`, `RAG_EMBEDDING_PROVIDER=auto|local_hash`, `NGINX_PORT` (default 8088). The built-in key is a single-tenant boundary; internet-facing deployments need TLS, OIDC/RBAC and rate limiting in front. MCP and A2A transports are off or allowlist-only by default.

**Development**, after `docker compose up -d postgres redis`:

| Module | Command |
| --- | --- |
| API | `cd backend/api && uv sync && uv run uvicorn app.main:app --reload` |
| Web | `cd frontend/web && pnpm install && pnpm dev` |
| TUI | `cd frontend/tui && uv sync && ATLAS_API_URL=http://localhost:8000 uv run atlas-tui` |
| Sandbox | `cd backend/sandbox && docker build -t atlas-sandbox . && docker run -d -p 8100:8100 atlas-sandbox` |

Tests: `cd backend/api && uv run python -m unittest discover -s tests` (499 passing).

</details>

<br>

<img src="./assets/readme/three-clients.webp" width="100%" alt="One control plane, three ways in" />

### The repository

```text
atlas-agent-control-plane/
├── frontend/
│   ├── web/        Next.js client (PWA)
│   └── tui/        Textual terminal client
├── backend/
│   ├── api/        FastAPI control plane · migrations · 456 tests
│   └── sandbox/    Isolated files / shell / browser / VNC
├── docs/           Deep-dive documentation
├── tutorial/       64-chapter engineering tutorial (62,000+ lines)
├── scripts/        start.sh / stop.sh
└── docker-compose.yml
```

Issues and PRs are welcome — [CONTRIBUTING.md](CONTRIBUTING.md) has the setup, commit conventions, and PR flow.

---

<a id="中文"></a>

### 为什么做这个

第一次部署 OpenClaw 的时候，体验是前所未有的。但随之而来的问题困扰了我很久：这些通用 Agent 已经这么强了，还有必要从零做一个新的吗？

后来我想明白了：通用 Agent 像一把好刀，垂类 Agent 更像一台按业务流程装配好的机器。两者并不冲突。所以这个项目就是我去造那台机器的尝试——不是一个接了 LLM 接口的聊天壳，而是一个能围绕任务做规划、逐步执行、调用工具、观察结果、最后用可指认的证据回答的系统。

做的过程中反复撞到同一堵墙：演示都很惊艳，但只要你问一句「这条事实从哪来的」「我睡着的时候 Agent 到底干了什么」，就没有一样东西站得住。AtlasAgent 就是把这堵墙当真之后的样子：每条事实带来源，每个工具调用先过门禁，每个长任务留下可以恢复的 Checkpoint，任务说自己完成了，验收命令必须 exit 0，系统才信它。

还有一件事：整个系统配了一套 [64 章的教程](tutorial/README.md)，从空目录开始把它重新造一遍。因为读源码能知道「是什么」，很难知道「为什么」——那些取舍、死路、和「为什么它是现在这个样子」，教程里都留着。[写在前面](tutorial/README.md) 里有完整的来龙去脉。

<br>

### 六个边界，当成第一性约束

| | |
|:--|:--|
| **带来源的记忆** | 事实先过写入门禁才到模型——来源、作用域、有效期，一个都不能少。再往上叠艾宾浩斯衰减、自动巩固、冲突消解、类型化记忆图谱。记忆应该会遗忘。 |
| **会引用出处的 RAG** | 查询改写、多查询 RRF 融合、父文档检索、LLM 重排（词法降级兜底）。每条引用带置信度，每次检索落审计。 |
| **有门禁的工具运行时** | 风险分级 → 审批 → 幂等 → 超时 → 脱敏 → 制品化。门禁说可以，handler 才执行。另有结果缓存、依赖分批、重试降级、步骤预算。 |
| **「完成」要挣来的** | 任务完成前，三道关依次跑：验收命令（exit 0 才算完）、范围审计（只改计划声明的文件）、LLM 覆盖度评审。三关共享重试额度——不和模型无限拉扯。 |
| **Checkpoint 优先于重启** | 状态哈希 + 环境指纹。第 38 步挂了，从第 17 步恢复。 |
| **事件是唯一事实源** | 任务状态只是可重建的视图，Checkpoint 是验证过的恢复点。Agent 干过的每件事都是一条可查询的记录。 |

### 跑起来

只要 Python 3.11+，不用 Docker、不用 PostgreSQL、不用 Redis：

```bash
git clone https://github.com/malevrigns/atlas-agent-control-plane.git
cd atlas-agent-control-plane
python scripts/quickstart.py
```

数据库换成 SQLite、队列换成进程内实现，靠两个环境变量切过去——应用、模型、路由、迁移链和生产完全是同一套。打开 <http://localhost:8000/docs> 就能调。

要完整形态（Web 工作台、Postgres、Redis、Nginx、沙箱容器），才需要 Git、Docker、Docker Compose v2：

```bash
cp .env.example .env
BUILD=true ./scripts/start.sh
```

打开 <http://localhost:8088> 就是 Web 工作台，启动脚本会打印登录用的 API Key。没配模型密钥也能跑——本地哈希 embedding 撑起离线模式；要接模型的话，DeepSeek、Qwen、DashScope、Ollama，任何 OpenAI 兼容接口在 `backend/api/config/llm.yaml` 里改一行就行。

<details>
<summary>直接调用控制平面</summary>

```bash
ATLAS_KEY="$(sed -n 's/^ATLAS_API_KEY=//p' .env)"

# 一个结构化任务，验收命令一开始就声明好
curl -X POST http://localhost:8088/api/control-plane/tasks \
  -H "X-Atlas-API-Key: ${ATLAS_KEY}" -H "Content-Type: application/json" \
  -d '{"title": "升级依赖", "goal": "可验证升级",
       "acceptance_criteria": ["pytest 退出码 0"], "project_id": "atlas"}'

# 一次工具调用——handler 执行前先过风险、审批、幂等检查
curl -X POST http://localhost:8088/api/agent-core/tools/draft_plan/invoke \
  -H "X-Atlas-API-Key: ${ATLAS_KEY}" -H "Content-Type: application/json" \
  -d '{"arguments": {"task": "检查交付质量"}, "project_id": "atlas",
       "idempotency_key": "demo-001"}'

# 每次调用都留了记录，随时可以查
curl -H "X-Atlas-API-Key: ${ATLAS_KEY}" \
  "http://localhost:8088/api/control-plane/tool-invocations?project_id=atlas"
```

更多：[Memory 与 Tool Control Plane](docs/MEMORY_TOOL_CONTROL_PLANE.md) · [RAG 与 Skill 注册中心](docs/RAG_AND_SKILLS.md) · [整体架构](ARCHITECTURE.md)

</details>

<details>
<summary>配置、安全与本地开发</summary>

**常用配置**（其余见 [.env.example](.env.example)）：`LLM_API_KEY`（可选）、`ATLAS_API_KEY`（自动生成）、`RAG_VECTOR_BACKEND=pgvector|qdrant`、`RAG_EMBEDDING_PROVIDER=auto|local_hash`、`NGINX_PORT`（默认 8088）。内置 API Key 是单租户边界；公网多用户部署需要 TLS、OIDC/RBAC 和限流。MCP 与 A2A 传输默认关闭或仅白名单。

**本地开发**，先 `docker compose up -d postgres redis`：

| 模块 | 命令 |
| --- | --- |
| API | `cd backend/api && uv sync && uv run uvicorn app.main:app --reload` |
| Web | `cd frontend/web && pnpm install && pnpm dev` |
| TUI | `cd frontend/tui && uv sync && ATLAS_API_URL=http://localhost:8000 uv run atlas-tui` |
| Sandbox | `cd backend/sandbox && docker build -t atlas-sandbox . && docker run -d -p 8100:8100 atlas-sandbox` |

测试：`cd backend/api && uv run python -m unittest discover -s tests`（499 个通过）。

</details>

### 仓库结构

```text
atlas-agent-control-plane/
├── frontend/
│   ├── web/        Next.js 客户端（PWA）
│   └── tui/        Textual 终端客户端
├── backend/
│   ├── api/        FastAPI 控制平面 · 迁移 · 456 个测试
│   └── sandbox/    文件 / Shell / 浏览器 / VNC 隔离执行
├── docs/           专题深潜文档
├── tutorial/       64 章中文工程教程（62000+ 行）
├── scripts/        start.sh / stop.sh
└── docker-compose.yml
```

欢迎 Issue 与 PR——流程见 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

<div align="center">
<sub>纵使这个时代资料多如繁星，也希望自己的思考能在这个时代留下痕迹。</sub>
</div>
