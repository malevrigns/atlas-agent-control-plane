# 第十九章. ReActAgent 循步而行

## 19.1 本章目标
​        第 18 章已经让 PlannerAgent 生成了结构化计划，但计划本身还只是静态列表。真正的 Agent 工作台不能停在“我有一个计划”，还要继续把计划步骤变成可观察的执行过程：某个步骤开始了，调用了哪个工具，工具返回了什么结果，这个步骤是否完成，整项任务是否结束。
​        本章会实现 ReActAgent 的第一个同步执行闭环。后端会从会话事件里找到最新的 `plan_created`，逐个读取计划步骤，写入 `step_started`、`tool_called`、`step_completed`、`task_done` 或 `task_error` 事件。前端会在计划面板里加入“执行”按钮，并根据执行事件把步骤状态从 `pending` 更新到 `running` 或 `completed`。这一章仍然不引入后台队列和流式推送，目的是先把 Reason、Act、Observe 的最小链路跑通。

![ReActAgent 执行闭环示意图](../assets/react-agent-loop.png)

## 19.2 最终效果
​        本章结束后，后端新增接口：

```Plain
POST /api/sessions/{session_id}/plan/execute
```

​        前端计划面板会新增“执行”按钮。
​        操作流程：

```Plain
创建会话
  |
  v
生成计划
  |
  v
点击执行
  |
  v
后端逐步产生步骤事件和工具事件
  |
  v
前端把步骤状态更新为 completed
```

​        本章先做同步执行。也就是说，点击执行后，请求会等待所有步骤执行完成再返回。第 20 章会把这个流程改造成后台任务和 Redis Stream。

## 19.3 本章要解决的问题
​        第 18 章已经能生成计划，但计划还只是静态列表。
​        真实 Agent 需要继续执行计划：

```Plain
计划步骤
  |
  v
开始执行步骤
  |
  v
选择工具
  |
  v
得到工具结果
  |
  v
完成步骤
```

​        这就是 ReAct 的核心：

```Plain
Reason  判断当前要做什么
Act     调用工具或执行动作
Observe 读取动作结果
Repeat  继续下一步
```

## 19.4 本章技术方案
​        本章后端调用链路：

```Plain
POST /api/sessions/{session_id}/plan/execute
  |
  v
ReActAgentService.execute_latest_plan()
  |
  +-- 找到最新 plan_created 事件
  +-- 遍历计划步骤
  +-- 写入 step_started
  +-- 调用内置工具
  +-- 写入 tool_called
  +-- 写入 step_completed
  +-- 最后写入 task_done
```

​        前端调用链路：

```Plain
PlanPanel 执行按钮
  |
  v
session-store.executePlan()
  |
  v
/api/sessions/{session_id}/plan/execute
  |
  v
追加执行事件
  |
  v
根据 step_completed 更新计划步骤状态
```

​        本章暂时不做后台任务，也不模拟真正的长时间执行；步骤事件不会通过 SSE 边执行边推送，工具也先不接真实文件、Shell 或浏览器能力。这些能力会在第 20 章和后续沙箱阶段继续完成。本章先把“计划可以被执行，并且执行过程能落成事件”这件事讲清楚。

## 19.5 新增和修改的文件

```Plain
README.md
api/README.md
api/app/api/routes/sessions.py
api/app/application/react_agent_service.py
api/app/domain/sessions/entities.py
api/app/schemas/session.py
docs/course/chapters/19-react-agent.md
ui/README.md
ui/app/components/chat-workspace.tsx
ui/app/components/plan-panel.tsx
ui/app/lib/session-api.ts
ui/app/page.tsx
ui/app/stores/session-store.ts
ui/app/types.ts
```

## 19.6 实施步骤
### 19.6.1 扩展会话事件类型
​        打开 `api/app/domain/sessions/entities.py`，扩展 `SessionEventType`：

```Python
class SessionEventType(StrEnum):
    message_created = "message_created"
    plan_created = "plan_created"
    step_started = "step_started"
    tool_called = "tool_called"
    step_completed = "step_completed"
    task_done = "task_done"
    task_error = "task_error"
```

#### 19.6.1.1 代码讲解
​        第 18 章只有 `plan_created`，表示计划已经生成。
​        第 19 章新增的是执行过程事件。`step_started` 表示某个计划步骤开始运行，`tool_called` 表示执行步骤时调用了工具，`step_completed` 表示该步骤完成，`task_done` 表示整份计划已经执行结束，`task_error` 则表示执行过程中出现错误。它们会和 `plan_created` 一起进入 `session_events` 表，前端可以按事件顺序还原一条完整执行轨迹。

