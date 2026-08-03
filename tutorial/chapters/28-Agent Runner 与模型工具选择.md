# 第二十八章. Agent Runner 与模型工具选择

## 28.1 合章说明

​        旧版教程把“Agent Runner 归一”与“模型工具选择策略精进”拆成了相邻两章。两者实际上属于同一条能力链：前者把基础结构立住，后者让它进入可用状态。本章将它们合并为前后两个阶段，保留原来的实现、验证与工程判断，同时减少能力尚未闭环时的章节跳转。

## 28.2 第一阶段：Agent Runner 归一

### 28.2.1 本阶段目标

​        学完本阶段后，你将能够：

​        展开来看，第一，理解为什么 Agent 主执行链路不能长期写在 HTTP 路由里；第二，把“用户消息 -> 计划生成 -> 步骤执行 -> 事件输出”收敛到统一 Runner；第三，让 SSE 流式接口复用同一个 Runner；第四，让同步执行接口和 Redis 后台任务也复用同一个 Runner；第五，理解 `AgentRunnerService`、`PlannerService`、`ReActAgentService` 的职责边界；第六，编写 Runner 的单元测试，保证事件输出顺序稳定。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

### 28.2.2 最终效果

​        本阶段结束后，前端发送消息的接口不变：

```Plain
POST /api/sessions/{session_id}/messages/stream
```

​        但后端内部链路会从：

```Plain
HTTP Route
  |
  +-- mark_running
  +-- create_user_message
  +-- create_plan
  +-- stream_latest_plan
  +-- get_session
```

​        收敛成：

```Plain
HTTP Route
  |
  v
AgentRunnerService.stream_user_message()
  |
  +-- SessionService
  +-- PlannerService
  +-- ReActAgentService
```

​        Redis 后台任务执行计划时，也会走：

```Plain
AgentTaskRunner
  |
  v
AgentRunnerService.execute_latest_plan()
  |
  v
ReActAgentService.execute_latest_plan()
```

​        也就是说，本阶段不是新增一个演示功能，而是整理项目的核心执行入口。

### 28.2.3 本阶段要解决的问题

​        前面章节为了逐步验证能力，把很多流程直接写在路由里。

​        例如 `/messages/stream` 做了这些事：

```Plain
标记会话 running
写入用户消息
推送 message_created
调用 Planner 生成计划
推送 plan_created
调用 ReAct 执行步骤
推送 step/tool/task 事件
读取最终会话状态
推送 stream_done
```

​        这样在早期很直观，但继续发展会有几个问题：

​        具体来说，第一，HTTP 路由承担了业务编排职责；第二，SSE 接口、同步执行接口、后台任务接口可能走出不同逻辑；第三，后续加入模型工具选择、复杂任务恢复、重试和 Harness 时，会找不到统一入口；第四，测试很难只测 Agent 主流程，不经过 HTTP 层。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        所以本阶段新增：

```Plain
AgentRunnerService
```

​        它负责统一编排一次 Agent 任务。

### 28.2.4 本阶段技术方案

​        本阶段不推翻前面的服务，而是在它们上面加一个更清晰的应用服务：

```Plain
AgentRunnerService
  |
  +-- SessionService       负责会话状态、用户消息、消息事件
  +-- PlannerService       负责上下文/长期记忆注入和计划生成
  +-- ReActAgentService    负责步骤执行和工具事件
```

​        Runner 不直接操作 SQLAlchemy 模型，也不直接拼 HTTP 响应。

​        它只产出：

```Plain
AgentRunnerStreamItem
```

​        每个 item 包含：

```Plain
name     SSE 事件名称
payload  领域对象或简单字典
```

​        路由层再把领域对象转换成 JSON。

​        这样职责边界更清楚：

```Plain
AgentRunnerService：管业务流程
HTTP Route：管请求、响应、SSE 编码
PlannerService：管计划
ReActAgentService：管步骤执行
```

​        本阶段暂时不做这些内容：

​        换句话说，第一，不改模型驱动工具选择策略；第二，不重写前端时间线样式；第三，不做复杂任务恢复和重试；第四，不做 Harness 任务评测。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        这些会在本章第二阶段之后继续完成。

### 28.2.5 新增和修改的文件

```Plain
README.md
api/README.md
api/app/application/agent_runner_service.py
api/app/application/agent_task_runner.py
api/app/presentation/http/routes/sessions.py
api/tests/test_agent_runner_service.py
docs/course/chapters/42-agent-runner-alignment.md
```

### 28.2.6 实施步骤
#### 28.2.6.1 先写 Runner 单元测试

​        创建：

```Plain
api/tests/test_agent_runner_service.py
```

​        完整代码如下：

