# 第四十二章. Agent Runner 归一

## 42.1 本章目标

​        学完本章后，你将能够：

​        展开来看，第一，理解为什么 Agent 主执行链路不能长期写在 HTTP 路由里；第二，把“用户消息 -> 计划生成 -> 步骤执行 -> 事件输出”收敛到统一 Runner；第三，让 SSE 流式接口复用同一个 Runner；第四，让同步执行接口和 Redis 后台任务也复用同一个 Runner；第五，理解 `AgentRunnerService`、`PlannerService`、`ReActAgentService` 的职责边界；第六，编写 Runner 的单元测试，保证事件输出顺序稳定。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

## 42.2 最终效果

​        本章结束后，前端发送消息的接口不变：

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

​        也就是说，本章不是新增一个演示功能，而是整理项目的核心执行入口。

## 42.3 本章要解决的问题

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

​        具体来说，第一，HTTP 路由承担了业务编排职责；第二，SSE 接口、同步执行接口、后台任务接口可能走出不同逻辑；第三，后续加入模型工具选择、复杂任务恢复、重试和 Harness 时，会找不到统一入口；第四，测试很难只测 Agent 主流程，不经过 HTTP 层。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        所以本章新增：

```Plain
AgentRunnerService
```

​        它负责统一编排一次 Agent 任务。

## 42.4 本章技术方案

​        本章不推翻前面的服务，而是在它们上面加一个更清晰的应用服务：

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

​        本章暂时不做这些内容：

​        换句话说，第一，不改模型驱动工具选择策略；第二，不重写前端时间线样式；第三，不做复杂任务恢复和重试；第四，不做 Harness 任务评测。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        这些会在第 43 章之后继续完成。

## 42.5 新增和修改的文件

```Plain
README.md
api/README.md
api/app/application/agent_runner_service.py
api/app/application/agent_task_runner.py
api/app/presentation/http/routes/sessions.py
api/tests/test_agent_runner_service.py
docs/course/chapters/42-agent-runner-alignment.md
```

## 42.6 实施步骤
### 42.6.1 先写 Runner 单元测试

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

#### 42.6.1.1 这段测试在验证什么

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

### 42.6.2 创建 AgentRunnerService

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

#### 42.6.2.1 代码讲解

​        `AgentRunnerStreamItem` 是 Runner 和 HTTP 层之间的桥。

​        它没有直接使用 Pydantic 响应模型，因为应用服务不应该知道 HTTP 响应怎么编码。

​        `stream_user_message()` 是本章的核心方法。

​        它按 5 步完成一次对话执行：

1. 会话进入运行中。
2. 写入用户消息。
3. 生成计划。
4. 执行计划。
5. 推送最终状态。

​        `execute_latest_plan()` 先保留旧能力，内部仍然调用 `ReActAgentService`。这样原来的 `/plan/execute` 和后台任务不会被破坏。

### 42.6.3 让 SSE 路由复用 Runner

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

#### 42.6.3.1 为什么路由变短了

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

### 42.6.4 让同步执行接口复用 Runner

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

#### 42.6.4.1 为什么同步接口还保留

​        前端主流程已经使用 `/messages/stream`。

​        但是同步执行接口仍然适合：

​        从实现顺序看，第一，curl 验证；第二，教程排查；第三，单步调试；第四，后续 Harness 复用。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        所以本章不删除它，而是让它和 SSE 一样复用 Runner。

### 42.6.5 让后台任务复用 Runner

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

#### 42.6.5.1 这段代码的业务流程

​        后台任务仍然由 Redis Stream 触发。

​        区别是：

```Plain
旧：AgentTaskRunner -> ReActAgentService
新：AgentTaskRunner -> AgentRunnerService -> ReActAgentService
```

​        这样以后如果 Runner 加入任务恢复、停止点、统一错误处理，后台任务也能自动复用。

## 42.7 关键理解

​        本章最重要的是理解“Runner 是应用层主流程，不是工具本身”。

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

​        放到工程语境里看，第一，SSE；第二，后台任务；第三，Harness 评测；第四，CLI 调用；第五，任务恢复。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

## 42.8 技术难点与亮点

​        技术难点：