### 19.6.2 编写 ReActAgentService
​        创建 `api/app/application/react_agent_service.py`：

```Python
from uuid import UUID

from app.application.unit_of_work import UnitOfWork
from app.core.exceptions import AppException
from app.domain.sessions.entities import SessionEvent, SessionEventType, SessionStatus
from app.infrastructure.agent_tools.builtin import build_builtin_tool_registry


class ReActAgentService:
    """第 19 章的 ReActAgent 同步执行服务。

    本章先把计划步骤转成可观察事件，不引入后台队列。
    第 20 章会把这里的执行过程迁移到 Redis Stream 和 TaskRunner。
    """

    def __init__(self, uow: UnitOfWork) -> None:
        # ===================== 第1步：保存数据库事务和工具注册表 =====================
        self.uow = uow
        self.registry = build_builtin_tool_registry()

    # ===================== 第2步：执行当前会话的最新计划 =====================
    async def execute_latest_plan(self, session_id: UUID) -> list[SessionEvent]:
        """执行最近一次 plan_created 事件中的计划步骤。"""

        session = await self.uow.sessions.get(session_id)
        if session is None:
            raise AppException(
                message="session not found",
                code=404,
                status_code=404,
            )

        events = await self.uow.session_events.list_by_session(session_id)
        plan_event = self._find_latest_plan_event(events)
        plan = plan_event.payload
        steps = plan.get("steps", [])
        if not steps:
            raise AppException(
                message="plan has no steps",
                code=400,
                status_code=400,
            )

        created_events: list[SessionEvent] = []
        await self.uow.sessions.update_status(session_id, SessionStatus.running.value)

        try:
            for index, step in enumerate(steps, start=1):
                created_events.extend(
                    await self._execute_step(
                        session_id=session_id,
                        plan=plan,
                        step=step,
                        index=index,
                    )
                )

            done_event = await self.uow.session_events.add(
                session_id=session_id,
                event_type=SessionEventType.task_done,
                payload={
                    "plan_id": plan.get("id") or plan.get("plan_id"),
                    "message": "计划步骤已全部执行完成。",
                },
            )
            created_events.append(done_event)
            await self.uow.sessions.update_status(session_id, SessionStatus.idle.value)
            await self.uow.sessions.touch(session_id)
            await self.uow.commit()
            return created_events
        except Exception as error:
            error_event = await self.uow.session_events.add(
                session_id=session_id,
                event_type=SessionEventType.task_error,
                payload={
                    "plan_id": plan.get("id") or plan.get("plan_id"),
                    "message": str(error),
                },
            )
            await self.uow.sessions.update_status(session_id, SessionStatus.failed.value)
            await self.uow.commit()
            return [*created_events, error_event]
```

#### 19.6.2.1 代码讲解
​        `execute_latest_plan()` 是本章核心流程：

```Plain
检查会话
  |
  v
加载事件
  |
  v
找到最新 plan_created
  |
  v
取出 plan.steps
  |
  v
把会话状态改成 running
  |
  v
逐步执行
  |
  v
写入 task_done
  |
  v
把会话状态改回 idle
```

​        注意，本章把所有事件一次性写完再返回。第 20 章会改成后台任务边执行边推送。

### 19.6.3 执行单个步骤
​        继续在 `react_agent_service.py` 中编写：

```Python
    # ===================== 第3步：执行单个计划步骤 =====================
    async def _execute_step(
        self,
        session_id: UUID,
        plan: dict,
        step: dict,
        index: int,
    ) -> list[SessionEvent]:
        """把一个计划步骤转换成 started/tool/completed 三类事件。"""

        plan_id = plan.get("id") or plan.get("plan_id")
        step_id = step.get("id")
        started = await self.uow.session_events.add(
            session_id=session_id,
            event_type=SessionEventType.step_started,
            payload={
                "plan_id": plan_id,
                "step_id": step_id,
                "index": index,
                "title": step.get("title", ""),
            },
        )

        tool_result = self._call_tool_for_step(step)
        tool_called = await self.uow.session_events.add(
            session_id=session_id,
            event_type=SessionEventType.tool_called,
            payload={
                "plan_id": plan_id,
                "step_id": step_id,
                "tool_name": tool_result["tool_name"],
                "arguments": tool_result["arguments"],
                "output": tool_result["output"],
            },
        )

        completed = await self.uow.session_events.add(
            session_id=session_id,
            event_type=SessionEventType.step_completed,
            payload={
                "plan_id": plan_id,
                "step_id": step_id,
                "index": index,
                "title": step.get("title", ""),
                "summary": tool_result["output"],
            },
        )
        return [started, tool_called, completed]
```

