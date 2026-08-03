# 第二十九章. 复杂任务复原与 Agent Harness

## 29.1 合章说明

​        旧版教程把“复杂任务状态、重试与复原”与“Agent Harness 量度与回放”拆成了相邻两章。两者实际上属于同一条能力链：前者把基础结构立住，后者让它进入可用状态。本章将它们合并为前后两个阶段，保留原来的实现、验证与工程判断，同时减少能力尚未闭环时的章节跳转。

## 29.2 第一阶段：复杂任务状态、重试与复原

### 29.2.1 本阶段目标

​        学完本阶段后，你将能够：

​        从实现顺序看，第一，理解长任务为什么不能只用 `running`、`failed`、`succeeded` 三种状态；第二，为后台任务补齐 `waiting`、`completed`、`stopped` 等状态语义；第三，区分“失败 failed”和“用户停止 stopped”；第四，让失败或停止的任务可以创建重试任务；第五，通过会话 ID 恢复最近一次后台任务状态；第六，扩展前端任务类型，让页面能识别等待中、已完成、已停止状态；第七，使用单元测试验证任务重试和恢复逻辑。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

### 29.2.2 最终效果

​        本阶段结束后，后台任务状态会支持：

```Plain
queued     已进入队列，等待 Runner 消费
running    Runner 正在执行
waiting    等待外部资源、人工继续或后续恢复
completed  正常完成
failed     执行失败
stopped    用户主动停止
```

​        原来早期章节中的：

```Plain
succeeded
cancelled
```

​        仍然保留在枚举中，用来兼容已经存在的旧任务数据。

​        新增接口：

```Plain
POST /api/sessions/tasks/{task_id}/retry
GET  /api/sessions/{session_id}/tasks/latest
```

​        请求链路变成：

```Plain
失败或停止的旧任务
  |
  v
POST /tasks/{task_id}/retry
  |
  v
创建新的 queued 任务
  |
  +-- parent_task_id 指向旧任务
  +-- retry_count + 1
  |
  v
Redis Stream 等待 AgentTaskRunner 消费
```

​        会话重新打开时，可以通过：

```Plain
GET /api/sessions/{session_id}/tasks/latest
```

​        恢复最近任务状态。

### 29.2.3 本阶段要解决的问题

​        第 14 章引入 Redis Stream 后，后台任务已经可以排队、执行、失败和取消。

​        但是随着任务变复杂，简单状态不够用了。

​        真实 Agent 任务可能会遇到：

```Plain
外部工具暂时不可用
浏览器页面一直加载
用户手动停止
某个步骤失败但可以重试
用户刷新页面后需要恢复任务状态
```

​        如果任务只有：

```Plain
queued
running
succeeded
failed
cancelled
```

​        就会出现几个问题：

​        放到工程语境里看，第一，不知道任务是系统失败，还是用户主动停止；第二，不知道任务是否等待外部资源；第三，失败后只能重新手动创建任务，无法追溯原任务；第四，页面刷新后不知道当前会话最近任务是什么；第五，后续 Harness 和任务回放无法关联重试链路。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        所以本阶段先补任务状态模型。

### 29.2.4 本阶段技术方案

​        本阶段重点修改：

```Plain
RedisAgentTaskQueue
```

​        它仍然使用 Redis Hash 保存任务详情，用 Redis Stream 投递执行任务。

​        新增字段：

```Plain
parent_task_id  本任务由哪个任务重试而来
retry_count     当前是第几次重试
```

​        新增 Redis Key：

```Plain
agent:session:{session_id}:latest-task
```

​        它保存当前会话最近一次任务 ID。

​        这样页面重新打开会话时，可以恢复任务状态：

```Plain
session_id
  |
  v
latest-task key
  |
  v
task_id
  |
  v
agent:task:{task_id}
```

​        本阶段暂时不做这些内容：

​        展开来看，第一，不做自动重试策略；第二，不做多次失败后的退避重试；第三，不做人工确认后继续执行；第四，不做沙箱资源彻底清理；第五，不做任务事件回放页面。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        这些会在后续 Harness、回放和生产化章节继续增强。

### 29.2.5 新增和修改的文件

```Plain
README.md
api/README.md
api/app/infrastructure/task_queue.py
api/app/application/agent_task_runner.py
api/app/presentation/http/routes/sessions.py
api/app/schemas/session.py
api/tests/test_task_queue_recovery.py
ui/app/types.ts
ui/app/components/conversation-timeline.tsx
docs/course/chapters/44-task-retry-recovery.md
```

### 29.2.6 实施步骤
#### 29.2.6.1 先写任务队列测试

​        创建：

```Plain
api/tests/test_task_queue_recovery.py
```

​        完整代码如下：