```Python
import unittest
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.application.agent_runner_service import AgentRunnerService
from app.domain.agent_core.planner import create_agent_plan, create_plan_step
from app.domain.sessions.entities import (
    MessageRole,
    Session,
    SessionEvent,
    SessionEventType,
    SessionMessage,
    SessionStatus,
)

def build_session(status: SessionStatus = SessionStatus.idle) -> Session:
    now = datetime.now(UTC)
    return Session(
        id=uuid4(),
        title="第 42 章测试会话",
        status=status,
        unread_count=0,
        created_at=now,
        updated_at=now,
    )

def build_message(session_id: UUID, content: str) -> SessionMessage:
    return SessionMessage(
        id=uuid4(),
        session_id=session_id,
        role=MessageRole.user,
        content=content,
        created_at=datetime.now(UTC),
    )

def build_event(
    session_id: UUID,
    event_type: SessionEventType,
    payload: dict,
) -> SessionEvent:
    return SessionEvent(
        id=uuid4(),
        session_id=session_id,
        type=event_type,
        payload=payload,
        created_at=datetime.now(UTC),
    )

@dataclass(slots=True)
class FakeSessionService:
    session: Session

    async def mark_running(self, session_id: UUID) -> Session:
        self.session.status = SessionStatus.running
        return self.session

    async def create_user_message(
        self,
        session_id: UUID,
        content: str,
    ) -> tuple[SessionMessage, SessionEvent]:
        message = build_message(session_id, content)
        event = build_event(
            session_id,
            SessionEventType.message_created,
            {"message_id": str(message.id), "content": content},
        )
        return message, event

    async def get_session(self, session_id: UUID) -> Session:
        self.session.status = SessionStatus.idle
        return self.session

class FakePlannerService:
    async def create_plan(
        self,
        session_id: UUID,
        task: str,
    ):
        plan = create_agent_plan(
            title="测试计划",
            goal=task,
            source="test",
            steps=[
                create_plan_step(
                    title="执行任务",
                    description="执行测试任务",
                    expected_output="返回结果",
                )
            ],
        )
        event = build_event(
            session_id,
            SessionEventType.plan_created,
            {"id": str(plan.id), "goal": task},
        )
        return plan, event

class FakeReactService:
    async def stream_latest_plan(self, session_id: UUID):
        yield build_event(
            session_id,
            SessionEventType.step_started,
            {"title": "执行任务"},
        )
        yield build_event(
            session_id,
            SessionEventType.task_done,
            {"message": "完成"},
        )

class AgentRunnerServiceTest(unittest.IsolatedAsyncioTestCase):
    # ===================== 第1步：验证对话执行流由统一 Runner 串起来 =====================
    async def test_stream_user_message_yields_unified_runner_events(self) -> None:
        session = build_session()
        service = AgentRunnerService(
            session_service=FakeSessionService(session),
            planner_service=FakePlannerService(),
            react_service=FakeReactService(),
        )

        items = [
            item
            async for item in service.stream_user_message(
                session_id=session.id,
                content="请执行一个测试任务",
            )
        ]

        self.assertEqual(
            [item.name for item in items],
            [
                "session_status",
                "message_created",
                "plan_created",
                "step_started",
                "task_done",
                "session_status",
                "stream_done",
            ],
        )
        self.assertEqual(items[-1].payload["session_id"], str(session.id))
        self.assertIn("message", items[-1].payload)

if __name__ == "__main__":
    unittest.main()
```

##### 28.2.6.1.1 这段测试在验证什么

​        测试没有连接数据库，也没有调用真实 LLM。

​        它只验证 Runner 的编排顺序：

```Plain
session_status running
message_created
plan_created
step_started
task_done
session_status idle
stream_done
```

​        这正是前端 SSE 时间线依赖的事件顺序。

#### 28.2.6.2 创建 AgentRunnerService

​        创建：

```Plain
api/app/application/agent_runner_service.py
```

​        完整代码如下：

