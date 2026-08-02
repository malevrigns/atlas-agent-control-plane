# 第二十章. AgentTaskRunner 与 Redis Stream 任务流转

> **最终实现修订：**本章前半先用单消费者 `XREAD` 解释后台任务模型；本章后半再把它升级为 Redis Consumer Group、pending reclaim、ACK 和真实协程取消。不要把教学过程中的 `$` 起点实现直接用于生产。

## 20.1 本章目标
​        第 19 章已经把计划执行跑通了，但同步 HTTP 请求只能支撑教学级短任务。真实 Agent 一旦开始访问网页、读取文件、运行 Shell、调用多个工具，执行时间就可能从几秒变成几分钟。浏览器一直等一个请求返回，不利于取消、状态展示、失败恢复，也不利于后续扩展多 worker。
​        本章会把“点击执行”改造成后台任务模型。API 只负责把计划执行任务写入 Redis Stream，并立即返回 `task_id`；任务状态保存在 Redis Hash 中，供前端轮询查询；`AgentTaskRunner` 在 FastAPI 生命周期中启动后台循环，消费 Stream 里的任务，并复用第 19 章的 `ReActAgentService` 执行计划。前端会显示任务状态，支持取消，并在轮询过程中刷新事件和步骤状态。

## 20.2 最终效果
​        本章结束后，计划面板的“执行”按钮不再直接调用同步执行接口，而是启动一个后台任务。
​        操作流程：

```Plain
创建会话
  |
  v
发送任务消息
  |
  v
生成计划
  |
  v
点击执行
  |
  v
API 把任务写入 Redis Stream
  |
  v
AgentTaskRunner 后台消费任务
  |
  v
ReActAgentService 执行计划步骤
  |
  v
前端轮询任务状态并刷新事件面板
```

​        新增接口：

```Plain
POST /api/sessions/{session_id}/plan/tasks
GET  /api/sessions/tasks/{task_id}
POST /api/sessions/tasks/{task_id}/cancel
```

​        第 19 章的同步执行接口仍然保留：

```Plain
POST /api/sessions/{session_id}/plan/execute
```

​        保留它是为了方便对比“同步执行”和“后台任务执行”的差异。

## 20.3 本章要解决的问题
​        第 19 章已经可以执行计划，但它有一个明显问题：浏览器点击执行后，HTTP 请求会一直等待后端执行完成。
​        如果后续任务变成这样：

```Plain
访问网页
读取文件
执行 Shell
调用多个工具
等待用户确认
执行 5 分钟甚至更久
```

​        普通 HTTP 请求就不适合一直占着连接等待结果。
​        更合理的做法是把“提交任务”和“执行任务”拆开：

```Plain
提交任务：快速返回 task_id
执行任务：后台 Runner 慢慢处理
查看任务：前端根据 task_id 查询状态
```

​        本章用 Redis Stream 完成这个拆分。

## 20.4 本章技术方案
​        后端分成四层：

```Plain
API Route
  |
  v
RedisAgentTaskQueue
  |
  +-- Redis Stream：保存待执行任务消息
  +-- Redis Hash：保存任务状态

AgentTaskRunner
  |
  v
ReActAgentService
  |
  v
session_events
```

​        为什么 Redis Stream 和 Redis Hash 都要用？

```Plain
Redis Stream 适合做“任务消息队列”
Redis Hash   适合做“任务状态查询”
```

​        任务消息只需要告诉 Runner：

```JSON
{
  "task_id": "...",
  "session_id": "...",
  "type": "execute_plan"
}
```

​        任务状态需要给前端查询：

```JSON
{
  "id": "...",
  "status": "running",
  "error": null,
  "created_at": "...",
  "updated_at": "..."
}
```

​        前端调用链路：

```Plain
PlanPanel 执行按钮
  |
  v
session-store.executePlan()
  |
  v
POST /api/sessions/{session_id}/plan/tasks
  |
  v
得到 task_id
  |
  v
每秒 GET /api/sessions/tasks/{task_id}
  |
  v
刷新事件列表和步骤状态
```

​        本章暂时只做单个 API 内置 Runner，不做多个 worker 进程，也不引入 Redis Consumer Group、失败任务自动重试、精确中断单个工具或任务历史列表。这些能力都和生产级任务系统有关，但如果一开始全部加入，反而会掩盖本章最重要的主线：先把任务入队、状态查询、后台消费和前端轮询跑通。

## 20.5 新增和修改的文件

```Plain
.env.example
README.md
api/README.md
api/pyproject.toml
api/uv.lock
api/app/api/routes/sessions.py
api/app/application/agent_task_runner.py
api/app/core/config.py
api/app/infrastructure/task_queue.py
api/app/main.py
api/app/schemas/session.py
docker-compose.yml
docs/course/chapters/20-agent-task-runner.md
ui/README.md
ui/app/components/chat-workspace.tsx
ui/app/components/plan-panel.tsx
ui/app/lib/session-api.ts
ui/app/page.tsx
ui/app/stores/session-store.ts
ui/app/types.ts
```

## 20.6 本章代码写法说明
​        本章会同时出现“新增文件”和“修改已有文件”。
​        为了避免边写边迷路，本章会把新增文件直接给出完整代码；关键修改文件会先说明改哪里，再给出完整代码或完整函数对照；特别长的已有文件不会整篇重复 600 多行，而是给出需要替换的函数、状态、action 和 props。这样读者既能跟着手敲，也能对照自己已有代码检查漏项。
​        如果你是跟着手敲代码，优先按每一步的完整代码写；如果你已经写过前面章节，可以用完整代码对照检查自己有没有漏 import、漏 props 或漏状态字段。

## 20.7 实施步骤
### 20.7.1 安装 Redis Python 客户端
​        进入后端目录：

```Bash
cd api
```

​        安装依赖：

```Bash
uv add "redis>=5.2,<6.0"
```

​        这条命令会更新两个文件：

```Plain
api/pyproject.toml
api/uv.lock
```

#### 20.7.1.1 代码讲解
​        本章使用的是 `redis` 官方 Python 客户端。它包含 `redis.asyncio`，可以在 FastAPI 异步服务里直接使用。
​        不要用同步 Redis 客户端阻塞事件循环。FastAPI 路由、后台 Runner、数据库访问都是异步代码，Redis 客户端也保持异步会更一致。

### 20.7.2 增加 Redis 和任务配置
​        打开 `api/app/core/config.py`，在 `Settings` 中加入：

```Python
redis_url: str = "redis://localhost:6379/0"
agent_task_stream: str = "agent:tasks"
agent_task_poll_timeout_ms: int = 1000
```