```Python
import unittest
from uuid import uuid4

from app.infrastructure.task_queue import AgentTaskStatus, RedisAgentTaskQueue

class FakeRedis:
    """用内存字典模拟 Redis Hash 和 Stream，避免单元测试依赖真实 Redis。"""

    def __init__(self) -> None:
        self.hashes: dict[str, dict] = {}
        self.streams: list[tuple[str, dict]] = []

    async def hset(self, key: str, mapping: dict) -> None:
        self.hashes[key] = dict(mapping)

    async def hgetall(self, key: str) -> dict:
        return dict(self.hashes.get(key, {}))

    async def xadd(self, stream_name: str, payload: dict) -> str:
        self.streams.append((stream_name, dict(payload)))
        return f"{len(self.streams)}-0"

class RedisAgentTaskQueueRecoveryTest(unittest.IsolatedAsyncioTestCase):
    # ===================== 第1步：失败任务可以创建重试任务 =====================
    async def test_retry_failed_task_creates_new_task_with_parent(self) -> None:
        session_id = uuid4()
        redis = FakeRedis()
        queue = RedisAgentTaskQueue(redis)

        original = await queue.enqueue_execute_plan(session_id)
        await queue.mark_failed(original.id, "tool failed")

        retry = await queue.retry_task(original.id)

        self.assertIsNotNone(retry)
        assert retry is not None
        self.assertEqual(retry.session_id, session_id)
        self.assertEqual(retry.status, AgentTaskStatus.queued)
        self.assertEqual(retry.parent_task_id, original.id)
        self.assertEqual(retry.retry_count, 1)

    # ===================== 第2步：会话可以恢复最近一次任务状态 =====================
    async def test_recover_session_task_returns_latest_task(self) -> None:
        session_id = uuid4()
        redis = FakeRedis()
        queue = RedisAgentTaskQueue(redis)

        first = await queue.enqueue_execute_plan(session_id)
        await queue.mark_failed(first.id, "first failed")
        retry = await queue.retry_task(first.id)

        latest = await queue.recover_session_task(session_id)

        self.assertIsNotNone(latest)
        assert latest is not None
        assert retry is not None
        self.assertEqual(latest.id, retry.id)
        self.assertEqual(latest.parent_task_id, first.id)

    # ===================== 第3步：运行中的任务可以进入 waiting，再恢复为 running =====================
    async def test_task_can_enter_waiting_and_resume_running(self) -> None:
        session_id = uuid4()
        redis = FakeRedis()
        queue = RedisAgentTaskQueue(redis)

        task = await queue.enqueue_execute_plan(session_id)
        await queue.mark_running(task.id)
        waiting = await queue.mark_waiting(task.id, "waiting for external tool")
        running = await queue.mark_running(task.id)

        self.assertIsNotNone(waiting)
        self.assertEqual(waiting.status, AgentTaskStatus.waiting)
        self.assertEqual(waiting.error, "waiting for external tool")
        self.assertIsNotNone(running)
        self.assertEqual(running.status, AgentTaskStatus.running)

if __name__ == "__main__":
    unittest.main()
```

##### 29.2.6.1.1 测试覆盖了什么

​        这组测试覆盖三件事：

​        具体来说，第一，失败任务可以创建新任务；第二，新任务能记录 `parent_task_id` 和 `retry_count`；第三，通过会话 ID 可以恢复最近任务；第四，任务可以进入 `waiting`，之后重新回到 `running`。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        这些都是复杂任务状态管理的基础。

#### 29.2.6.2 扩展任务状态和任务字段

​        打开：

```Plain
api/app/infrastructure/task_queue.py
```

​        把任务状态改成：

```Python
class AgentTaskStatus(StrEnum):
    queued = "queued"
    running = "running"
    waiting = "waiting"
    completed = "completed"
    failed = "failed"
    stopped = "stopped"
    # 兼容早期章节已经返回过的状态值。
    succeeded = "succeeded"
    cancelled = "cancelled"
```

​        扩展 `AgentTask`：

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
    parent_task_id: str | None = None
    retry_count: int = 0
```

##### 29.2.6.2.1 字段含义

​        换句话说，第一，`parent_task_id`：如果这个任务是重试任务，它指向原任务 ID；第二，`retry_count`：当前重试次数，第一次重试是 `1`。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        这样后续可以形成重试链：

```Plain
task A failed
  |
  v
task B parent_task_id=A retry_count=1
  |
  v
task C parent_task_id=B retry_count=2
```

#### 29.2.6.3 写入会话最近任务索引

​        修改 `enqueue_execute_plan()`：

```Python
async def enqueue_execute_plan(
    self,
    session_id: UUID,
    *,
    parent_task_id: str | None = None,
    retry_count: int = 0,
) -> AgentTask:
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
        parent_task_id=parent_task_id,
        retry_count=retry_count,
    )
    await self._write_task(task)
    await self._write_latest_session_task(task)
    await self.redis.xadd(
        self.stream_name,
        {
            "task_id": task.id,
            "session_id": str(session_id),
            "type": task.type,
            "parent_task_id": parent_task_id or "",
            "retry_count": str(retry_count),
        },
    )
    return task
```

​        新增：

```Python
async def _write_latest_session_task(self, task: AgentTask) -> None:
    await self.redis.hset(
        self._latest_task_key(task.session_id),
        mapping={
            "task_id": task.id,
            "updated_at": task.updated_at,
        },
    )
```

##### 29.2.6.3.1 这段代码在流程中的位置

​        每次创建新任务，队列都会同时写两份数据：

```Plain
agent:task:{task_id}                    任务详情
agent:session:{session_id}:latest-task  这个会话最近任务 ID
```

​        第二份数据是给页面恢复用的。

#### 29.2.6.4 新增重试和恢复方法

​        继续在 `RedisAgentTaskQueue` 中新增：

```Python
async def retry_task(self, task_id: str) -> AgentTask | None:
    """基于历史任务创建一个新的 queued 任务。"""

    task = await self.get_task(task_id)
    if task is None:
        return None
    if task.status not in {
        AgentTaskStatus.failed,
        AgentTaskStatus.stopped,
        AgentTaskStatus.cancelled,
        AgentTaskStatus.completed,
        AgentTaskStatus.succeeded,
    }:
        return task

    return await self.enqueue_execute_plan(
        task.session_id,
        parent_task_id=task.id,
        retry_count=task.retry_count + 1,
    )