```Python
from dataclasses import dataclass
from uuid import UUID

from app.application.planner_service import PlannerService
from app.application.react_agent_service import ReActAgentService
from app.application.session_service import SessionService
from app.application.unit_of_work import UnitOfWork
from app.domain.sessions.entities import Session, SessionEvent, SessionMessage

@dataclass(slots=True)
class AgentRunnerStreamItem:
    """Agent Runner 推给 HTTP/SSE 层的一条可观察输出。

    `name` 对应 SSE event 名称；`payload` 保留领域对象或简单字典。
    路由层负责把领域对象转换成 Pydantic 响应模型，避免应用服务依赖 HTTP 细节。
    """

    name: str
    payload: Session | SessionEvent | dict

class AgentRunnerService:
    """统一编排一次会话任务的主执行链路。

    第 42 章把前面分散在路由里的步骤收敛到这里：
    1. 标记会话运行中。
    2. 写入用户消息和 message_created 事件。
    3. 使用 Planner 生成 plan_created。
    4. 使用 ReAct 按步骤执行并持续产出事件。
    5. 读取最终会话状态并发出 stream_done。
    """

    def __init__(
        self,
        *,
        session_service: SessionService,
        planner_service: PlannerService,
        react_service: ReActAgentService,
    ) -> None:
        # ===================== 第1步：保存 Runner 需要协调的三个应用服务 =====================
        self.session_service = session_service
        self.planner_service = planner_service
        self.react_service = react_service

    @classmethod
    def from_uow(
        cls,
        uow: UnitOfWork,
        *,
        planner_service: PlannerService | None = None,
    ) -> "AgentRunnerService":
        """用同一个 UnitOfWork 构建 Runner，保证执行链路使用同一事务入口。"""

        return cls(
            session_service=SessionService(uow),
            planner_service=planner_service or PlannerService(uow),
            react_service=ReActAgentService(uow),
        )

    # ===================== 第2步：运行一次用户消息驱动的 Agent 任务 =====================
    async def stream_user_message(
        self,
        *,
        session_id: UUID,
        content: str,
    ):
        """把用户消息转换成可流式观察的 Agent 执行过程。"""

        # 1. 会话先进入 running，前端可以立即展示任务开始。
        running_session = await self.session_service.mark_running(session_id)
        yield AgentRunnerStreamItem(
            name="session_status",
            payload=running_session,
        )

        # 2. 写入用户消息，并把 message_created 推给前端时间线。
        message, message_event = await self.session_service.create_user_message(
            session_id=session_id,
            content=content,
        )
        yield AgentRunnerStreamItem(
            name=message_event.type.value,
            payload=message_event,
        )

        # 3. 生成计划。Planner 内部会读取上下文快照和长期记忆。
        _plan, plan_event = await self.planner_service.create_plan(
            session_id=session_id,
            task=content,
        )
        yield AgentRunnerStreamItem(
            name=plan_event.type.value,
            payload=plan_event,
        )

        # 4. 执行计划。ReAct 内部会持续写 step/tool/task 事件。
        async for event in self.react_service.stream_latest_plan(session_id):
            yield AgentRunnerStreamItem(
                name=event.type.value,
                payload=event,
            )

        # 5. 推送最终会话状态和 stream_done，前端据此收尾 loading 状态。
        final_session = await self.session_service.get_session(session_id)
        yield AgentRunnerStreamItem(
            name="session_status",
            payload=final_session,
        )
        yield AgentRunnerStreamItem(
            name="stream_done",
            payload={
                "session_id": str(session_id),
                "message_id": str(message.id),
                "message": {
                    "id": str(message.id),
                    "session_id": str(message.session_id),
                    "role": message.role.value,
                    "content": message.content,
                    "created_at": message.created_at.isoformat(),
                },
            },
        )

    # ===================== 第3步：运行已有计划，供同步接口和后台任务复用 =====================
    async def execute_latest_plan(self, session_id: UUID) -> list[SessionEvent]:
        """执行会话最近一次计划，保持旧接口兼容。"""

        return await self.react_service.execute_latest_plan(session_id)
```

##### 28.2.6.2.1 代码讲解

​        `AgentRunnerStreamItem` 是 Runner 和 HTTP 层之间的桥。

​        它没有直接使用 Pydantic 响应模型，因为应用服务不应该知道 HTTP 响应怎么编码。

​        `stream_user_message()` 是本阶段的核心方法。

​        它按 5 步完成一次对话执行：

1. 会话进入运行中。
2. 写入用户消息。
3. 生成计划。
4. 执行计划。
5. 推送最终状态。

​        `execute_latest_plan()` 先保留旧能力，内部仍然调用 `ReActAgentService`。这样原来的 `/plan/execute` 和后台任务不会被破坏。

#### 28.2.6.3 让 SSE 路由复用 Runner

​        打开：

```Plain
api/app/presentation/http/routes/sessions.py
```

​        新增导入：

```Python
from app.application.agent_runner_service import AgentRunnerService, AgentRunnerStreamItem
```

​        新增依赖构造函数：

```Python
def build_agent_runner_service(
    db_session: AsyncSession = Depends(get_db_session),
) -> AgentRunnerService:
    uow = UnitOfWork(db_session)
    return AgentRunnerService.from_uow(
        uow,
        planner_service=PlannerService(uow, LLMService()),
    )
```

​        新增 SSE payload 转换函数：

```Python
def to_runner_stream_payload(item: AgentRunnerStreamItem) -> dict:
    """把 Runner 产出的领域对象转换成 SSE 可以发送的 JSON 数据。"""

    if isinstance(item.payload, Session):
        return to_session_response(item.payload).model_dump(mode="json")
    if isinstance(item.payload, SessionEvent):
        return to_event_response(item.payload).model_dump(mode="json")
    return item.payload
```

​        把 `/messages/stream` 改成：

```Python
@router.post("/{session_id}/messages/stream")
async def stream_message(
    session_id: UUID,
    payload: MessageCreateRequest,
    runner: AgentRunnerService = Depends(build_agent_runner_service),
) -> StreamingResponse:
    async def event_stream():
        # ===================== 第1步：Runner 统一产出 SSE 需要的状态和事件 =====================
        async for item in runner.stream_user_message(
            session_id=session_id,
            content=payload.content,
        ):
            yield encode_sse(item.name, to_runner_stream_payload(item))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

##### 28.2.6.3.1 为什么路由变短了

​        路由现在只做两件事：

```Plain
接收 HTTP 请求
把 Runner 输出编码成 SSE
```

​        它不再关心：

```Plain
什么时候生成计划
什么时候执行计划
什么时候读取最终会话状态
```

​        这些都属于 Agent 主流程，应该放在 Runner。

#### 28.2.6.4 让同步执行接口复用 Runner

​        继续打开 `sessions.py`，把 `/plan/execute` 改成：

```Python
@router.post(
    "/{session_id}/plan/execute",
    response_model=ApiResponse[PlanExecuteResponse],
)
async def execute_plan(
    session_id: UUID,
    service: AgentRunnerService = Depends(build_agent_runner_service),
) -> ApiResponse[PlanExecuteResponse]:
    events = await service.execute_latest_plan(session_id)
    return ApiResponse(
        data=PlanExecuteResponse(
            events=[to_event_response(event) for event in events],
        )
    )