#### 20.7.2.1 代码讲解
​        `redis_url` 是后端连接 Redis 的地址。
​        本地直接运行 API 时，默认值是：

```Plain
redis://localhost:6379/0
```

​        Docker Compose 运行时，会使用：

```Plain
redis://redis:6379/0
```

​        这里的 `redis` 是 Docker Compose 服务名，不是本机域名。
​        `agent_task_stream` 是任务队列名称。后续所有 Agent 后台任务都会先进入这个 Stream。
​        `agent_task_poll_timeout_ms` 是 Runner 读取 Stream 的等待时间。本章设置为 1000 毫秒，表示如果暂时没有任务，Runner 最多阻塞 1 秒再继续循环。

### 20.7.3 编写 RedisAgentTaskQueue
​        创建 `api/app/infrastructure/task_queue.py`。
​        这个文件负责两件事：

```Plain
1. 把任务写入 Redis Stream
2. 把任务状态写入 Redis Hash
```

​        完整代码如下：

```Python
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from redis.asyncio import Redis

from app.core.config import settings


class AgentTaskStatus(StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


@dataclass(slots=True)
class AgentTask:
    id: str
    session_id: UUID
    type: str
    status: AgentTaskStatus
    error: str | None
    created_at: str
    updated_at: str


class RedisAgentTaskQueue:
    """基于 Redis Stream 的 Agent 任务队列。

    本章只使用一个 Stream 和一个 API 内置 Runner，先把后台任务模型跑通。
    后续可以继续扩展 consumer group、多个 worker 和任务重试策略。
    """

    def __init__(self, redis: Redis, stream_name: str | None = None) -> None:
        # ===================== 第1步：保存 Redis 连接和 Stream 名称 =====================
        self.redis = redis
        self.stream_name = stream_name or settings.agent_task_stream

    # ===================== 第2步：创建任务并写入 Stream =====================
    async def enqueue_execute_plan(self, session_id: UUID) -> AgentTask:
        """创建一个执行计划任务，并把任务 ID 写入 Redis Stream。"""

        now = self._now()
        task = AgentTask(
            id=str(uuid4()),
            session_id=session_id,
            type="execute_plan",
            status=AgentTaskStatus.queued,
            error=None,
            created_at=now,
            updated_at=now,
        )
        await self._write_task(task)
        await self.redis.xadd(
            self.stream_name,
            {
                "task_id": task.id,
                "session_id": str(session_id),
                "type": task.type,
            },
        )
        return task

    # ===================== 第3步：读取单个任务状态 =====================
    async def get_task(self, task_id: str) -> AgentTask | None:
        """从 Redis Hash 中读取任务状态。"""

        data = await self.redis.hgetall(self._task_key(task_id))
        if not data:
            return None
        return self._to_task(data)

    # ===================== 第4步：取消还没有完成的任务 =====================
    async def cancel_task(self, task_id: str) -> AgentTask | None:
        """把任务标记为 cancelled。

        本章的 Runner 是短任务同步执行，如果任务已经 running，取消会尽力标记状态；
        第 20 章先理解任务状态流转，后续长任务会再加入更细的中断点。
        """

        task = await self.get_task(task_id)
        if task is None:
            return None
        if task.status in {
            AgentTaskStatus.succeeded,
            AgentTaskStatus.failed,
            AgentTaskStatus.cancelled,
        }:
            return task

        task.status = AgentTaskStatus.cancelled
        task.updated_at = self._now()
        await self._write_task(task)
        return task

    # ===================== 第5步：更新任务状态 =====================
    async def mark_running(self, task_id: str) -> AgentTask | None:
        return await self._update_status(task_id, AgentTaskStatus.running)

    async def mark_succeeded(self, task_id: str) -> AgentTask | None:
        return await self._update_status(task_id, AgentTaskStatus.succeeded)

    async def mark_failed(self, task_id: str, error: str) -> AgentTask | None:
        return await self._update_status(task_id, AgentTaskStatus.failed, error=error)

    async def _update_status(
        self,
        task_id: str,
        status: AgentTaskStatus,
        error: str | None = None,
    ) -> AgentTask | None:
        task = await self.get_task(task_id)
        if task is None:
            return None
        task.status = status
        task.error = error
        task.updated_at = self._now()
        await self._write_task(task)
        return task

    # ===================== 第6步：封装 Redis Hash 读写细节 =====================
    async def _write_task(self, task: AgentTask) -> None:
        await self.redis.hset(
            self._task_key(task.id),
            mapping={
                "id": task.id,
                "session_id": str(task.session_id),
                "type": task.type,
                "status": task.status.value,
                "error": task.error or "",
                "created_at": task.created_at,
                "updated_at": task.updated_at,
            },
        )

    def _to_task(self, data: dict) -> AgentTask:
        return AgentTask(
            id=str(data["id"]),
            session_id=UUID(str(data["session_id"])),
            type=str(data["type"]),
            status=AgentTaskStatus(str(data["status"])),
            error=str(data["error"]) or None,
            created_at=str(data["created_at"]),
            updated_at=str(data["updated_at"]),
        )

    def _task_key(self, task_id: str) -> str:
        return f"agent:task:{task_id}"

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()


def create_redis_client() -> Redis:
    """创建 Redis 客户端。

    decode_responses=True 会把 Redis 返回值解码成字符串，代码里不需要反复处理 bytes。
    """

    return Redis.from_url(settings.redis_url, decode_responses=True)
```

​        下面再把关键部分拆开讲：

```Python
class AgentTaskStatus(StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"
```

#### 20.7.3.1 代码讲解
​        任务状态从上到下表示一条后台任务的生命周期。`queued` 说明任务已经入队但还没有被 Runner 消费，`running` 说明 Runner 已经拿到任务并开始执行，`succeeded` 表示任务执行成功，`failed` 表示执行失败并会记录错误信息，`cancelled` 表示任务被用户取消或被系统标记为取消。前端后面展示的任务状态，全部来自这组枚举。
​        继续看任务结构：

```Python
@dataclass(slots=True)
class AgentTask:
    id: str
    session_id: UUID
    type: str
    status: AgentTaskStatus
    error: str | None
    created_at: str
    updated_at: str
```

#### 20.7.3.2 业务讲解
​        `AgentTask` 是给前端看的任务对象。
​        前端点击执行后，会立刻拿到：

```Plain
任务 ID
任务状态
创建时间
更新时间
错误信息
```

​        这样页面不用等待计划执行完成，可以马上显示“后台任务：queued”。
​        创建任务的核心方法是：