async def recover_session_task(self, session_id: UUID) -> AgentTask | None:
    """读取某个会话最近一次后台任务状态。"""

    data = await self.redis.hgetall(self._latest_task_key(session_id))
    task_id = str(data.get("task_id") or "")
    if not task_id:
        return None
    return await self.get_task(task_id)
```

​        新增 `waiting` 状态更新：

```Python
async def mark_waiting(self, task_id: str, reason: str | None = None) -> AgentTask | None:
    return await self._update_status(task_id, AgentTaskStatus.waiting, error=reason)
```

​        把完成状态改成：

```Python
async def mark_succeeded(self, task_id: str) -> AgentTask | None:
    return await self._update_status(task_id, AgentTaskStatus.completed)
```

​        这里保留方法名 `mark_succeeded()` 是为了减少旧代码改动，但返回状态改成 `completed`。

##### 29.2.6.4.1 为什么 stopped 比 cancelled 更清楚

​        `cancelled` 容易让人理解成队列层取消。

​        `stopped` 更贴近 Agent 产品语义：

```Plain
用户主动停止了这个任务
```

​        所以本阶段后续新状态用 `stopped`，但旧的 `cancelled` 仍然兼容读取。

#### 29.2.6.5 更新 AgentTaskRunner

​        打开：

```Plain
api/app/application/agent_task_runner.py
```

​        把取消判断更新为：

```Python
if task is None or task.status in {AgentTaskStatus.stopped, AgentTaskStatus.cancelled}:
    return
```

​        执行结束前也要检查：

```Python
latest_task = await self.queue.get_task(task_id)
if latest_task and latest_task.status in {AgentTaskStatus.stopped, AgentTaskStatus.cancelled}:
    return
await self.queue.mark_succeeded(task_id)
```

##### 29.2.6.5.1 为什么要两次检查停止状态

​        第一次检查发生在任务开始前。

​        第二次检查发生在任务执行后、标记完成前。

​        这样用户在任务执行中点击停止时，Runner 不会再把它改回 `completed`。

#### 29.2.6.6 扩展 API 响应和路由

​        打开 `api/app/schemas/session.py`，扩展 `AgentTaskResponse`：

```Python
class AgentTaskResponse(BaseModel):
    id: str
    session_id: UUID
    type: str
    status: str
    error: str | None
    created_at: str
    updated_at: str
    parent_task_id: str | None = None
    retry_count: int = 0
```

​        打开 `api/app/presentation/http/routes/sessions.py`，更新响应转换：

```Python
def to_agent_task_response(task: AgentTask) -> AgentTaskResponse:
    return AgentTaskResponse(
        id=task.id,
        session_id=task.session_id,
        type=task.type,
        status=task.status.value,
        error=task.error,
        created_at=task.created_at,
        updated_at=task.updated_at,
        parent_task_id=task.parent_task_id,
        retry_count=task.retry_count,
    )
```

​        新增重试接口：

```Python
@router.post(
    "/tasks/{task_id}/retry",
    response_model=ApiResponse[AgentTaskResponse],
)
async def retry_agent_task(
    task_id: str,
    queue: RedisAgentTaskQueue = Depends(get_task_queue),
) -> ApiResponse[AgentTaskResponse]:
    task = await queue.retry_task(task_id)
    if task is None:
        return ApiResponse(
            code=404,
            message="task not found",
            data=None,
        )
    return ApiResponse(data=to_agent_task_response(task))
```

​        新增恢复接口：

```Python
@router.get(
    "/{session_id}/tasks/latest",
    response_model=ApiResponse[AgentTaskResponse],
)
async def recover_latest_session_task(
    session_id: UUID,
    queue: RedisAgentTaskQueue = Depends(get_task_queue),
) -> ApiResponse[AgentTaskResponse]:
    task = await queue.recover_session_task(session_id)
    if task is None:
        return ApiResponse(
            code=404,
            message="task not found",
            data=None,
        )
    return ApiResponse(data=to_agent_task_response(task))