```

##### 28.2.6.4.1 为什么同步接口还保留

​        前端主流程已经使用 `/messages/stream`。

​        但是同步执行接口仍然适合：

​        从实现顺序看，第一，curl 验证；第二，教程排查；第三，单步调试；第四，后续 Harness 复用。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        所以本阶段不删除它，而是让它和 SSE 一样复用 Runner。

#### 28.2.6.5 让后台任务复用 Runner

​        打开：

```Plain
api/app/application/agent_task_runner.py
```

​        把导入改成：

```Python
from app.application.agent_runner_service import AgentRunnerService
```

​        把 `_execute_plan()` 改成：

```Python
async def _execute_plan(self, session_id: UUID):
    """为后台任务创建独立数据库会话，再复用统一 Agent Runner。"""

    async with self.session_factory() as db_session:
        service = AgentRunnerService.from_uow(UnitOfWork(db_session))
        return await service.execute_latest_plan(session_id)
```

##### 28.2.6.5.1 这段代码的业务流程

​        后台任务仍然由 Redis Stream 触发。

​        区别是：

```Plain
旧：AgentTaskRunner -> ReActAgentService
新：AgentTaskRunner -> AgentRunnerService -> ReActAgentService
```

​        这样以后如果 Runner 加入任务恢复、停止点、统一错误处理，后台任务也能自动复用。

### 28.2.7 关键理解

​        本阶段最重要的是理解“Runner 是应用层主流程，不是工具本身”。

​        `PlannerService` 负责生成计划。

​        `ReActAgentService` 负责执行步骤和调用工具。

​        `AgentRunnerService` 负责把它们串成一次完整任务。

​        可以这样理解：

```Plain
Planner = 做计划的人
ReAct = 按计划动手的人
Runner = 负责调度整个任务的人
```

​        第二个重点是：

```Plain
HTTP 路由不应该承载业务编排。
```

​        路由越薄，后续越容易支持：

​        放到工程语境里看，第一，SSE；第二，后台任务；第三，Harness 评测；第四，CLI 调用；第五，任务恢复。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

### 28.2.8 技术难点与亮点

​        技术难点：

​        展开来看，第一，不能破坏现有前端 SSE 事件名称；第二，不能让应用服务依赖 HTTP 响应模型；第三，同步执行、流式执行和后台任务要逐步收敛，不能一次性重写所有能力；第四，Runner 要复用第 27 章的上下文和长期记忆注入，而不是另开一套逻辑。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        项目亮点：

​        具体来说，第一，Agent 主执行链路有了明确入口；第二，SSE 路由明显变薄；第三，Redis 后台任务和同步执行接口开始复用同一套 Runner；第四，Runner 有单元测试保护事件顺序；第五，为本章第二阶段模型驱动工具选择、第 29 章任务恢复、第 29 章 Harness 打基础。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

### 28.2.9 面试考点

​        换句话说，第一，为什么不能把 Agent 编排长期写在 HTTP 路由里？；第二，Runner、Planner、ReAct 分别负责什么？；第三，为什么应用服务不应该直接返回 FastAPI Response？；第四，SSE 接口为什么适合消费 Runner 的流式输出？；第五，后台任务和同步接口为什么要复用同一个 Runner？。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

### 28.2.10 运行验证

​        下面命令默认在项目根目录执行：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
```

#### 28.2.10.1 运行后端单元测试

```Bash
cd api
uv run python -m unittest discover -s tests -v
```

​        预期能看到：

```Plain
test_stream_user_message_yields_unified_runner_events ... ok
```

#### 28.2.10.2 编译后端代码

```Bash
uv run python -m compileall app
```

​        预期没有 Python 语法错误。

#### 28.2.10.3 检查前端

​        本阶段没有修改前端代码，但仍建议确认现有 UI 没有类型问题：

```Bash
cd ../ui
pnpm typecheck
pnpm build
```

#### 28.2.10.4 启动服务

​        回到项目根目录：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
docker compose build api
docker compose up -d nginx
docker compose exec api uv run alembic upgrade head
```

​        本阶段没有新增数据库迁移，执行 `alembic upgrade head` 是为了确认数据库处于最新状态。

#### 28.2.10.5 页面验证

​        访问：

```Plain
http://localhost:8088
```

​        操作：

​        从实现顺序看，第一，创建或选择一个会话；第二，在输入框发送一个任务；第三，确认页面仍然自动出现用户消息、计划步骤、工具调用和完成状态；第四，点击“上下文”，确认长期记忆和短期上下文仍然可以查看。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        这说明前端接口没有变化，但后端编排已经切换到 Runner。

#### 28.2.10.6 curl 验证 SSE

​        创建会话：

```Bash
curl -X POST http://localhost:8088/api/sessions \
  -H "Content-Type: application/json" \
  -d '{"title":"第 42 章 Runner 测试"}'