#### 19.6.3.1 代码讲解
​        一个步骤会产生三个事件：

```Plain
step_started
tool_called
step_completed
```

​        这样前端不只知道“最后完成了”，还知道中间调用了什么工具。
​        `tool_called.payload` 里保存：

```Plain
tool_name
arguments
output
```

​        这会成为后续工具预览面板的数据来源。

### 19.6.4 选择工具并查找计划
​        继续在 `react_agent_service.py` 中编写：

```Python
    # ===================== 第4步：用教学工具模拟步骤执行 =====================
    def _call_tool_for_step(self, step: dict) -> dict:
        """根据步骤内容选择并调用一个内置工具。"""

        title = str(step.get("title", ""))
        description = str(step.get("description", ""))
        text = f"{title} {description}".strip()

        if "拆" in title or "步骤" in title or "计划" in title:
            tool = self.registry.get("draft_plan")
            arguments = {"task": text}
        elif "关键" in title or "重点" in title:
            tool = self.registry.get("extract_keywords")
            arguments = {"text": text}
        else:
            tool = self.registry.get("summarize_text")
            arguments = {"text": text}

        result = tool.call(arguments)
        return {
            "tool_name": result.tool_name,
            "arguments": result.arguments,
            "output": result.output,
        }

    # ===================== 第5步：找到最新 plan_created 事件 =====================
    def _find_latest_plan_event(self, events: list[SessionEvent]) -> SessionEvent:
        """从会话事件中倒序查找最近一次计划。"""

        for event in reversed(events):
            if event.type is SessionEventType.plan_created:
                return event
        raise AppException(
            message="plan not found",
            code=404,
            status_code=404,
        )
```

#### 19.6.4.1 代码讲解
​        本章还没有接真实搜索、文件、Shell 和浏览器工具，所以 `_call_tool_for_step()` 先使用第 17 章的内置教学工具。
​        选择规则很简单：如果步骤标题里包含“拆”“步骤”或“计划”，就调用 `draft_plan`；如果标题里包含“关键”或“重点”，就调用 `extract_keywords`；其他情况则调用 `summarize_text`。这不是最终的智能决策，只是用确定性规则把 ReAct 的执行链路跑通。后续接入真实工具和模型选择时，这里会从规则分支升级为更完整的工具调度逻辑。

### 19.6.5 扩展接口响应
​        打开 `api/app/schemas/session.py`，新增：

```Python
class PlanExecuteResponse(BaseModel):
    events: list[SessionEventResponse]
```

#### 19.6.5.1 代码讲解
​        执行接口返回事件列表。
​        前端拿到后可以：

```Plain
追加到事件列表
根据 step_completed 更新步骤状态
```

### 19.6.6 新增执行接口
​        打开 `api/app/api/routes/sessions.py`，新增依赖：

```Python
def build_react_agent_service(
    db_session: AsyncSession = Depends(get_db_session),
) -> ReActAgentService:
    return ReActAgentService(UnitOfWork(db_session))
```

​        新增接口：

```Python
@router.post(
    "/{session_id}/plan/execute",
    response_model=ApiResponse[PlanExecuteResponse],
)
async def execute_plan(
    session_id: UUID,
    service: ReActAgentService = Depends(build_react_agent_service),
) -> ApiResponse[PlanExecuteResponse]:
    events = await service.execute_latest_plan(session_id)
    return ApiResponse(
        data=PlanExecuteResponse(
            events=[to_event_response(event) for event in events],
        )
    )
```

#### 19.6.6.1 代码讲解
​        接口路径放在：

```Plain
/api/sessions/{session_id}/plan/execute
```

​        原因是执行计划仍然属于某个会话。
​        第 20 章做后台任务后，这个接口会变成“启动任务”，而不是同步等所有步骤执行完。

### 19.6.7 扩展前端 API 和类型
​        打开 `ui/app/types.ts`，新增：

```TypeScript
export type PlanExecuteData = {
  events: SessionEventItem[];
};
```

​        打开 `ui/app/lib/session-api.ts`，新增：

```TypeScript
export function executePlan(sessionId: string): Promise<PlanExecuteData> {
  return requestApi<PlanExecuteData>(
    `/api/sessions/${sessionId}/plan/execute`,
    {
      method: "POST",
    },
  );
}
```