```

#### 29.2.6.7 更新前端任务类型

​        打开：

```Plain
ui/app/types.ts
```

​        扩展 `AgentTaskItem`：

```TypeScript
export type AgentTaskItem = {
  id: string;
  session_id: string;
  type: string;
  status:
    | "queued"
    | "running"
    | "waiting"
    | "completed"
    | "succeeded"
    | "failed"
    | "stopped"
    | "cancelled";
  error: string | null;
  created_at: string;
  updated_at: string;
  parent_task_id: string | null;
  retry_count: number;
};
```

​        打开：

```Plain
ui/app/components/conversation-timeline.tsx
```

​        更新任务状态展示：

```TypeScript
function TaskStatusCard({ task }: { task: AgentTaskItem | null }) {
  if (
    !task ||
    ["completed", "succeeded", "failed", "stopped", "cancelled"].includes(
      task.status,
    )
  ) {
    return null;
  }

  return (
    <RunningBlock
      text={
        task.status === "waiting"
          ? "后台任务等待外部资源或人工继续"
          : `后台任务正在执行：${task.status}`
      }
    />
  );
}
```

##### 29.2.6.7.1 为什么前端先只改类型和展示

​        本阶段重点是后端任务状态模型。

​        前端先保证：

​        从实现顺序看，第一，新状态不会类型报错；第二，`waiting` 能显示可读文案；第三，`completed/stopped` 不再被误认为运行中。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        更完整的重试按钮、恢复提示和任务回放会在后续章节继续产品化。

### 29.2.7 关键理解

​        本阶段最重要的是理解：

```Plain
任务状态是 Agent 产品体验的核心协议。
```

​        如果状态设计不清楚，前端、后端、Runner、工具、Harness 都会各自解释任务进度。

​        本阶段把状态分成三类：

```Plain
开始前：queued
进行中：running、waiting
终态：completed、failed、stopped
```

​        第二个重点是重试链。

​        重试不是把旧任务状态改回 queued。

​        而是创建一个新任务：

```Plain
旧任务保留失败原因
新任务记录 parent_task_id
```

​        这样才能追踪历史。

### 29.2.8 技术难点与亮点

​        技术难点：

​        放到工程语境里看，第一，要兼容早期 `succeeded/cancelled` 状态；第二，停止任务不能在执行结束后被 Runner 改回 completed；第三，重试任务需要保留原任务关系；第四，页面刷新后要能按会话恢复最近任务。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        项目亮点：

​        展开来看，第一，任务状态更接近真实长任务系统；第二，失败和用户停止被明确区分；第三，重试链路有 `parent_task_id` 和 `retry_count`；第四，会话最近任务可以恢复；第五，队列逻辑有单元测试保护。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

### 29.2.9 面试考点

​        具体来说，第一，为什么任务重试不应该复用原任务 ID？；第二，`failed` 和 `stopped` 有什么区别？；第三，`waiting` 适合表达哪些场景？；第四，为什么需要按会话保存 latest task？；第五，为什么要保留旧状态兼容？。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

### 29.2.10 运行验证

​        下面命令默认在项目根目录执行：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
```

#### 29.2.10.1 运行后端测试

```Bash
cd api
uv run python -m unittest discover -s tests -v
```

​        预期能看到：

```Plain
test_retry_failed_task_creates_new_task_with_parent ... ok
test_recover_session_task_returns_latest_task ... ok
test_task_can_enter_waiting_and_resume_running ... ok
```

#### 29.2.10.2 编译后端

```Bash
uv run python -m compileall app
```

​        预期没有语法错误。

#### 29.2.10.3 检查前端

```Bash
cd ../ui
pnpm typecheck
pnpm build
```

​        预期没有 TypeScript 报错。

#### 29.2.10.4 启动服务

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
docker compose build api ui
docker compose up -d nginx
docker compose exec api uv run alembic upgrade head
```

​        本阶段没有新增数据库迁移。

#### 29.2.10.5 创建会话和后台任务

​        创建会话：

```Bash
curl -X POST http://localhost:8088/api/sessions \
  -H "Content-Type: application/json" \
  -d '{"title":"第 44 章任务状态测试"}'
```

​        先创建计划：

```Bash
curl -X POST http://localhost:8088/api/sessions/{session_id}/plan \
  -H "Content-Type: application/json" \
  -d '{"task":"请搜索 FastAPI 资料并总结"}'
```

​        启动后台计划任务：

```Bash
curl -X POST http://localhost:8088/api/sessions/{session_id}/plan/tasks
```

​        返回中会包含：

```Plain
id
status: queued
retry_count: 0
```

#### 29.2.10.6 恢复最近任务状态

```Bash
curl http://localhost:8088/api/sessions/{session_id}/tasks/latest
```

​        预期能看到最近任务。

#### 29.2.10.7 停止并重试任务

​        如果任务还没有完成，可以停止：

```Bash
curl -X POST http://localhost:8088/api/sessions/tasks/{task_id}/cancel
```

​        本阶段开始，这个接口会返回：

```Plain
status: stopped
```

​        然后重试：

```Bash
curl -X POST http://localhost:8088/api/sessions/tasks/{task_id}/retry
```

​        预期返回新任务：

```Plain
status: queued
parent_task_id: {task_id}
retry_count: 1
```

### 29.2.11 阶段小结

​        本阶段完成了复杂任务状态的第一轮增强：

​        换句话说，第一，新增 `waiting/completed/stopped` 状态；第二，保留 `succeeded/cancelled` 兼容旧数据；第三，`AgentTask` 新增 `parent_task_id` 和 `retry_count`；第四，队列创建任务时写入会话最近任务索引；第五，新增 `retry_task()`；第六，新增 `recover_session_task()`；第七，新增重试和恢复 API；第八，前端类型支持新任务状态；第九，新增任务队列重试和恢复单元测试。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        从这一阶段开始，任务不再只是简单开始和结束，而是具备了失败追踪、停止区分、重试链路和会话恢复能力。

## 29.3 第二阶段：Agent Harness 量度与回放

### 29.3.1 本阶段目标

​        学完本阶段后，你将能够：

​        从实现顺序看，第一，理解为什么 Agent 项目需要 Harness，而不只是普通单元测试；第二，使用固定任务集保存回归评测用例；第三，为 Agent 事件流编写基础断言；第四，区分稳定模拟评测和真实模型评测；第五，通过接口运行 Harness 用例并查看断言结果；第六，在前端设置页增加 Harness 运行和回放入口；第七，为后续测试、调试和可观测性章节打基础。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

### 29.3.2 最终效果

​        本阶段结束后，会新增一组 Harness 接口：

```Plain
GET  /api/harness/cases
POST /api/harness/cases/{case_id}/run
GET  /api/harness/runs/{run_id}
GET  /api/harness/runs/{run_id}/replay
```

​        访问：

```Plain
http://localhost:8088
```

​        点击左侧“设置”，页面中会出现：

```Plain
Agent Harness
```

​        你可以：

​        放到工程语境里看，第一，查看固定评测任务集；第二，点击“模拟运行”；第三，查看 required event、required tool、forbidden event 等断言结果；第四，点击“回放”，查看这次运行产生的事件流。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

### 29.3.3 本阶段要解决的问题

​        前面章节已经有了 Planner、ReAct、工具选择、上下文工程、长期记忆、多 Agent、重试和恢复。

​        但是 Agent 系统有一个很现实的问题：

```Plain
今天改了提示词，昨天能跑通的工具调用还正常吗？
今天换了模型，任务规划是不是退化了？
今天重构了事件结构，前端还能正确展示过程吗？
```

​        如果每次都靠手动打开页面、输入任务、肉眼判断，就会有三个问题：

​        展开来看，第一，结果不稳定，真实模型和外部网页会变化；第二，覆盖不系统，容易只验证自己刚改过的地方；第三，失败难复盘，无法快速看到哪一步事件、工具或产物缺失。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        所以本阶段加入 Agent Harness。

​        Harness 的职责是：

```Plain
固定任务集
  |
  v