```

​        发送流式任务：

```Bash
curl -N -X POST http://localhost:8088/api/sessions/{session_id}/messages/stream \
  -H "Content-Type: application/json" \
  -d '{"content":"请帮我规划并执行一个简单的后端接口检查任务"}'
```

​        预期能看到这些事件：

```Plain
event: session_status
event: message_created
event: plan_created
event: step_started
event: tool_called
event: step_completed
event: task_done
event: session_status
event: stream_done
```

### 28.2.11 阶段小结

​        本阶段完成了 Agent 主执行链路的第一轮最终对齐：

​        放到工程语境里看，第一，新增 `AgentRunnerService`；第二，新增 `AgentRunnerStreamItem`；第三，`/messages/stream` 改成调用 Runner；第四，`/plan/execute` 改成调用 Runner；第五，`AgentTaskRunner` 后台计划任务改成调用 Runner；第六，新增 Runner 单元测试，验证流式事件顺序。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        从这一阶段开始，后续模型工具选择、任务恢复、Harness 评测和生产化状态管理都有了更清楚的主入口。

## 28.3 第二阶段：模型工具选择策略精进

### 28.3.1 本阶段目标

​        学完本阶段后，你将能够：

​        展开来看，第一，理解为什么关键词规则不能长期承担 Agent 工具选择；第二，把工具 schema 注入模型上下文；第三，让模型输出结构化 tool call；第四，在模型不可用、输出不是 JSON、工具名不存在时回退到确定性规则；第五，在工具参数缺失时做最小参数修复；第六，让 ReAct 执行步骤时使用统一的 `ModelToolSelectionService`；第七，理解为什么工具选择过程只展示可观察摘要，不暴露隐藏推理。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

### 28.3.2 最终效果

​        本阶段结束后，用户仍然通过同一个前端输入框发任务：

```Plain
http://localhost:8088
```

​        后端内部工具选择会从：

```Plain
ReActAgentService
  |
  +-- 大量关键词 if/elif
  |
  v
AgentTool
```

​        升级为：

```Plain
ReActAgentService
  |
  v
ModelToolSelectionService
  |
  +-- LLM 结构化 tool call
  +-- fallback 规则选择
  +-- 参数修复
  |
  v
AgentTool
```

​        如果 LLM API Key 已配置，模型会看到：

```Plain
当前任务
当前步骤
短期上下文
长期记忆
工具 schema
```

​        然后输出：

```JSON
{
  "tool_name": "search_web",
  "arguments": {
    "query": "AI Agent latest news",
    "count": 5
  },
  "observable_summary": "搜索公开网页资料"
}
```

​        如果模型不可用，系统会自动回退到稳定规则，页面仍然能看到工具调用事件。

### 28.3.3 本阶段要解决的问题

​        第 13 章到本章第一阶段，ReAct 执行步骤时主要靠关键词选择工具。

​        例如：

```Plain
包含“搜索” -> search_web
包含“浏览器” -> browser_open
包含“A2A” -> a2a_call
包含“MCP” -> mcp_call
包含“多 Agent” -> multi_agent_collaborate
```

​        这个方式适合课程早期，因为它稳定、可预测、不依赖外部模型。

​        但它不是成熟 Agent 的最终形态。

​        真实任务里，用户可能这样说：

```Plain
帮我看看最近 Python 生态有什么重要变化
请打开官网确认安装说明
让研究 Agent 帮我补充资料
把结果整理成一个文件
```

​        这些任务不一定包含固定关键词。工具选择应该结合：

​        具体来说，第一，用户任务目标；第二，Planner 生成的当前步骤；第三，第 15 章短期上下文；第四，第 27 章长期记忆；第五，工具 schema；第六，子 Agent 能力说明；第七，沙箱状态。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        本阶段先完成第一步：

```Plain
模型基于工具 schema 输出结构化 tool call
```

​        并保留 fallback，保证本地网络或 API Key 不可用时仍能验证。

### 28.3.4 本阶段技术方案

​        新增：

```Plain
api/app/application/tool_selection_service.py
```

​        核心类：

```Plain
ModelToolSelectionService
```

​        职责如下：

```Plain
输入：
  - plan
  - step
  - index
  - agent_context
  - ToolRegistry

处理：
  - 渲染工具 schema
  - 调用 LLM 输出 JSON tool call
  - 解析工具名和参数
  - 校验工具是否存在
  - 修复常见缺失参数
  - fallback 到确定性规则

输出：
  - ToolCallResult
```

​        ReAct 只保留执行职责：

```Plain
ReActAgentService
  |
  v
ModelToolSelectionService.call_tool_for_step()
  |
  v
ToolCallResult
  |
  v