#### 19.6.7.1 代码讲解
​        执行计划不需要请求体，因为后端会从会话事件里找到最新的 `plan_created`。
​        如果会话里没有计划，后端会返回：

```Plain
plan not found
```

### 19.6.8 在 store 中加入执行计划逻辑
​        打开 `ui/app/stores/session-store.ts`，新增状态：

```TypeScript
executingPlan: boolean;
```

​        新增工具函数：

```TypeScript
function applyExecutionEvents(plan: AgentPlan | null, events: SessionEventItem[]) {
  if (!plan) {
    return null;
  }
  const nextSteps = plan.steps.map((step) => ({ ...step }));

  for (const event of events) {
    const payload = event.payload as Record<string, unknown>;
    const stepId = typeof payload.step_id === "string" ? payload.step_id : null;
    if (!stepId) {
      continue;
    }
    const step = nextSteps.find((item) => item.id === stepId);
    if (!step) {
      continue;
    }
    if (event.type === "step_started") {
      step.status = "running";
    }
    if (event.type === "step_completed") {
      step.status = "completed";
    }
    if (event.type === "task_error") {
      step.status = "failed";
    }
  }

  return {
    ...plan,
    steps: nextSteps,
  };
}
```

​        新增 action：

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

  set({ actionError: null, executingPlan: true });
  try {
    const result = await executePlan(sessionId);
    set((state) => {
      const currentEvents =
        state.events.type === "ready" ? state.events.data : [];
      const events = [...currentEvents, ...result.events];
      return {
        events: { type: "ready", data: events },
        latestPlan: applyExecutionEvents(state.latestPlan, result.events),
      };
    });
    await get().refreshSessions();
  } catch (error) {
    set({ actionError: getErrorMessage(error) });
  } finally {
    set({ executingPlan: false });
  }
}
```

#### 19.6.8.1 代码讲解
​        前端拿到执行事件后，会做两件事：

```Plain
追加事件列表
更新计划步骤状态
```

​        `applyExecutionEvents()` 负责把执行事件转换成 UI 状态。收到 `step_started` 时，对应步骤变成 `running`；收到 `step_completed` 时，对应步骤变成 `completed`；如果出现 `task_error`，相关步骤会被标记为 `failed`。这样计划面板看到的状态不是前端凭空猜出来的，而是从后端执行事件推导出来的。

### 19.6.9 更新计划面板
​        打开 `ui/app/components/plan-panel.tsx`，新增执行按钮：

```TypeScript
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
```

​        在步骤标题下方展示状态：

```TypeScript
<span className="mt-1 inline-flex rounded bg-white px-2 py-0.5 text-xs text-slate-500">
  {step.status}
</span>
```

#### 19.6.9.1 代码讲解
​        生成和执行是两个动作：

```Plain
生成：创建 plan_created 事件
执行：创建 step/tool/task 事件
```

​        计划还不存在时，执行按钮禁用。
​        执行中，生成和执行按钮都禁用，避免重复提交。

### 19.6.10 接入聊天工作台
​        打开 `ui/app/components/chat-workspace.tsx`，把执行参数传给 `PlanPanel`：

```TypeScript
<PlanPanel
  disabled={!selectedSession}
  executing={executingPlan}
  onCreatePlan={onCreatePlan}
  onExecutePlan={onExecutePlan}
  plan={plan}
  planning={planning}
/>
```

​        打开 `ui/app/page.tsx`，传入 store action：

```TypeScript
<ChatWorkspace
  executingPlan={workspace.executingPlan}
  onExecutePlan={workspace.executePlan}
    ...