```Python
async def enqueue_execute_plan(self, session_id: UUID) -> AgentTask:
    now = self._now()
    task = AgentTask(
        id=str(uuid4()),
        session_id=session_id,
        type="execute_plan",
        status=AgentTaskStatus.queued,
        error=None,
        created_at=now,
        updated_at=now,
    )
    await self._write_task(task)
    await self.redis.xadd(
        self.stream_name,
        {
            "task_id": task.id,
            "session_id": str(session_id),
            "type": task.type,
        },
    )
    return task
```

#### 20.7.3.3 代码讲解
​        这段代码分成三步：

```Plain
第 1 步：生成 task_id 和初始状态
第 2 步：把完整任务状态写入 Redis Hash
第 3 步：把任务消息写入 Redis Stream
```

​        为什么先写 Hash，再写 Stream？
​        因为 Runner 读到 Stream 消息后，会立刻根据 `task_id` 查询任务状态。如果先写 Stream，再写 Hash，极端情况下 Runner 可能先读到了消息，但任务状态还不存在。
​        任务状态写入 Redis Hash：

```Python
await self.redis.hset(
    self._task_key(task.id),
    mapping={
        "id": task.id,
        "session_id": str(task.session_id),
        "type": task.type,
        "status": task.status.value,
        "error": task.error or "",
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    },
)
```

​        Hash 的 key 类似：

```Plain
agent:task:0a8c...
```

​        任务消息写入 Stream：

```Python
await self.redis.xadd(
    self.stream_name,
    {
        "task_id": task.id,
        "session_id": str(session_id),
        "type": task.type,
    },
)
```

​        Stream 的名称是：

```Plain
agent:tasks
```

### 20.7.4 编写 AgentTaskRunner
​        创建 `api/app/application/agent_task_runner.py`。
​        Runner 的职责是：

```Plain
读取 Redis Stream
  |
  v
找到任务状态
  |
  v
标记 running
  |
  v
调用 ReActAgentService
  |
  v
标记 succeeded 或 failed
```

​        完整代码如下：

```Python
import asyncio
from contextlib import suppress
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.application.react_agent_service import ReActAgentService
from app.application.unit_of_work import UnitOfWork
from app.core.config import settings
from app.infrastructure.task_queue import AgentTaskStatus, RedisAgentTaskQueue


class AgentTaskRunner:
    """从 Redis Stream 消费 Agent 任务，并在后台执行。

    第 19 章的执行接口是同步请求：浏览器要等执行结束。
    第 20 章把执行请求拆成两段：
    1. API 只负责把任务放进 Redis Stream。
    2. Runner 在后台读取任务并执行。
    """

    def __init__(
        self,
        queue: RedisAgentTaskQueue,
        session_factory: async_sessionmaker,
    ) -> None:
        # ===================== 第1步：保存队列和数据库会话工厂 =====================
        self.queue = queue
        self.session_factory = session_factory
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_stream_id = "$"

    # ===================== 第2步：启动后台循环 =====================
    def start(self) -> None:
        """在 FastAPI 启动时创建后台任务。"""

        if self._task is not None:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    # ===================== 第3步：停止后台循环 =====================
    async def stop(self) -> None:
        """在 FastAPI 关闭时停止后台任务。"""

        self._running = False
        if self._task is None:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    # ===================== 第4步：循环读取 Redis Stream =====================
    async def _run_loop(self) -> None:
        """不断读取 Stream 中的新任务。"""

        while self._running:
            try:
                streams = await self.queue.redis.xread(
                    {self.queue.stream_name: self._last_stream_id},
                    block=settings.agent_task_poll_timeout_ms,
                    count=1,
                )
                for _, messages in streams:
                    for message_id, payload in messages:
                        self._last_stream_id = message_id
                        await self._handle_message(payload)
            except asyncio.CancelledError:
                raise
            except Exception:
                # 这里不能让单次任务异常杀死整个后台循环。
                # 真实项目会接入结构化日志和告警；本章先保证 Runner 可以继续消费下一条任务。
                await asyncio.sleep(1)

    # ===================== 第5步：处理单条任务消息 =====================
    async def _handle_message(self, payload: dict) -> None:
        """根据任务类型分发到具体执行方法。"""

        task_id = str(payload.get("task_id", ""))
        task_type = str(payload.get("type", ""))
        session_id_text = str(payload.get("session_id", ""))
        if not task_id or not session_id_text:
            return

        task = await self.queue.get_task(task_id)
        if task is None or task.status is AgentTaskStatus.cancelled:
            return

        await self.queue.mark_running(task_id)
        try:
            if task_type == "execute_plan":
                await self._execute_plan(UUID(session_id_text))
            else:
                raise ValueError(f"unsupported task type: {task_type}")
        except Exception as error:
            await self.queue.mark_failed(task_id, str(error))
            return

        latest_task = await self.queue.get_task(task_id)
        if latest_task and latest_task.status is AgentTaskStatus.cancelled:
            return
        await self.queue.mark_succeeded(task_id)

    # ===================== 第6步：真正调用 ReActAgentService =====================
    async def _execute_plan(self, session_id: UUID) -> None:
        """为后台任务创建独立数据库会话，再复用第 19 章执行逻辑。"""

        async with self.session_factory() as db_session:
            service = ReActAgentService(UnitOfWork(db_session))
            await service.execute_latest_plan(session_id)
```

​        核心启动方法：

```Python
def start(self) -> None:
    if self._task is not None:
        return
    self._running = True
    self._task = asyncio.create_task(self._run_loop())
```

#### 20.7.4.1 代码讲解
​        `asyncio.create_task()` 会创建一个后台协程。
​        这意味着 FastAPI 启动后，Runner 会和 API 请求处理同时运行：

```Plain
FastAPI 处理 HTTP 请求
AgentTaskRunner 后台消费任务
```

​        核心消费循环：

```Python
streams = await self.queue.redis.xread(
    {self.queue.stream_name: self._last_stream_id},
    block=settings.agent_task_poll_timeout_ms,
    count=1,
)
```

#### 20.7.4.2 代码讲解
​        `xread` 是 Redis Stream 的读取命令。
​        这里传入：

```Plain
stream_name: agent:tasks
last_stream_id: $
block: 1000
count: 1
```

​        含义是：

```Plain
从 agent:tasks 读取新任务
如果暂时没有任务，最多等待 1000 毫秒
一次最多读取 1 条任务
```

​        `_last_stream_id` 初始值是 `$`，表示 Runner 启动后只消费新任务，避免服务重启时重复执行历史任务。
​        处理任务的关键代码：

```Python
await self.queue.mark_running(task_id)
try:
    if task_type == "execute_plan":
        await self._execute_plan(UUID(session_id_text))
    else:
        raise ValueError(f"unsupported task type: {task_type}")
except Exception as error:
    await self.queue.mark_failed(task_id, str(error))
    return

await self.queue.mark_succeeded(task_id)
```