写入 tool_called 事件
```

​        本阶段暂时不做这些内容：

​        换句话说，第一，不把 MCP 动态工具展开成大量细粒度工具；第二，不做复杂重试链路；第三，不做工具调用失败后的模型自我修复多轮循环；第四，不展示隐藏推理；第五，不重构前端样式。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        这些会在后续章节继续增强。

### 28.3.5 新增和修改的文件

```Plain
README.md
api/README.md
api/app/application/tool_selection_service.py
api/app/application/react_agent_service.py
api/tests/test_tool_selection_service.py
docs/course/chapters/43-model-tool-selection.md
```

### 28.3.6 实施步骤
#### 28.3.6.1 编写工具选择服务测试

​        创建：

```Plain
api/tests/test_tool_selection_service.py
```

​        完整代码如下：

```Python
import unittest

from app.application.tool_selection_service import ModelToolSelectionService
from app.domain.agent_core.tools import AgentTool, ToolDefinition, ToolParameter, ToolRegistry
from app.domain.llm.entities import LLMChatResult

class FakeLLMService:
    """为工具选择测试返回固定模型输出，不访问真实模型服务。"""

    def __init__(self, content: str | Exception) -> None:
        self.content = content
        self.messages = []

    async def chat(self, messages, **kwargs):
        self.messages = messages
        if isinstance(self.content, Exception):
            raise self.content
        return LLMChatResult(
            provider="fake",
            model="fake-tool-selector",
            content=self.content,
            usage=None,
        )

def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="search_web",
                description="搜索互联网公开网页。",
                parameters=[
                    ToolParameter(
                        name="query",
                        type="string",
                        description="搜索关键词。",
                    ),
                    ToolParameter(
                        name="count",
                        type="integer",
                        description="结果数量。",
                        required=False,
                    ),
                ],
            ),
            handler=lambda query, count=5: f"搜索：{query}，数量：{count}",
        )
    )
    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="summarize_text",
                description="总结文本。",
                parameters=[
                    ToolParameter(
                        name="text",
                        type="string",
                        description="要总结的文本。",
                    )
                ],
            ),
            handler=lambda text: f"摘要：{text}",
        )
    )
    return registry

class ModelToolSelectionServiceTest(unittest.IsolatedAsyncioTestCase):
    # ===================== 第1步：模型返回合法 tool call 时优先使用模型选择 =====================
    async def test_selects_tool_from_model_json(self) -> None:
        service = ModelToolSelectionService(
            registry=build_registry(),
            llm_service=FakeLLMService(
                '{"tool_name":"search_web","arguments":{"query":"AI Agent news","count":3}}'
            ),
        )

        result = await service.call_tool_for_step(
            plan={"goal": "搜索 AI Agent 新闻"},
            step={"title": "搜索资料", "description": "搜索 AI Agent news"},
            index=1,
            agent_context="长期记忆：用户偏好中文解释",
        )

        self.assertEqual(result.tool_name, "search_web")
        self.assertEqual(result.arguments["query"], "AI Agent news")
        self.assertEqual(result.arguments["count"], 3)

    # ===================== 第2步：模型输出不可解析时回退到确定性规则 =====================
    async def test_falls_back_to_rule_when_model_output_is_invalid(self) -> None:
        service = ModelToolSelectionService(
            registry=build_registry(),
            llm_service=FakeLLMService("这不是 JSON"),
        )

        result = await service.call_tool_for_step(
            plan={"goal": "请搜索 FastAPI 资料"},
            step={"title": "搜索资料", "description": "查找 FastAPI 最新资料"},
            index=1,
            agent_context="",
        )

        self.assertEqual(result.tool_name, "search_web")
        self.assertIn("FastAPI", result.arguments["query"])

    # ===================== 第3步：模型缺少必填参数时尝试从当前步骤修复 =====================
    async def test_repairs_missing_required_argument_before_calling_tool(self) -> None:
        service = ModelToolSelectionService(
            registry=build_registry(),
            llm_service=FakeLLMService('{"tool_name":"search_web","arguments":{}}'),
        )

        result = await service.call_tool_for_step(
            plan={"goal": "搜索 PostgreSQL 索引优化"},
            step={"title": "搜索资料", "description": "检索 PostgreSQL 索引优化"},
            index=1,
            agent_context="",
        )

        self.assertEqual(result.tool_name, "search_web")
        self.assertIn("PostgreSQL", result.arguments["query"])

if __name__ == "__main__":
    unittest.main()