运行任务
  |
  v
收集事件流、工具调用和产物
  |
  v
执行断言
  |
  v
保存结果并支持回放
```

### 29.3.4 本阶段技术方案

​        本阶段先实现稳定的 `simulate` 模式。

​        它不会调用真实 LLM、搜索引擎、浏览器或外部网站，而是根据用例预期生成一组稳定事件，再用同一套断言逻辑评估事件流。

​        这样设计不是偷懒，而是为了把 Harness 的基础设施先做稳：

​        具体来说，第一，固定任务集怎么保存？；第二，事件流怎么评估？；第三，断言结果怎么表达？；第四，失败任务怎么回放？；第五，前端怎么查看评测结果？。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        后续如果要加入真实模型模式，只需要把真实 Agent Runner 的事件流传给同一个：

```Plain
evaluate_events()
```

​        本阶段会新增：

```Plain
api/config/eval_cases.yaml
api/app/domain/harness/entities.py
api/app/application/agent_harness_service.py
api/app/schemas/harness.py
api/app/presentation/http/routes/harness.py
api/tests/test_agent_harness_service.py
ui/app/lib/harness-api.ts
ui/app/components/harness-panel.tsx
```

​        本阶段暂时不做：

​        换句话说，第一，不把 Harness 运行结果落库；第二，不做真实模型批量评测；第三，不做自动评分大模型；第四，不做 CI 自动执行；第五，不做复杂指标报表。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        这些内容会在测试、调试、可观测性和生产化章节继续扩展。

### 29.3.5 实施步骤
#### 29.3.5.1 创建固定任务集

​        创建：

```Plain
api/config/eval_cases.yaml
```

​        完整代码如下：

```YAML
cases:
  - id: browser_observation
    title: 浏览器观察任务
    task: 请访问 https://example.com 并截图观察页面
    description: 验证浏览器工具是否能完成打开网页和截图这条基础链路。
    tags:
      - browser
      - tool
      - regression
    expectation:
      required_events:
        - message_created
        - plan_created
        - task_done
      required_tools:
        - browser_open
        - browser_screenshot
      required_files: []
      forbidden_events:
        - task_error
```

##### 29.3.5.1.1 代码讲解

​        `eval_cases.yaml` 是 Harness 的固定任务集。

​        每条用例包含：

​        从实现顺序看，第一，`id`：稳定标识，接口运行时会用它定位用例；第二，`title`：页面展示标题；第三，`task`：要交给 Agent 的任务文本；第四，`description`：为什么要测这条任务；第五，`tags`：分类标签，后续可以按 browser、memory、multi_agent 过滤；第六，`expectation`：断言规则。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        `required_events` 表示事件流里必须出现这些事件。

​        `required_tools` 表示事件流里必须出现这些工具调用。

​        `forbidden_events` 表示不能出现这些事件。例如 `task_error` 出现时，就说明这条任务失败。

#### 29.3.5.2 定义 Harness 领域实体

​        创建：

```Plain
api/app/domain/harness/entities.py
```

​        核心代码如下：

```Python
from dataclasses import dataclass, field
from datetime import datetime

@dataclass(slots=True)
class HarnessExpectation:
    """一条评测用例的断言规则。"""

    required_events: list[str] = field(default_factory=list)
    required_tools: list[str] = field(default_factory=list)
    required_files: list[str] = field(default_factory=list)
    forbidden_events: list[str] = field(default_factory=list)

@dataclass(slots=True)
class HarnessCase:
    """固定任务集中的一条 Agent 回归任务。"""

    id: str
    title: str
    task: str
    description: str
    tags: list[str]
    expectation: HarnessExpectation

@dataclass(slots=True)
class HarnessAssertion:
    """一次 Harness 运行里的单条断言结果。"""

    name: str
    passed: bool
    detail: str

@dataclass(slots=True)
class HarnessRun:
    """一次 Harness 运行结果。"""

    id: str
    case_id: str
    mode: str
    status: str
    task: str
    prompt_summary: str
    events: list[dict]
    assertions: list[HarnessAssertion]
    started_at: datetime
    completed_at: datetime | None