​        展开来看，第一，不能破坏现有前端 SSE 事件名称；第二，不能让应用服务依赖 HTTP 响应模型；第三，同步执行、流式执行和后台任务要逐步收敛，不能一次性重写所有能力；第四，Runner 要复用第 41 章的上下文和长期记忆注入，而不是另开一套逻辑。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        项目亮点：

​        具体来说，第一，Agent 主执行链路有了明确入口；第二，SSE 路由明显变薄；第三，Redis 后台任务和同步执行接口开始复用同一套 Runner；第四，Runner 有单元测试保护事件顺序；第五，为第 43 章模型驱动工具选择、第 44 章任务恢复、第 45 章 Harness 打基础。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

## 42.9 面试考点

​        换句话说，第一，为什么不能把 Agent 编排长期写在 HTTP 路由里？；第二，Runner、Planner、ReAct 分别负责什么？；第三，为什么应用服务不应该直接返回 FastAPI Response？；第四，SSE 接口为什么适合消费 Runner 的流式输出？；第五，后台任务和同步接口为什么要复用同一个 Runner？。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

## 42.10 运行验证

​        下面命令默认在项目根目录执行：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
```

### 42.10.1 运行后端单元测试

```Bash
cd api
uv run python -m unittest discover -s tests -v
```

​        预期能看到：

```Plain
test_stream_user_message_yields_unified_runner_events ... ok
```

### 42.10.2 编译后端代码

```Bash
uv run python -m compileall app
```

​        预期没有 Python 语法错误。

### 42.10.3 检查前端

​        本章没有修改前端代码，但仍建议确认现有 UI 没有类型问题：

```Bash
cd ../ui
pnpm typecheck
pnpm build
```

### 42.10.4 启动服务

​        回到项目根目录：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
docker compose build api
docker compose up -d nginx
docker compose exec api uv run alembic upgrade head
```

​        本章没有新增数据库迁移，执行 `alembic upgrade head` 是为了确认数据库处于最新状态。

### 42.10.5 页面验证

​        访问：

```Plain
http://localhost:8088
```

​        操作：

​        从实现顺序看，第一，创建或选择一个会话；第二，在输入框发送一个任务；第三，确认页面仍然自动出现用户消息、计划步骤、工具调用和完成状态；第四，点击“上下文”，确认长期记忆和短期上下文仍然可以查看。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        这说明前端接口没有变化，但后端编排已经切换到 Runner。

### 42.10.6 curl 验证 SSE

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

## 42.11 常见问题

- 问题：为什么本章没有明显改变页面？

​        解释：本章是执行链路收敛，属于架构对齐。前端接口保持不变，页面应该继续正常工作。

- 问题：为什么不直接把模型工具选择也放进本章？

​        解释：工具选择策略会影响所有工具调用，风险和讲解量都很大。第 42 章先把入口统一，第 43 章再升级工具选择。

- 问题：为什么 `AgentRunnerStreamItem.payload` 不是 Pydantic 模型？

​        解释：Runner 属于应用层，不应该依赖 HTTP 响应模型。HTTP 路由负责把领域对象转成 Pydantic 响应。

- 问题：为什么后台任务现在还是执行已有计划，而不是直接处理用户消息？

​        解释：本章先让后台计划执行复用统一 Runner。后续任务恢复和 Harness 会继续扩展消息级后台任务。

## 42.12 本章小结

​        本章完成了 Agent 主执行链路的第一轮最终对齐：

​        放到工程语境里看，第一，新增 `AgentRunnerService`；第二，新增 `AgentRunnerStreamItem`；第三，`/messages/stream` 改成调用 Runner；第四，`/plan/execute` 改成调用 Runner；第五，`AgentTaskRunner` 后台计划任务改成调用 Runner；第六，新增 Runner 单元测试，验证流式事件顺序。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        从这一章开始，后续模型工具选择、任务恢复、Harness 评测和生产化状态管理都有了更清楚的主入口。

## 42.13 下一章预告

​        第 43 章会进入模型工具选择策略增强，让模型结合任务目标、短期上下文、长期记忆、工具 schema、子 Agent 能力和沙箱状态，输出结构化 tool call 或 agent handoff。