```

##### 28.3.6.1.1 测试覆盖了什么

​        这三个测试分别覆盖：

​        从实现顺序看，第一，模型输出合法 JSON 时，优先使用模型选择；第二，模型输出坏 JSON 时，fallback 仍能选工具；第三，模型遗漏必填参数时，服务会尝试从任务文本修复。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        这里使用假工具注册表，避免单元测试访问真实搜索、浏览器或沙箱。

#### 28.3.6.2 实现 ModelToolSelectionService

​        创建：

```Plain
api/app/application/tool_selection_service.py
```

​        核心代码如下：

```Python
class ModelToolSelectionService:
    """结合模型输出和确定性 fallback 选择工具。

    第 43 章开始把工具选择从 ReActAgentService 中抽出来：
    1. 优先让模型基于工具 schema、任务、上下文输出结构化 tool call。
    2. 模型不可用或输出不合法时，回退到规则选择，保证课程本地可验证。
    3. 调用前修复缺失的常见参数，避免简单参数缺失导致整步失败。
    """

    def __init__(
        self,
        *,
        registry: ToolRegistry,
        llm_service: LLMService | None = None,
    ) -> None:
        # ===================== 第1步：保存工具注册表和模型服务 =====================
        self.registry = registry
        self.llm_service = llm_service or LLMService()

    # ===================== 第2步：为计划步骤选择并调用工具 =====================
    async def call_tool_for_step(
        self,
        *,
        plan: dict,
        step: dict,
        index: int,
        agent_context: str,
    ) -> ToolCallResult:
        """选择一个工具、修复参数、执行工具并返回统一结果。"""

        # 1. 收集当前任务文本。工具选择必须优先看当前任务，避免长期记忆误触发工具。
        goal = str(plan.get("goal", ""))
        title = str(step.get("title", ""))
        description = str(step.get("description", ""))
        expected_output = str(step.get("expected_output", ""))
        step_text = f"{title} {description} {expected_output}".strip()
        task_text = f"{goal} {step_text}".strip()

        # 2. 先尝试模型工具选择；失败后使用确定性规则兜底。
        decision = await self._select_with_model(
            task_text=task_text,
            agent_context=agent_context,
        )
        if decision is None:
            decision = self._select_with_rules(
                task_text=task_text,
                step_text=step_text,
                index=index,
                agent_context=agent_context,
            )

        # 3. 校验工具存在，并在调用前修复缺失的常见参数。
        tool = self.registry.get(decision.tool_name)
        arguments = self._repair_arguments(
            tool=tool,
            arguments=decision.arguments,
            task_text=task_text,
            agent_context=agent_context,
        )

        # 4. AgentTool 会继续执行必填参数校验，并返回标准 ToolCallResult。
        return tool.call(arguments)
```

##### 28.3.6.2.1 代码讲解

​        `call_tool_for_step()` 是对外入口。

​        它不直接相信模型输出。

​        流程是：

```Plain
收集任务文本
  |
  v
尝试模型选择
  |
  +-- 成功：校验工具名和参数
  |
  +-- 失败：fallback 规则选择
  |
  v
修复缺失参数
  |
  v
AgentTool.call()
```

##### 28.3.6.2.2 模型提示词如何写

​        `_select_with_model()` 会把工具 schema 渲染给模型：

```Python
"你是 Agent 的工具选择器。请只返回 JSON，不要返回 Markdown。"
"JSON 格式："
'{"tool_name":"工具名","arguments":{},"observable_summary":"给用户看的简短说明"}'
"\n\n可用工具：\n"
f"{self._render_tool_schemas()}\n\n"
"压缩上下文：\n"
f"{agent_context or '暂无额外上下文'}\n\n"
"注意：不要输出隐藏推理，只输出可观察的工具选择结果。"
```

​        这段提示词有两个关键点：

​        放到工程语境里看，第一，要求只返回 JSON，方便程序解析；第二，要求不要输出隐藏推理，只输出可观察工具选择结果。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

##### 28.3.6.2.3 为什么还要 fallback

​        模型工具选择可能失败：

​        展开来看，第一，API Key 没配置；第二，网络超时；第三，模型返回 Markdown；第四，模型输出不存在的工具名；第五，模型参数缺失。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        如果没有 fallback，本地课程会因为外部模型状态不稳定而无法验证。

​        所以本阶段保留确定性规则：

```Plain
搜索/检索 -> search_web
浏览器/访问 -> browser_open
截图 -> browser_screenshot
MCP -> mcp_call
A2A -> a2a_call
多 Agent/协作 -> multi_agent_collaborate
默认 -> summarize_text
```

#### 28.3.6.3 接入 ReActAgentService

​        打开：

```Plain
api/app/application/react_agent_service.py
```

​        新增导入：

```Python
from app.application.tool_selection_service import ModelToolSelectionService
```

​        在构造函数中创建工具选择服务：

```Python
def __init__(self, uow: UnitOfWork) -> None:
    # ===================== 第1步：保存数据库事务和工具注册表 =====================
    self.uow = uow
    self.registry = build_builtin_tool_registry()
    self.tool_selector = ModelToolSelectionService(registry=self.registry)
```

​        在 `_execute_step()` 中改成异步调用：

```Python
tool_result = await self._call_tool_for_step(
    plan=plan,
    step=step,
    index=index,
    memory_context=memory_context,
)
```

​        把 `_call_tool_for_step()` 改成：

```Python
async def _call_tool_for_step(
    self,
    plan: dict,
    step: dict,
    index: int,
    memory_context: MemoryContext,
) -> dict:
    """通过模型工具选择服务调用一个内置工具。

    第 43 章开始，ReAct 不再自己维护大段关键词分支。
    它把计划、步骤和长期记忆交给 ModelToolSelectionService：
    - 模型可用时，模型根据工具 schema 输出结构化 tool call。
    - 模型不可用或输出异常时，服务内部使用确定性 fallback。
    """

    result = await self.tool_selector.call_tool_for_step(
        plan=plan,
        step=step,
        index=index,
        agent_context=self._render_memory_guidance(memory_context),
    )
    return {
        "tool_name": result.tool_name,
        "arguments": result.arguments,
        "output": result.output,
    }