```

##### 29.3.5.2.1 代码讲解

​        这组实体只描述 Harness 自己的业务概念，不依赖 FastAPI、Pydantic 或数据库。

​        `HarnessExpectation` 是“应该发生什么、不应该发生什么”。

​        `HarnessCase` 是一条固定任务。

​        `HarnessAssertion` 是一次运行里的检查结果。例如：

```Plain
required_tool:browser_open passed
required_tool:browser_screenshot passed
forbidden_event:task_error passed
```

​        `HarnessRun` 是一次完整运行。它保存：

​        放到工程语境里看，第一，运行模式；第二，用例 ID；第三，prompt 摘要；第四，事件流；第五，断言结果；第六，开始和结束时间。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        本阶段先把 `events` 保留为 `dict`，因为 Harness 以后可能评估来自不同来源的事件：真实 Runner、模拟 Runner、历史回放、测试 fixture。

#### 29.3.5.3 实现 AgentHarnessService

​        创建：

```Plain
api/app/application/agent_harness_service.py
```

​        关键代码如下：

```Python
class AgentHarnessService:
    """运行 Agent 回归评测任务集。"""

    def __init__(self, case_file: Path | None = None) -> None:
        # ===================== 第1步：确定评测任务集文件 =====================
        api_root = Path(__file__).resolve().parents[2]
        self.case_file = case_file or api_root / "config" / "eval_cases.yaml"

        # ===================== 第2步：准备进程内运行结果存储 =====================
        self._runs: dict[str, HarnessRun] = {}
```

​        继续实现运行逻辑：

```Python
    def run_case(self, case_id: str, mode: str = "simulate") -> HarnessRun:
        """运行单条 Harness 用例。"""

        # ===================== 第1步：读取用例并校验运行模式 =====================
        case = self.get_case(case_id)
        if mode != "simulate":
            raise AppException(
                message="only simulate mode is available in this chapter",
                code=400,
                status_code=400,
            )

        # ===================== 第2步：生成稳定事件流 =====================
        started_at = self._now()
        events = self._simulate_events(case)

        # ===================== 第3步：对事件流执行断言 =====================
        assertions = self.evaluate_events(case, events)
        passed = all(assertion.passed for assertion in assertions)
        completed_at = self._now()

        # ===================== 第4步：保存运行结果，供失败回放接口读取 =====================
        run = HarnessRun(
            id=str(uuid4()),
            case_id=case.id,
            mode=mode,
            status="passed" if passed else "failed",
            task=case.task,
            prompt_summary=self._build_prompt_summary(case),
            events=events,
            assertions=assertions,
            started_at=started_at,
            completed_at=completed_at,
        )
        self._runs[run.id] = run
        return run
```

##### 29.3.5.3.1 业务流程

​        运行一条 Harness 用例时，会经过：

```Plain
读取 case
  |
  v
生成模拟事件流
  |
  v
执行 required/forbidden 断言
  |
  v
保存 HarnessRun
  |
  v
返回运行结果
```

##### 29.3.5.3.2 为什么先做 simulate

​        真实 Agent 运行会依赖模型、搜索、浏览器、网络和沙箱状态。它适合做最终验收，但不适合作为每次开发改动后的最小回归验证。

​        `simulate` 模式让我们先稳定这些基础设施：

​        展开来看，第一，用例读取；第二，断言逻辑；第三，回放接口；第四，前端结果展示。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        等这些稳定后，再把真实 Runner 的事件流接进来。

#### 29.3.5.4 编写断言逻辑

​        `evaluate_events()` 是本阶段最重要的函数：

```Python
    def evaluate_events(
        self,
        case: HarnessCase,
        events: list[dict],
    ) -> list[HarnessAssertion]:
        """对一组事件执行 Harness 断言。"""

        # ===================== 第1步：抽取事件类型、工具名和产物名 =====================
        event_types = {str(event.get("type")) for event in events}
        tool_names = {
            str(event.get("payload", {}).get("tool_name"))
            for event in events
            if event.get("type") == "tool_called"
        }
        file_names = {
            str(event.get("payload", {}).get("file_name"))
            for event in events
            if event.get("type") == "file_created"
        }

        # ===================== 第2步：逐类规则生成断言结果 =====================
        assertions: list[HarnessAssertion] = []
        assertions.extend(
            self._assert_contains(
                name="required_event",
                expected=case.expectation.required_events,
                actual=event_types,
            )
        )
        assertions.extend(
            self._assert_contains(
                name="required_tool",
                expected=case.expectation.required_tools,
                actual=tool_names,
            )
        )
        assertions.extend(
            self._assert_contains(
                name="required_file",
                expected=case.expectation.required_files,
                actual=file_names,
            )
        )
        assertions.extend(
            self._assert_absent(
                name="forbidden_event",
                expected_absent=case.expectation.forbidden_events,
                actual=event_types,
            )
        )
        return assertions
```

##### 29.3.5.4.1 代码讲解

​        这里故意只依赖事件字典。

​        因为 Harness 不应该只服务于某一个接口。未来事件可能来自：

​        具体来说，第一，SSE 真实运行；第二，后台任务历史记录；第三，数据库中保存的事件；第四，本阶段模拟事件；第五，单元测试中的 fixture。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        只要事件结构里有：

```Plain
type
payload.tool_name
payload.file_name
```

​        Harness 就能评估它。

#### 29.3.5.5 新增 API Schema 和路由

​        创建：

```Plain
api/app/schemas/harness.py
```

​        其中 `HarnessRunResponse` 表示一次运行结果：

```Python
class HarnessRunResponse(BaseModel):
    id: str
    case_id: str
    mode: str
    status: str
    task: str
    prompt_summary: str
    events: list[HarnessEventResponse]
    assertions: list[HarnessAssertionResponse]
    started_at: datetime
    completed_at: datetime | None