#### 20.7.4.3 业务讲解
​        这一段就是任务状态机：

```Plain
queued -> running -> succeeded
queued -> running -> failed
queued -> cancelled
```

​        本章的任务执行很快，所以取消是“尽力取消”。如果任务还在队列里，取消状态会生效；如果任务已经执行完，状态不会回退。
​        真正执行计划的代码：

```Python
async with self.session_factory() as db_session:
    service = ReActAgentService(UnitOfWork(db_session))
    await service.execute_latest_plan(session_id)
```

#### 20.7.4.4 代码讲解
​        后台任务不能复用 HTTP 请求里的数据库会话。
​        所以 Runner 每执行一个任务，都要创建新的数据库会话：

```Plain
HTTP 请求数据库会话：只属于当前请求
后台任务数据库会话：由 Runner 自己创建和释放
```

​        这是后台任务代码里非常重要的边界。

### 20.7.5 把 Runner 接入 FastAPI 生命周期
​        打开 `api/app/main.py`，新增 `lifespan`：
​        完整代码如下：

```Python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.application.agent_task_runner import AgentTaskRunner
from app.core.config import settings
from app.core.handlers import register_exception_handlers
from app.core.logging import configure_logging
from app.infrastructure.database.session import AsyncSessionLocal
from app.infrastructure.task_queue import RedisAgentTaskQueue, create_redis_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ===================== 第1步：创建 Redis 连接和任务队列 =====================
    redis = create_redis_client()
    queue = RedisAgentTaskQueue(redis)

    # ===================== 第2步：启动 AgentTaskRunner 后台循环 =====================
    runner = AgentTaskRunner(queue=queue, session_factory=AsyncSessionLocal)
    app.state.task_queue = queue
    app.state.task_runner = runner
    await redis.ping()
    runner.start()

    try:
        yield
    finally:
        # ===================== 第3步：应用关闭时释放后台任务和 Redis 连接 =====================
        await runner.stop()
        await redis.aclose()


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title=settings.api_app_name,
        version=settings.api_version,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )
    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
```

​        下面拆开看新增的生命周期代码：

```Python
@asynccontextmanager
async def lifespan(app: FastAPI):
    redis = create_redis_client()
    queue = RedisAgentTaskQueue(redis)

    runner = AgentTaskRunner(queue=queue, session_factory=AsyncSessionLocal)
    app.state.task_queue = queue
    app.state.task_runner = runner
    await redis.ping()
    runner.start()

    try:
        yield
    finally:
        await runner.stop()
        await redis.aclose()
```

​        再把 `lifespan` 传给 FastAPI：

```Python
app = FastAPI(
    title=settings.api_app_name,
    version=settings.api_version,
    lifespan=lifespan,
)
```

#### 20.7.5.1 代码讲解
​        FastAPI 生命周期分成两段：

```Plain
yield 之前：应用启动
yield 之后：应用关闭
```

​        启动时做：

```Plain
创建 Redis 连接
创建任务队列
创建并启动 Runner
把 queue 和 runner 放到 app.state
```

​        关闭时做：

```Plain
停止 Runner
关闭 Redis 连接
```

​        为什么要放到 `app.state`？
​        因为路由函数里需要拿到同一个任务队列：

```Python
def get_task_queue(request: Request) -> RedisAgentTaskQueue:
    return request.app.state.task_queue
```

​        这样每个请求不需要重新创建 Redis 连接。

### 20.7.6 编写任务 API
​        打开 `api/app/schemas/session.py`，新增：

```Python
class AgentTaskResponse(BaseModel):
    id: str
    session_id: UUID
    type: str
    status: str
    error: str | None
    created_at: str
    updated_at: str
```

#### 20.7.6.1 代码讲解
​        这个响应模型对应前端计划面板中的任务状态块。
​        启动任务接口：

```Python
@router.post(
    "/{session_id}/plan/tasks",
    response_model=ApiResponse[AgentTaskResponse],
)
async def start_plan_task(
    session_id: UUID,
    service: SessionService = Depends(build_session_service),
    queue: RedisAgentTaskQueue = Depends(get_task_queue),
) -> ApiResponse[AgentTaskResponse]:
    await service.get_session(session_id)
    task = await queue.enqueue_execute_plan(session_id)
    return ApiResponse(data=to_agent_task_response(task))
```

#### 20.7.6.2 业务讲解
​        这里不会直接执行计划。
​        它只做两件事：

```Plain
确认会话存在
把 execute_plan 任务写入 Redis Stream
```

​        所以这个接口会很快返回。
​        查询任务接口：

```Python
@router.get(
    "/tasks/{task_id}",
    response_model=ApiResponse[AgentTaskResponse],
)
async def get_agent_task(
    task_id: str,
    queue: RedisAgentTaskQueue = Depends(get_task_queue),
) -> ApiResponse[AgentTaskResponse]:
    task = await queue.get_task(task_id)
    if task is None:
        return ApiResponse(
            code=404,
            message="task not found",
            data=None,
        )
    return ApiResponse(data=to_agent_task_response(task))
```

​        取消任务接口：

```Python
@router.post(
    "/tasks/{task_id}/cancel",
    response_model=ApiResponse[AgentTaskResponse],
)
async def cancel_agent_task(
    task_id: str,
    queue: RedisAgentTaskQueue = Depends(get_task_queue),
) -> ApiResponse[AgentTaskResponse]:
    task = await queue.cancel_task(task_id)
    if task is None:
        return ApiResponse(
            code=404,
            message="task not found",
            data=None,
        )
    return ApiResponse(data=to_agent_task_response(task))
```

#### 20.7.6.3 代码讲解
​        本章把任务接口放在 `sessions` 路由下：

```Plain
/api/sessions/{session_id}/plan/tasks
/api/sessions/tasks/{task_id}
```

​        原因是当前任务都围绕会话执行。后续如果任务类型变多，可以再拆成独立的 `agent_tasks` 路由模块。

### 20.7.7 更新 Docker Compose
​        打开 `docker-compose.yml`，在 `api.environment` 中加入：

```YAML
REDIS_URL: ${REDIS_URL:-redis://redis:6379/0}
AGENT_TASK_STREAM: ${AGENT_TASK_STREAM:-agent:tasks}
AGENT_TASK_POLL_TIMEOUT_MS: ${AGENT_TASK_POLL_TIMEOUT_MS:-1000}
```

​        在 `api` 服务中加入依赖：

```YAML
depends_on:
  - postgres
  - redis
```

#### 20.7.7.1 代码讲解
​        API 启动时会执行：

```Python
await redis.ping()
```