```

##### 28.3.6.3.1 这段代码的业务变化

​        ReAct 不再自己维护工具选择策略。

​        它只负责：

```Plain
拿到计划步骤
  |
  v
调用工具选择服务
  |
  v
把工具结果写入 tool_called
```

​        工具选择服务负责：

```Plain
模型选择
fallback
参数修复
工具调用
```

​        这样第 29 章之后再做重试、恢复、评测时，工具选择会更容易单独测试和替换。

### 28.3.7 关键理解

​        本阶段最重要的是理解：

```Plain
工具选择不是工具执行。
```

​        工具选择回答：

```Plain
下一步应该调用哪个工具？参数是什么？
```

​        工具执行回答：

```Plain
这个工具具体怎么运行？输出是什么？
```

​        把它们分开后，系统会更清楚：

```Plain
ModelToolSelectionService -> 决定调用谁
AgentTool.call() -> 执行工具
ReActAgentService -> 写事件和推进步骤
```

​        第二个重点是：

```Plain
不要展示隐藏推理。
```

​        前端可以展示：

​        具体来说，第一，工具名；第二，调用参数；第三，工具输出；第四，可观察摘要。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        但不应该展示模型内部推理过程。

### 28.3.8 技术难点与亮点

​        技术难点：

​        换句话说，第一，模型输出不稳定，必须解析和兜底；第二，工具参数可能缺失，不能直接让任务失败；第三，长期记忆可能包含旧工具关键词，不能无脑让记忆触发工具；第四，ReAct 要变薄，但不能破坏已有工具调用事件。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        项目亮点：

​        从实现顺序看，第一，工具选择从 ReAct 中抽离成独立服务；第二，工具 schema 真正进入模型上下文；第三，模型输出结构化 tool call；第四，fallback 保证本地验证稳定；第五，参数修复减少简单模型错误导致的任务失败。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

### 28.3.9 面试考点

​        放到工程语境里看，第一，为什么工具选择应该和工具执行分开？；第二，为什么模型工具选择需要结构化 JSON？；第三，为什么模型输出必须校验工具名和参数？；第四，为什么模型不可用时仍然需要 fallback？；第五，为什么不能把隐藏推理展示给用户？。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

### 28.3.10 运行验证

​        下面命令默认在项目根目录执行：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
```

#### 28.3.10.1 运行后端单元测试

```Bash
cd api
uv run python -m unittest discover -s tests -v
```

​        预期能看到：

```Plain
test_selects_tool_from_model_json ... ok
test_falls_back_to_rule_when_model_output_is_invalid ... ok
test_repairs_missing_required_argument_before_calling_tool ... ok
```

#### 28.3.10.2 编译后端代码

```Bash
uv run python -m compileall app
```

​        预期没有 Python 语法错误。

#### 28.3.10.3 检查前端

​        本阶段没有修改前端代码，但仍建议执行：

```Bash
cd ../ui
pnpm typecheck
pnpm build
```

#### 28.3.10.4 启动服务

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
docker compose build api
docker compose up -d nginx
docker compose exec api uv run alembic upgrade head
```

​        本阶段没有新增数据库迁移。

#### 28.3.10.5 页面验证

​        访问：

```Plain
http://localhost:8088
```

​        发送任务：

```Plain
请搜索 FastAPI 最新资料，并总结关键点
```

​        预期：

​        展开来看，第一，页面出现用户消息；第二，系统生成计划；第三，执行过程中出现 `tool_called`；第四，工具名优先可能是 `search_web`；第五，如果 LLM 不可用，fallback 仍然会根据“搜索”关键词选择 `search_web`。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        再发送：

```Plain
请总结这段任务目标，并给出下一步建议
```

​        预期：

​        具体来说，第一，工具调用可能是 `summarize_text` 或模型选择的更合适工具；第二，页面不应该显示隐藏推理，只显示工具调用参数和输出。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

### 28.3.11 阶段小结

​        本阶段完成了工具选择策略的关键升级：

​        换句话说，第一，新增 `ModelToolSelectionService`；第二，工具 schema 注入模型提示词；第三，模型输出结构化 tool call；第四，模型不可用或输出异常时 fallback；第五，工具参数缺失时做最小修复；第六，ReAct 执行步骤时改用统一工具选择服务；第七，增加工具选择单元测试。这些点放在一起看，构成了本阶段叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        从这一阶段开始，工具调用不再只是关键词规则，而是具备了模型驱动选择的基础结构。

## 28.4 本章小结

​        完成“Agent Runner 归一”和“模型工具选择策略精进”两个阶段后，这条能力链已经形成闭环。读者仍然可以在每个阶段结束时单独运行验证，但理解上应把两者视作一个连续决策：先建立可靠边界，再让上层能力真正依赖它。

---

[← 第二十七章. 长期记忆与上下文注入](27-长期记忆与上下文注入.md) · [返回目录](../README.md) · [第二十九章. 复杂任务复原与 Agent Harness →](29-复杂任务复原与%20Agent%20Harness.md)