```

​        创建：

```Plain
api/app/presentation/http/routes/harness.py
```

​        核心路由如下：

```Python
@router.get("/cases", response_model=ApiResponse[HarnessCaseListResponse])
async def list_harness_cases(
    service: AgentHarnessService = Depends(build_harness_service),
) -> ApiResponse[HarnessCaseListResponse]:
    # ===================== 第1步：读取固定任务集 =====================
    cases = service.list_cases()

    # ===================== 第2步：转换成 HTTP 响应模型 =====================
    return ApiResponse(
        data=HarnessCaseListResponse(
            items=[to_case_response(case) for case in cases],
        )
    )
```

​        运行用例：

```Python
@router.post(
    "/cases/{case_id}/run",
    response_model=ApiResponse[HarnessRunResponse],
)
async def run_harness_case(
    case_id: str,
    payload: HarnessRunRequest,
    service: AgentHarnessService = Depends(build_harness_service),
) -> ApiResponse[HarnessRunResponse]:
    # 第 45 章默认使用 simulate，先保证断言和回放链路稳定可验。
    run = service.run_case(case_id=case_id, mode=payload.mode)
    return ApiResponse(data=to_run_response(run))
```

​        回放运行：

```Python
@router.get(
    "/runs/{run_id}/replay",
    response_model=ApiResponse[HarnessReplayResponse],
)
async def replay_harness_run(
    run_id: str,
    service: AgentHarnessService = Depends(build_harness_service),
) -> ApiResponse[HarnessReplayResponse]:
    # 回放接口返回运行信息和事件流，前端可以按时间线重新渲染失败过程。
    run = service.replay_run(run_id)
    return ApiResponse(
        data=HarnessReplayResponse(
            run=to_run_response(run),
            events=[to_event_response(event) for event in run.events],
        )
    )
```

​        最后打开：

```Plain
api/app/presentation/http/router.py
```

​        注册：

```Python
from app.presentation.http.routes import harness

api_router.include_router(harness.router)
```

#### 29.3.5.6 编写单元测试

​        创建：

```Plain
api/tests/test_agent_harness_service.py
```

​        核心测试如下：

```Python
class AgentHarnessServiceTest(unittest.TestCase):
    # ===================== 第1步：模拟运行应生成可通过断言的事件流 =====================
    def test_simulated_run_passes_required_assertions(self) -> None:
        service = AgentHarnessService()

        run = service.run_case("browser_observation")

        self.assertEqual(run.status, "passed")
        self.assertEqual(run.mode, "simulate")
        self.assertTrue(run.events)
        self.assertTrue(all(assertion.passed for assertion in run.assertions))

    # ===================== 第2步：缺少关键工具调用时断言应失败 =====================
    def test_evaluate_events_reports_missing_required_tool(self) -> None:
        service = AgentHarnessService()
        case = build_case()
        events = [
            {"type": "message_created", "payload": {}},
            {"type": "plan_created", "payload": {}},
            {"type": "task_done", "payload": {}},
        ]

        assertions = service.evaluate_events(case, events)
        failed = [assertion for assertion in assertions if not assertion.passed]

        self.assertEqual(
            [assertion.name for assertion in failed],
            [
                "required_tool:browser_open",
                "required_tool:browser_screenshot",
            ],
        )
```

##### 29.3.5.6.1 测试重点

​        这组测试不访问数据库、Redis、LLM、浏览器或外部网络。

​        它只验证 Harness 的核心规则：

​        换句话说，第一，模拟运行能产生通过结果；第二，缺少关键工具调用时会失败；第三，保存的运行结果可以回放。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

#### 29.3.5.7 新增前端 API 函数

​        创建：

```Plain
ui/app/lib/harness-api.ts
```

​        完整代码如下：

```TypeScript
import { requestApi } from "./api";
import type {
  HarnessCaseListData,
  HarnessReplayData,
  HarnessRunData,
} from "../types";

export function fetchHarnessCases(): Promise<HarnessCaseListData> {
  return requestApi<HarnessCaseListData>("/api/harness/cases");
}

export function runHarnessCase(caseId: string): Promise<HarnessRunData> {
  return requestApi<HarnessRunData>(`/api/harness/cases/${caseId}/run`, {
    method: "POST",
    body: JSON.stringify({ mode: "simulate" }),
  });
}