​        所以 Docker Compose 里要让 `redis` 服务先创建。
​        注意：`depends_on` 只表示创建顺序，不保证 Redis 已经完全健康。如果刚启动的一瞬间 API 还没连上 Redis，可以执行：

```Bash
docker compose restart api nginx
```

### 20.7.8 更新前端类型和 API 函数
​        打开 `ui/app/types.ts`，新增任务类型：

```TypeScript
export type AgentTaskItem = {
  id: string;
  session_id: string;
  type: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  error: string | null;
  created_at: string;
  updated_at: string;
};
```

​        打开 `ui/app/lib/session-api.ts`，新增：
​        本章完成后，`ui/app/lib/session-api.ts` 的完整代码如下：

```TypeScript
import { requestApi } from "./api";
import { readSseStream } from "./sse";
import type {
  AgentTaskItem,
  ChatMessage,
  MessageCreateData,
  MessageListData,
  PlanCreateData,
  PlanExecuteData,
  SessionEventItem,
  SessionEventListData,
  SessionFileItem,
  SessionFileListData,
  SessionItem,
  SessionListData,
  StreamEvent,
} from "../types";

export function fetchSessions(): Promise<SessionItem[]> {
  return requestApi<SessionListData>("/api/sessions").then((data) => data.items);
}

export function createSession(title: string): Promise<SessionItem> {
  return requestApi<SessionItem>("/api/sessions", {
    method: "POST",
    body: JSON.stringify({ title }),
  });
}

export function deleteSession(sessionId: string): Promise<void> {
  return requestApi<void>(`/api/sessions/${sessionId}`, { method: "DELETE" });
}

export function stopSession(sessionId: string): Promise<SessionItem> {
  return requestApi<SessionItem>(`/api/sessions/${sessionId}/stop`, {
    method: "POST",
  });
}

export function clearUnread(sessionId: string): Promise<SessionItem> {
  return requestApi<SessionItem>(`/api/sessions/${sessionId}/read`, {
    method: "POST",
  });
}

export function fetchMessages(sessionId: string): Promise<ChatMessage[]> {
  return requestApi<MessageListData>(`/api/sessions/${sessionId}/messages`).then(
    (data) => data.items,
  );
}

export function fetchEvents(sessionId: string): Promise<SessionEventItem[]> {
  return requestApi<SessionEventListData>(
    `/api/sessions/${sessionId}/events`,
  ).then((data) => data.items);
}

export function fetchSessionFiles(sessionId: string): Promise<SessionFileItem[]> {
  return requestApi<SessionFileListData>(`/api/sessions/${sessionId}/files`).then(
    (data) => data.items,
  );
}

export async function uploadSessionFile(
  sessionId: string,
  file: File,
): Promise<SessionFileItem> {
  const formData = new FormData();
  formData.append("upload", file);

  const response = await fetch(`/api/sessions/${sessionId}/files`, {
    method: "POST",
    body: formData,
  });
  const payload = (await response.json()) as {
    code: number;
    message: string;
    data: SessionFileItem | null;
  };
  if (!response.ok || payload.code >= 400) {
    throw new Error(payload.message || `HTTP ${response.status}`);
  }
  if (!payload.data) {
    throw new Error("empty response");
  }
  return payload.data;
}

export function sendMessage(
  sessionId: string,
  content: string,
): Promise<MessageCreateData> {
  return requestApi<MessageCreateData>(`/api/sessions/${sessionId}/messages`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

export function createPlan(
  sessionId: string,
  task: string,
): Promise<PlanCreateData> {
  return requestApi<PlanCreateData>(`/api/sessions/${sessionId}/plan`, {
    method: "POST",
    body: JSON.stringify({ task }),
  });
}

export function executePlan(sessionId: string): Promise<PlanExecuteData> {
  return requestApi<PlanExecuteData>(
    `/api/sessions/${sessionId}/plan/execute`,
    {
      method: "POST",
    },
  );
}

export function startPlanTask(sessionId: string): Promise<AgentTaskItem> {
  return requestApi<AgentTaskItem>(`/api/sessions/${sessionId}/plan/tasks`, {
    method: "POST",
  });
}

export function fetchAgentTask(taskId: string): Promise<AgentTaskItem> {
  return requestApi<AgentTaskItem>(`/api/sessions/tasks/${taskId}`);
}

export function cancelAgentTask(taskId: string): Promise<AgentTaskItem> {
  return requestApi<AgentTaskItem>(`/api/sessions/tasks/${taskId}/cancel`, {
    method: "POST",
  });
}

export async function streamMessage(
  sessionId: string,
  content: string,
  onEvent: (event: StreamEvent) => void,
) {
  const response = await fetch(`/api/sessions/${sessionId}/messages/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({ content }),
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }

  await readSseStream(response, onEvent);
}
```

​        下面单独看第 20 章新增的三个任务函数：

```TypeScript
export function startPlanTask(sessionId: string): Promise<AgentTaskItem> {
  return requestApi<AgentTaskItem>(`/api/sessions/${sessionId}/plan/tasks`, {
    method: "POST",
  });
}

export function fetchAgentTask(taskId: string): Promise<AgentTaskItem> {
  return requestApi<AgentTaskItem>(`/api/sessions/tasks/${taskId}`);
}