/>
```

#### 19.6.10.1 代码讲解
​        `page.tsx` 仍然只做页面编排。
​        真正的业务动作在 `session-store.ts`，接口请求在 `session-api.ts`，展示在 `plan-panel.tsx`。

## 19.7 关键理解
​        ReActAgent 不只是“生成一段回复”。
​        它会围绕步骤执行：

```Plain
开始步骤
调用工具
观察工具结果
完成步骤
```

​        本章用同步接口把这个过程跑通。它的缺点是：如果步骤执行很久，请求会一直等待。
​        第 20 章会把它改成后台任务：

```Plain
点击执行 -> 立即返回 task_id -> 后台执行 -> Redis Stream 推送事件
```

## 19.8 技术难点与亮点
​        本章的技术难点在于把“执行”拆成可追踪事件。服务层必须先从事件列表里找到最新计划，再把每个步骤拆成开始、工具调用和完成三个阶段；工具调用结果不能只留在内存里，而要进入事件 payload，方便前端后续展示工具详情。前端也不能只在点击按钮后把所有步骤直接标成完成，而要根据后端返回的事件逐步推导状态。
​        项目亮点在于计划已经真正进入执行流程。第 17 章的工具协议不再只是演示面板里的 schema，而是开始被 ReActAgentService 调用；第 18 章的计划面板也不再只展示静态步骤，而是能展示执行后的状态变化。这为第 20 章的后台任务、Redis Stream 和流式事件打好了接口和状态基础。

## 19.9 面试考点
​        面试里可以把 ReAct 拆成 Reason、Act 和 Observe 来讲。Reason 对应选择当前步骤和判断要调用什么工具，Act 对应实际工具调用，Observe 对应读取工具结果并把结果写回事件流。步骤执行要拆成多个事件，是为了让前端和后续任务系统都能观察中间过程，而不是只拿到一个最终完成状态。同步执行适合教学闭环，后台执行适合长任务；工具结果进入 payload，是为了让事件本身具备可回放和可展示的信息。

## 19.10 运行验证
​        下面命令默认在项目根目录执行。

### 19.10.1 检查后端代码

```Bash
cd api
uv run python -m compileall app
```

### 19.10.2 检查前端类型

```Bash
cd ../ui
pnpm typecheck
```

### 19.10.3 重新构建并启动服务

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
docker compose build --pull=false api ui
docker compose up -d --force-recreate api ui nginx
```

​        如果刚启动后出现 `502 Bad Gateway`：

```Bash
docker compose ps
docker compose restart nginx
```

### 19.10.4 创建会话

```Bash
curl -X POST http://localhost:8088/api/sessions \
  -H "Content-Type: application/json" \
  -d '{"title":"第 19 章执行测试"}'
```

​        记录返回的 `id`。

### 19.10.5 生成计划

```Bash
curl -X POST http://localhost:8088/api/sessions/{session_id}/plan \
  -H "Content-Type: application/json" \
  -d '{"task":"帮我规划一个 AI Agent 项目"}'
```

### 19.10.6 执行计划

```Bash
curl -X POST http://localhost:8088/api/sessions/{session_id}/plan/execute
```

​        预期返回的事件中包含：

```Plain
step_started
tool_called
step_completed
task_done
```

### 19.10.7 验证页面
​        访问：

```Plain
http://localhost:8088
```

​        操作步骤：
​        验证页面时，先创建或选择一个会话，输入任务并生成计划，再点击计划面板中的“执行”。执行完成后，步骤状态应该从 `pending` 变为 `completed`，事件列表里也应该出现 `step_started`、`tool_called`、`step_completed` 和 `task_done`。这个结果说明计划、工具协议、后端事件和前端状态已经串成了一个最小 ReAct 执行闭环。

## 19.11 常见问题

### 19.11.1 执行计划返回 `plan not found` 怎么办
​        当前会话还没有生成计划，或者生成计划的事件没有写入成功。先调用 `/api/sessions/{session_id}/plan` 生成计划，再调用 `/api/sessions/{session_id}/plan/execute` 执行计划；如果页面操作，先点击“生成”，看到计划面板出现步骤后再点击“执行”。

### 19.11.2 为什么点击执行后不是一点点流式出现
​        本章实现的是同步执行，请求会等待所有步骤执行完成后再返回事件列表。这样可以先把事件结构、工具调用和前端状态更新讲清楚。第 20 章会改成后台任务和 Redis Stream，届时执行事件会边产生边推送。

### 19.11.3 为什么工具结果看起来像摘要或草稿
​        本章使用第 17 章的教学工具模拟执行，因此结果会像摘要、关键词或计划草稿。这里关注的是 ReAct 执行链路，而不是工具本身的真实能力。后续接入文件、Shell、浏览器等工具后，`tool_called` 事件里的输出会变成更具体的观察结果。

## 19.12 本章小结
​        本章完成了 ReActAgent 的第一个执行闭环。后端新增步骤和任务执行事件，实现了 `ReActAgentService`，可以从当前会话的最新计划中读取步骤，并为每个步骤写入 started、tool、completed 三类事件，最后用 `task_done` 或 `task_error` 收尾。前端计划面板新增执行按钮，执行结果返回后会追加事件，并根据事件更新步骤状态。
​        第 20 章会进入 AgentTaskRunner 与 Redis Stream，把同步执行升级为后台任务和流式事件。到那时，执行接口会从“等待所有步骤完成”变成“启动任务并持续观察任务状态”。