export function replayHarnessRun(runId: string): Promise<HarnessReplayData> {
  return requestApi<HarnessReplayData>(`/api/harness/runs/${runId}/replay`);
}
```

##### 29.3.5.7.1 代码讲解

​        这里不让组件直接写 `fetch()`。

​        组件只关心三个动作：

​        从实现顺序看，第一，读取任务集；第二，运行某条用例；第三，回放某次运行。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        接口路径、统一响应解析和错误处理都放在 `lib` 层。

#### 29.3.5.8 新增 HarnessPanel 组件

​        创建：

```Plain
ui/app/components/harness-panel.tsx
```

​        核心结构如下：

```TypeScript
export function HarnessPanel() {
  const [cases, setCases] = useState<LoadState<HarnessCaseListData>>({
    type: "loading",
  });
  const [latestRun, setLatestRun] = useState<HarnessRunData | null>(null);
  const [replay, setReplay] = useState<HarnessReplayData | null>(null);
  const [action, setAction] = useState<HarnessActionState>({ type: "idle" });

  async function loadCases() {
    setCases({ type: "loading" });
    try {
      const data = await fetchHarnessCases();
      setCases({ type: "ready", data });
    } catch (error) {
      const message = error instanceof Error ? error.message : "unknown error";
      setCases({ type: "error", message });
    }
  }
```

​        运行单条用例：

```TypeScript
  async function runCase(item: HarnessCaseItem) {
    setAction({ type: "running", caseId: item.id });
    setReplay(null);
    try {
      const run = await runHarnessCase(item.id);
      setLatestRun(run);
      setAction({ type: "idle" });
    } catch (error) {
      const message = error instanceof Error ? error.message : "unknown error";
      setAction({ type: "error", message });
    }
  }
```

​        回放最近运行：

```TypeScript
  async function replayLatestRun() {
    if (!latestRun) {
      return;
    }
    setAction({ type: "running", caseId: latestRun.case_id });
    try {
      const data = await replayHarnessRun(latestRun.id);
      setReplay(data);
      setAction({ type: "idle" });
    } catch (error) {
      const message = error instanceof Error ? error.message : "unknown error";
      setAction({ type: "error", message });
    }
  }
```

##### 29.3.5.8.1 组件职责

​        `HarnessPanel` 是自包含组件。

​        它自己负责：

​        放到工程语境里看，第一，加载 Harness 用例；第二，运行用例；第三，保存最近运行结果；第四，请求回放；第五，展示断言和事件。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        `page.tsx` 不需要新增状态，这样页面文件不会继续膨胀。

#### 29.3.5.9 接入设置页

​        打开：

```Plain
ui/app/components/settings-workspace.tsx
```

​        导入：

```TypeScript
import { HarnessPanel } from "./harness-panel";
```

​        在 `MemorySettingsPanel` 后面加入：

```TypeScript
<MemorySettingsPanel />
<HarnessPanel />
```

##### 29.3.5.9.1 为什么放在设置页

​        Harness 是工程验证能力，不是普通聊天交互。

​        它适合放在“设置/工程能力”区域，和模型、工具、记忆、多 Agent 配置放在一起。

​        主工作台仍然专注于：

```Plain
用户输入任务 -> Agent 执行 -> 展示过程和结果
```

### 29.3.6 关键理解

​        本阶段最重要的是理解 Harness 和普通测试的区别。

​        普通单元测试检查函数行为。

​        Harness 检查 Agent 任务链路：

```Plain
任务输入
计划生成
工具调用
事件流
产物输出
最终状态
```

​        第二个重点是理解“稳定模拟”和“真实运行”的边界。

​        `simulate` 模式不是最终目标，但它让 Harness 基础设施可以快速、稳定、无网络依赖地验证。

​        真实运行模式未来只需要把真实事件流交给：

```Plain
evaluate_events()
```

​        第三个重点是失败回放。

​        当某条任务失败时，不能只告诉用户“failed”。更有价值的是展示：

```Plain
哪些事件出现了？
哪个工具没调用？
有没有 task_error？
产物有没有生成？
```

### 29.3.7 运行验证

​        下面命令默认在项目根目录执行：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
```

#### 29.3.7.1 运行后端测试

```Bash
cd api
uv run python -m unittest tests/test_agent_harness_service.py -v
```

​        预期看到：

```Plain
OK
```

#### 29.3.7.2 编译后端代码

```Bash
uv run python -m compileall app
```

#### 29.3.7.3 检查前端类型

```Bash
cd ../ui
pnpm typecheck
```

#### 29.3.7.4 启动服务

​        回到项目根目录：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
docker compose up -d api ui nginx
```

#### 29.3.7.5 验证 Harness 接口

​        查看固定任务集：

```Bash
curl http://localhost:8088/api/harness/cases
```

​        运行浏览器观察用例：

```Bash
curl -X POST http://localhost:8088/api/harness/cases/browser_observation/run \
  -H "Content-Type: application/json" \
  -d '{"mode":"simulate"}'
```

​        预期返回中能看到：

```Plain
"status":"passed"
"required_tool:browser_open"
"required_tool:browser_screenshot"
```

​        把返回里的 `id` 作为 `run_id`，执行：

```Bash
curl http://localhost:8088/api/harness/runs/{run_id}/replay
```

​        预期能看到事件回放列表。

#### 29.3.7.6 页面验证

​        访问：

```Plain
http://localhost:8088
```

​        操作：

​        展开来看，第一，点击左侧“设置”；第二，找到 “Agent Harness” 面板；第三，点击任意用例的“模拟运行”；第四，确认断言列表显示通过或失败；第五，点击“回放”；第六，确认事件回放区域出现 message_created、plan_created、tool_called、task_done 等事件。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

### 29.3.8 阶段小结

​        本阶段完成了 Agent Harness 的最小闭环：

​        具体来说，第一，新增固定评测任务集；第二，新增 Harness 领域实体；第三，新增 Harness 应用服务；第四，新增 Harness 接口；第五，新增 Harness 单元测试；第六，前端设置页新增 Agent Harness 面板；第七，支持模拟运行、断言结果和事件回放。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        从这一阶段开始，项目不再只靠手动页面验证。后续改模型、改提示词、改工具系统时，可以用固定任务集检查核心 Agent 链路是否退化。

## 29.4 本章小结

​        完成“复杂任务状态、重试与复原”和“Agent Harness 量度与回放”两个阶段后，这条能力链已经形成闭环。读者仍然可以在每个阶段结束时单独运行验证，但理解上应把两者视作一个连续决策：先建立可靠边界，再让上层能力真正依赖它。

---

[← 第二十八章. Agent Runner 与模型工具选择](28-Agent%20Runner%20与模型工具选择.md) · [返回目录](../README.md) · [第三十章. 生产构建、测试与可观测性 →](30-生产构建、测试与可观测性.md)