export function cancelAgentTask(taskId: string): Promise<AgentTaskItem> {
  return requestApi<AgentTaskItem>(`/api/sessions/tasks/${taskId}/cancel`, {
    method: "POST",
  });
}
```

#### 20.7.8.1 代码讲解
​        前端现在有三个动作：

```Plain
startPlanTask  启动后台任务
fetchAgentTask 查询后台任务
cancelAgentTask 取消后台任务
```

​        这三个函数都只关心任务，不直接关心 ReActAgent 具体怎么执行。

### 20.7.9 更新 zustand store
​        打开 `ui/app/stores/session-store.ts`。
​        这个文件已经在前面章节积累了 600 多行代码，本章不要整篇重写。按下面四处修改即可。
​        第一处，在 import 区域补充任务 API 和任务类型：

```TypeScript
import {
  cancelAgentTask,
  fetchAgentTask,
  startPlanTask,
} from "../lib/session-api";
import type { AgentTaskItem } from "../types";
```

​        如果你的 import 已经是多行合并写法，就把这三个函数和 `AgentTaskItem` 合并到现有 import 中，不要重复写两个相同来源的 import。
​        第二处，在 `SessionState` 中新增状态：

```TypeScript
currentTask: AgentTaskItem | null;
executingPlan: boolean;
```

​        `currentTask` 用来显示当前后台任务：

```Plain
queued
running
succeeded
failed
cancelled
```

​        第三处，在 `SessionActions` 中新增取消任务 action：

```TypeScript
cancelPlanTask: () => Promise<void>;
```

​        第四处，在辅助函数区域新增：

```TypeScript
function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function isTerminalTaskStatus(status: AgentTaskItem["status"]) {
  return ["succeeded", "failed", "cancelled"].includes(status);
}
```

​        `sleep()` 用来让前端每隔 1 秒查询一次任务状态。
​        `isTerminalTaskStatus()` 用来判断任务是否已经结束。只要任务进入 `succeeded`、`failed` 或 `cancelled`，前端就应该停止轮询。
​        最后，把 store 里的 `executePlan` action 改成下面的完整代码，并新增 `cancelPlanTask`：

```TypeScript
executePlan: async () => {
  const sessionId = get().selectedSessionId;
  if (!sessionId) {
    set({ actionError: "请先选择一个会话" });
    return;
  }
  if (!get().latestPlan) {
    set({ actionError: "请先生成计划" });
    return;
  }

  set({ actionError: null, currentTask: null, executingPlan: true });
  try {
    // ===================== 第1步：只把任务放入 Redis Stream，不等待执行结束 =====================
    const queuedTask = await startPlanTask(sessionId);
    set({ currentTask: queuedTask });

    // ===================== 第2步：轮询任务状态，同时刷新事件面板 =====================
    let latestTask = queuedTask;
    while (!isTerminalTaskStatus(latestTask.status)) {
      await sleep(1000);
      latestTask = await fetchAgentTask(queuedTask.id);
      const events = await fetchEvents(sessionId);
      set({
        currentTask: latestTask,
        events: { type: "ready", data: events },
        latestPlan: applyExecutionEvents(getLatestPlan(events), events),
      });
    }

    // ===================== 第3步：任务结束后用数据库状态做最终刷新 =====================
    if (latestTask.status === "failed") {
      set({ actionError: latestTask.error ?? "任务执行失败" });
    }
    if (latestTask.status === "cancelled") {
      set({ actionError: "任务已取消" });
    }
    await get().loadSessionDetail(sessionId);
    await get().refreshSessions();
  } catch (error) {
    set({ actionError: getErrorMessage(error) });
  } finally {
    set({ executingPlan: false });
  }
},

cancelPlanTask: async () => {
  const task = get().currentTask;
  if (!task) {
    set({ actionError: "当前没有可取消的任务" });
    return;
  }

  set({ actionError: null });
  try {
    const cancelled = await cancelAgentTask(task.id);
    set({ currentTask: cancelled });
  } catch (error) {
    set({ actionError: getErrorMessage(error) });
  }
},
```

#### 20.7.9.1 代码讲解
​        这段代码在流程中的位置：

```Plain
PlanPanel 点击执行
  |
  v
store.executePlan()
  |
  v
POST /plan/tasks
  |
  v
GET /tasks/{task_id}
  |
  v
GET /events
```

​        输入是当前选中的会话 ID 和当前会话里的最新计划。
​        输出不是一个最终答案，而是页面状态变化：

```Plain
currentTask 更新为 queued/running/succeeded
events 更新为最新事件列表
latestPlan 根据 step_completed 更新步骤状态
```

​        流程是：

```Plain
第 1 步：启动任务，拿到 task_id
第 2 步：每秒查询一次任务状态
第 3 步：每次轮询时顺便刷新事件
第 4 步：任务进入终态后停止轮询
```

​        终态包括：

```Plain
succeeded
failed
cancelled
```

​        为什么轮询时要刷新事件？
​        因为真正的执行事件是 ReActAgentService 写入数据库的：

```Plain
step_started
tool_called
step_completed
task_done
```

​        前端刷新事件列表后，就能更新事件面板和步骤状态。
​        这里最容易写错的是 `latestPlan` 的更新。不要只把 `currentTask` 更新了就结束。任务状态只能说明“后台任务执行到哪里”，真正的步骤结果来自事件列表，所以每次轮询都要重新读取 `fetchEvents(sessionId)`。
​        另外，`cancelPlanTask()` 本章只是把 Redis 里的任务状态标记为 `cancelled`。如果 Runner 已经开始执行一个很短的计划，它可能很快就执行完了。长任务的精确中断会在后续章节继续增强。

### 20.7.10 更新计划面板
​        打开 `ui/app/components/plan-panel.tsx`。
​        新增 props：
​        本章完成后，`ui/app/components/plan-panel.tsx` 的完整代码如下：

```TypeScript
import { GitBranch, Loader2, Play, Sparkles, Square } from "lucide-react";

import type { AgentPlan, AgentTaskItem } from "../types";

type PlanPanelProps = {
  disabled: boolean;
  executing: boolean;
  onCancelTask: () => void;
  onCreatePlan: () => void;
  onExecutePlan: () => void;
  plan: AgentPlan | null;
  planning: boolean;
  task: AgentTaskItem | null;
};


// ===================== 第1步：展示当前会话的最新计划 =====================
export function PlanPanel({
  disabled,
  executing,
  onCancelTask,
  onCreatePlan,
  onExecutePlan,
  plan,
  planning,
  task,
}: PlanPanelProps) {
  const canCancelTask =
    task !== null && !["succeeded", "failed", "cancelled"].includes(task.status);

  return (
    <div className="rounded-md border border-slate-200 bg-white p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-slate-950">计划面板</h2>
          <p className="mt-1 text-sm text-slate-500">
            根据当前任务生成 PlannerAgent 步骤
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          <button
            className="inline-flex h-9 items-center gap-2 rounded-md border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400"
            disabled={disabled || planning || executing}
            onClick={onCreatePlan}
            type="button"
          >
            {planning ? (
              <Loader2 className="animate-spin" size={15} />
            ) : (
              <Sparkles size={15} />
            )}
            生成
          </button>
          <button
            className="inline-flex h-9 items-center gap-2 rounded-md border border-slate-200 bg-slate-950 px-3 text-sm font-medium text-white disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-200 disabled:text-slate-500"
            disabled={disabled || !plan || executing || planning}
            onClick={onExecutePlan}
            type="button"
          >
            {executing ? (
              <Loader2 className="animate-spin" size={15} />
            ) : (
              <Play size={15} />
            )}
            执行
          </button>
          <button
            className="inline-flex h-9 items-center gap-2 rounded-md border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400"
            disabled={!canCancelTask}
            onClick={onCancelTask}
            type="button"
          >
            <Square size={15} />
            取消
          </button>
        </div>
      </div>

      {task ? (
        <div className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-3 text-xs leading-5 text-slate-600">
          <div className="font-medium text-slate-900">后台任务：{task.status}</div>
          <div className="mt-1 break-all">任务 ID：{task.id}</div>
          {task.error ? (
            <div className="mt-1 text-rose-600">错误：{task.error}</div>
          ) : null}
        </div>
      ) : null}

      {plan ? (
        <div className="mt-4">
          <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
              <GitBranch size={16} aria-hidden="true" />
              {plan.title}
            </div>
            <p className="mt-2 text-sm leading-6 text-slate-600">{plan.goal}</p>
            <p className="mt-2 text-xs text-slate-500">来源：{plan.source}</p>
          </div>

          <ol className="mt-3 grid gap-3">
            {plan.steps.map((step, index) => (
              <li
                className="rounded-md border border-slate-200 bg-slate-50 p-3"
                key={step.id}
              >
                <div className="flex items-start gap-2">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-white text-xs font-semibold text-slate-500">
                    {index + 1}
                  </span>
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-slate-900">
                      {step.title}
                    </div>
                    <span className="mt-1 inline-flex rounded bg-white px-2 py-0.5 text-xs text-slate-500">
                      {step.status}
                    </span>
                    <p className="mt-1 text-sm leading-6 text-slate-600">
                      {step.description}
                    </p>
                    <p className="mt-2 text-xs leading-5 text-slate-500">
                      预期输出：{step.expected_output}
                    </p>
                  </div>
                </div>
              </li>
            ))}
          </ol>
        </div>
      ) : (
        <div className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-4 text-sm leading-6 text-slate-500">
          输入任务后点击生成，这里会出现结构化计划。
        </div>
      )}
    </div>
  );
}
```

​        下面再拆开看第 20 章新增的 props：

```TypeScript
type PlanPanelProps = {
  disabled: boolean;
  executing: boolean;
  onCancelTask: () => void;
  onCreatePlan: () => void;
  onExecutePlan: () => void;
  plan: AgentPlan | null;
  planning: boolean;
  task: AgentTaskItem | null;
};
```

​        新增任务状态展示：

```TypeScript
{task ? (
  <div className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-3 text-xs leading-5 text-slate-600">
    <div className="font-medium text-slate-900">后台任务：{task.status}</div>
    <div className="mt-1 break-all">任务 ID：{task.id}</div>
    {task.error ? (
      <div className="mt-1 text-rose-600">错误：{task.error}</div>
    ) : null}
  </div>
) : null}
```

#### 20.7.10.1 代码讲解
​        执行按钮负责启动任务。
​        取消按钮负责把任务标记为 `cancelled`。
​        任务状态块让用户能看到现在发生了什么：

```Plain
后台任务：queued
后台任务：running
后台任务：succeeded
后台任务：failed
后台任务：cancelled
```

​        这比只显示一个 loading 更适合 Agent 产品，因为 Agent 经常会执行较长时间。

## 20.8 关键理解
​        本章最重要的是理解“请求”和“任务”的区别。
​        同步请求是：

```Plain
浏览器请求开始
  |
  v
后端执行完整任务
  |
  v
浏览器拿到结果
```

​        后台任务是：

```Plain
浏览器提交任务
  |
  v
后端返回 task_id
  |
  v
后台 Runner 执行任务
  |
  v
浏览器查询 task_id 状态
```

​        第二个重点是 Redis Stream 和数据库事件表的区别。

```Plain
Redis Stream：让 Runner 知道有什么任务要执行
数据库事件表：让页面知道 Agent 执行过程中发生了什么
```

​        不要把这两者混在一起。
​        第三个重点是后台任务要创建自己的数据库会话。
​        HTTP 请求结束后，请求里的数据库会话就会释放。后台任务不能拿着已经结束的请求会话继续用。

## 20.9 技术难点与亮点
​        本章的技术难点在于把队列、状态、生命周期和前端轮询拆清楚。Redis Stream 负责排队，Redis Hash 负责状态查询，两者不能互相替代；FastAPI `lifespan` 既要在启动时连接 Redis 和启动 Runner，也要在关闭时取消后台任务并释放连接；Runner 不能复用请求里的数据库会话，而要在后台执行时创建独立会话。前端也要把任务轮询、事件刷新和步骤状态更新串起来，不能只看任务是否结束。
​        项目亮点在于 Agent 执行从同步 HTTP 请求升级成后台任务。前端能立即拿到 `task_id` 和任务状态，不再只能等接口返回；`ReActAgentService` 被 Runner 复用，没有重复实现执行逻辑；Redis Stream 也为后续长任务、沙箱工具、多 worker 和更细粒度取消打下了基础。

## 20.10 面试考点
​        面试里可以从长任务为什么不适合放在普通 HTTP 请求里讲起。普通请求适合短动作，后台任务适合可持续观察、可取消和可恢复的执行过程。Redis Stream 比 Redis List 更适合保留任务消息和扩展消费模型，但任务状态仍然需要放在 Hash 里，方便按 `task_id` 直接查询。FastAPI 后台任务必须创建独立数据库会话，因为它已经脱离了原始请求生命周期。`depends_on` 只能保证容器启动顺序，不能保证 Redis 已经健康；前端轮询适合本章这种任务状态查询，SSE 更适合后续实时推送事件。

## 20.11 运行验证
​        下面命令默认在项目根目录执行。

### 20.11.1 安装后端依赖
​        如果还没有同步第 20 章依赖：

```Bash
cd api
uv sync
```

### 20.11.2 检查后端编译

```Bash
uv run python -m compileall app
```

​        预期没有 Python 语法错误。

### 20.11.3 检查前端类型

```Bash
cd ../ui
pnpm typecheck
```

​        预期没有 TypeScript 报错。

### 20.11.4 启动服务
​        回到项目根目录：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
```

​        如果镜像已经存在，可以执行：

```Bash
docker compose up -d nginx
```

​        如果第 20 章后端依赖刚变更，需要重新构建 API：

```Bash
docker compose build api ui
docker compose up -d nginx
```

​        如果 Nginx 返回 502，通常是 API 刚重建后容器 IP 变化，可以执行：

```Bash
docker compose restart nginx
```

### 20.11.5 创建会话、发送消息、生成计划
​        创建会话：

```Bash
curl -X POST http://localhost:8088/api/sessions \
  -H "Content-Type: application/json" \
  -d '{"title":"第 20 章任务测试"}'
```

​        发送消息：

```Bash
curl -N -X POST http://localhost:8088/api/sessions/{session_id}/messages/stream \
  -H "Content-Type: application/json" \
  -d '{"content":"帮我规划一个 AI Agent 后台任务系统"}'
```

​        生成计划：

```Bash
curl -X POST http://localhost:8088/api/sessions/{session_id}/plan \
  -H "Content-Type: application/json" \
  -d '{"task":"帮我规划一个 AI Agent 后台任务系统"}'
```

### 20.11.6 启动后台执行任务

```Bash
curl -X POST http://localhost:8088/api/sessions/{session_id}/plan/tasks
```

​        预期返回：

```JSON
{
  "code": 200,
  "message": "success",
  "data": {
    "id": "...",
    "session_id": "...",
    "type": "execute_plan",
    "status": "queued",
    "error": null
  }
}
```

​        记录返回的 `id`，继续查询任务：

```Bash
curl http://localhost:8088/api/sessions/tasks/{task_id}
```

​        任务执行完成后，状态应该变成：

```Plain
succeeded
```

​        查询事件：

```Bash
curl http://localhost:8088/api/sessions/{session_id}/events
```

​        预期能看到：

```Plain
step_started
tool_called
step_completed
task_done
```

### 20.11.7 验证页面
​        访问：

```Plain
http://localhost:8088
```

​        在页面里验证时，先创建或选择一个会话，输入任务并发送，再点击“生成”得到计划。随后点击“执行”，计划面板应当显示后台任务状态，从 `queued` 进入 `running`，最后变成 `succeeded`。任务完成后，事件记录里应当出现步骤执行事件，计划步骤也应当更新为 `completed`。这说明 API 入队、Runner 消费、事件写入和前端轮询都已经接通。

## 20.12 最终实现修订：可靠消费与真实取消

前面的单消费者版本便于理解，但它从 Redis Stream 的 `$` 开始读取。API 在消息入队后、Runner 处理前重启时，这条消息可能永远不会再被读取。交付版改用 Consumer Group：

```text
XGROUP CREATE atlas:tasks atlas-agent-runner 0-0 MKSTREAM
XREADGROUP GROUP atlas-agent-runner <consumer> STREAMS atlas:tasks >
XAUTOCLAIM atlas:tasks atlas-agent-runner <consumer> <idle-ms> 0-0
XACK atlas:tasks atlas-agent-runner <message-id>
```

四个动作分别解决首次建组、消费新消息、接管崩溃消费者留下的 pending 消息和处理完成确认。Runner 只有在任务进入终态后才 ACK；异常退出留下的消息会在下次启动时被认领，因此交付版提供的是 **at-least-once**，不是 exactly-once。工具副作用仍要依赖第 70 章的幂等键去重。

Runner 同时保存 `task_id -> asyncio.Task` 的活动任务映射。取消接口不再只改 Redis 状态，而是先把状态写成 `stopped`，再调用协程的 `cancel()`。这能停止尚未完成的 Python 协程，但不能自动撤销已经提交到数据库、浏览器或外部服务的副作用；长工具还应实现自己的取消协议或补偿动作。

服务关闭与用户取消必须区别处理：用户取消已经产生明确终态，因此消息可以 ACK；服务关闭只是执行权转移，Runner 会取消本进程协程但不 ACK，消息继续留在 pending，等待下一实例接管。

Compose 中 Redis 使用 `noeviction`，避免内存压力下静默淘汰任务 Hash 或 Stream。正式环境还应配置持久化、监控 pending 数量，并为失败次数过多的消息增加死信处理。

相应的可靠性验收至少包括：

1. 消息入队后重启 API，旧消息仍会被消费；
2. Runner 中途退出后，pending 消息可被 `XAUTOCLAIM` 接管；
3. 成功、失败和取消任务最终都会 ACK；
4. 取消运行中任务后，执行协程确实停止；
5. 重复交付消息不会造成工具副作用重复执行。
6. 服务关闭时运行中消息不 ACK，用户取消的消息才进入终态并 ACK。

## 20.13 常见问题

### 20.13.1 API 启动失败并提示 Redis 连接不上怎么办
​        第 20 章的 API 启动时会连接 Redis，并在 `lifespan` 里执行 `redis.ping()`。先执行 `docker compose ps`，确认 `atlas-redis` 是否运行并健康。如果 Redis 刚启动完成，可以执行 `docker compose restart api nginx`，让 API 重新建立 Redis 连接，再让 Nginx 重新代理到健康的 API 容器。

### 20.13.2 点击执行后一直是 `queued` 怎么办
​        这说明任务已经写入 Redis Hash 和 Stream，但 Runner 没有成功消费。优先查看 API 日志：`docker compose logs --tail=100 api`。如果日志里有 Redis 连接、数据库连接或 Runner 循环异常，要先解决 Runner 启动问题；如果 API 没有重新构建，也可能仍然运行着上一章的旧代码。

### 20.13.3 任务状态是 `succeeded` 但页面步骤没更新怎么办
​        任务成功只说明 Runner 已经执行完成，页面步骤还依赖事件列表刷新。可以刷新页面，或者直接检查 `GET /api/sessions/{session_id}/events` 是否包含 `step_completed`。如果事件存在但页面没更新，要检查前端是否在轮询任务状态时同步刷新事件并调用 `applyExecutionEvents()`。

### 20.13.4 取消按钮为什么有时来不及取消
​        交付版会取消正在执行的协程，但取消请求仍可能晚于任务完成，也不能撤销已经发生的外部副作用。长任务应在循环中设置取消检查点；外部工具还要提供幂等键、取消协议或补偿动作。

### 20.13.5 为什么不用 Celery
​        Celery 是成熟方案，但本项目此时更需要让读者看清 Agent 任务、事件、状态和 Runner 之间的底层关系。Redis Stream 更轻量，也更容易和后续事件流、任务状态轮询和多 Agent 调度模型衔接。等理解了这一层，再替换成 Celery、RQ 或其他队列方案并不困难。

## 20.14 本章小结
​        本章完成了 Agent 后台任务的第一版闭环。后端增加 Redis 客户端依赖和任务配置，使用 Redis Stream 保存待执行任务，使用 Redis Hash 保存任务状态，并编写 `AgentTaskRunner` 在后台消费任务；FastAPI 启动时会创建 Redis 连接、任务队列和 Runner，关闭时会停止后台循环并释放连接。接口层新增了启动任务、查询任务和取消任务三类能力。
​        前端计划面板不再只是等待同步接口返回，而是会先拿到任务状态，再轮询任务进度，刷新事件列表和步骤状态。从这一章开始，Agent 执行不再依赖单个 HTTP 请求等待完成。后续长任务、沙箱工具、浏览器操作和用户中断都会建立在这个后台任务模型上。

## 20.15 下一章预告
​        第 21 章会进入上下文工程，处理长任务执行中的记忆压缩、上下文裁剪、文件系统替代消息列表等问题。

## 20.16 代码
​        暂时无法在飞书文档外展示此内容
