# 第十八章. PlannerAgent 任务运筹

## 18.1 本章目标
​        第 17 章已经让系统具备了 Memory 和工具协议，但 Agent 要真正执行一个复杂任务，还需要先知道“要按什么顺序做”。这正是 PlannerAgent 的位置：它不负责直接完成用户任务，而是把用户输入转换成结构化计划，让后续执行器有明确的目标、步骤和预期输出。
​        本章会把 PlannerAgent 接入真实会话。后端会新增计划步骤领域模型和 `PlannerService`，优先使用 LLM 生成 JSON 计划，解析失败或模型不可用时生成稳定的教学 fallback，再把计划保存成 `plan_created` 会话事件。前端会在聊天工作台右侧加入计划面板，并从事件列表中恢复最新计划。这样计划不再是临时页面状态，而是会话时间线里真实发生过的一次 Agent 动作。

## 18.2 最终效果
​        本章结束后，后端新增接口：

```Plain
POST /api/sessions/{session_id}/plan
```

​        前端聊天工作台右侧会新增“计划面板”。
​        使用流程：

```Plain
创建会话
  |
  v
输入任务
  |
  v
点击计划面板里的“生成”
  |
  v
后端生成 plan_created 事件
  |
  v
前端展示计划步骤
```

​        本章只生成计划，不执行计划。第 19 章会实现 ReActAgent，让计划步骤逐步执行并流式展示工具调用。

## 18.3 本章要解决的问题
​        第 17 章已经有了 Memory 和工具协议，但还没有真正的任务规划能力。
​        如果用户输入：

```Plain
帮我从 0 到 1 实现一个 AI Agent 项目
```

​        普通 ChatBot 可能直接给一段回答。
​        PlannerAgent 要做的是把这个任务变成结构化计划：

```Plain
目标：实现一个可运行的 AI Agent 项目

步骤：
1. 明确需求和边界
2. 设计后端接口和数据模型
3. 设计前端交互
4. 接入工具和执行流程
5. 验证和总结
```

​        这样后续 ReActAgent 才能逐步执行，而不是在一条消息里把所有事情说完。

## 18.4 本章技术方案
​        本章后端调用链路：

```Plain
POST /api/sessions/{session_id}/plan
  |
  v
PlannerService.create_plan()
  |
  +-- 检查会话是否存在
  +-- 调用 LLMService.chat()
  +-- 解析 JSON 计划
  +-- 写入 session_events.plan_created
  +-- 更新会话 updated_at
```

​        前端调用链路：

```Plain
PlanPanel
  |
  v
session-store.createPlan()
  |
  v
session-api.createPlan()
  |
  v
/api/sessions/{session_id}/plan
  |
  v
把 plan_created 事件追加到当前事件列表
```

​        为什么计划保存成事件，而不是新建计划表？
​        当前阶段更重要的是让会话时间线能看到 Agent 做了什么。计划生成本身就是会话中的一个重要动作，适合先进入 `session_events`。
​        后续如果计划需要编辑、版本管理、多人协作，再单独拆出 `plans` 表也不晚。

## 18.5 新增和修改的文件

```Plain
README.md
api/README.md
api/app/api/routes/sessions.py
api/app/application/planner_service.py
api/app/domain/agent_core/planner.py
api/app/domain/sessions/entities.py
api/app/schemas/session.py
docs/course/chapters/18-planner-agent.md
ui/README.md
ui/app/components/chat-workspace.tsx
ui/app/components/plan-panel.tsx
ui/app/lib/session-api.ts
ui/app/page.tsx
ui/app/stores/session-store.ts
ui/app/types.ts
```

## 18.6 实施步骤
### 18.6.1 扩展会话事件类型
​        打开 `api/app/domain/sessions/entities.py`，扩展 `SessionEventType`：

```Python
class SessionEventType(StrEnum):
    message_created = "message_created"
    plan_created = "plan_created"
```

#### 18.6.1.1 代码讲解
​        第 09 章只有 `message_created`，表示用户消息被创建。
​        本章新增 `plan_created`，表示 PlannerAgent 为当前会话生成了一份计划。
​        事件表已经有：

```Plain
type
payload
created_at
```

​        所以不需要新增迁移文件。计划会保存在 `payload` 里。

### 18.6.2 定义计划领域模型
​        创建 `api/app/domain/agent_core/planner.py`：

```Python
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID, uuid4


# ===================== 第1步：定义计划步骤状态 =====================
class PlanStepStatus(StrEnum):
    """计划步骤的执行状态。

    第 18 章只生成计划，不执行步骤，所以默认都是 pending。
    """

    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


# ===================== 第2步：定义一个计划步骤 =====================
@dataclass(slots=True)
class PlanStep:
    """PlannerAgent 生成的单个任务步骤。"""

    id: UUID
    title: str
    description: str
    expected_output: str
    status: PlanStepStatus = PlanStepStatus.pending


# ===================== 第3步：定义完整计划 =====================
@dataclass(slots=True)
class AgentPlan:
    """PlannerAgent 对用户任务生成的完整计划。"""

    id: UUID
    title: str
    goal: str
    steps: list[PlanStep]
    source: str


# ===================== 第4步：提供便捷创建函数 =====================
def create_agent_plan(
    title: str,
    goal: str,
    steps: list[PlanStep],
    source: str,
) -> AgentPlan:
    """统一创建计划对象，避免应用层手动生成 plan id。"""

    return AgentPlan(
        id=uuid4(),
        title=title,
        goal=goal,
        steps=steps,
        source=source,
    )


def create_plan_step(
    title: str,
    description: str,
    expected_output: str,
) -> PlanStep:
    """统一创建计划步骤，默认状态为 pending。"""

    return PlanStep(
        id=uuid4(),
        title=title,
        description=description,
        expected_output=expected_output,
    )
```

#### 18.6.2.1 代码讲解
​        `PlanStepStatus` 先定义四种状态：

```Plain
pending
running
completed
failed
```

​        第 18 章只生成计划，所以步骤默认是 `pending`。第 19 章执行步骤时，才会让状态进入 `running`、`completed` 或 `failed`。
​        `AgentPlan.source` 用来记录计划来源：

```Plain
llm       来自真实模型
fallback  来自教学 fallback
```

​        这样前端和调试日志可以知道这份计划是不是模型生成的。

### 18.6.3 编写 PlannerService
​        创建 `api/app/application/planner_service.py`。
​        核心代码如下：

```Python
import json
from uuid import UUID

from app.application.llm_service import LLMService
from app.application.unit_of_work import UnitOfWork
from app.core.exceptions import AppException
from app.domain.agent_core.planner import (
    AgentPlan,
    PlanStep,
    create_agent_plan,
    create_plan_step,
)
from app.domain.llm.entities import LLMMessage
from app.domain.sessions.entities import SessionEvent, SessionEventType


class PlannerService:
    """第 18 章的 PlannerAgent 应用服务。

    它负责把用户任务转换成结构化计划，并把计划保存成 session event。
    """

    def __init__(
        self,
        uow: UnitOfWork,
        llm_service: LLMService | None = None,
    ) -> None:
        # ===================== 第1步：保存依赖 =====================
        self.uow = uow
        self.llm_service = llm_service or LLMService()

    # ===================== 第2步：生成计划并写入会话事件 =====================
    async def create_plan(
        self,
        session_id: UUID,
        task: str,
    ) -> tuple[AgentPlan, SessionEvent]:
        """为会话生成计划，并保存 plan_created 事件。"""

        clean_task = task.strip()
        if not clean_task:
            raise AppException(
                message="task is required",
                code=400,
                status_code=400,
            )

        session = await self.uow.sessions.get(session_id)
        if session is None:
            raise AppException(
                message="session not found",
                code=404,
                status_code=404,
            )

        plan = await self._generate_plan(clean_task)
        event = await self.uow.session_events.add(
            session_id=session_id,
            event_type=SessionEventType.plan_created,
            payload=self._plan_to_payload(plan),
        )
        await self.uow.sessions.touch(session_id)
        await self.uow.commit()
        return plan, event
```

#### 18.6.3.1 代码讲解
​        `create_plan()` 的业务流程是：

```Plain
清理 task
  |
  v
检查会话是否存在
  |
  v
生成 AgentPlan
  |
  v
写入 plan_created 事件
  |
  v
更新会话 updated_at
  |
  v
提交事务
```

​        生成计划和保存事件放在同一个应用服务里，是因为它们属于同一个业务动作。

### 18.6.4 调用 LLM 并解析计划
​        继续在 `planner_service.py` 中编写：

```Python
    # ===================== 第3步：优先使用 LLM 生成计划 =====================
    async def _generate_plan(self, task: str) -> AgentPlan:
        """调用 LLM 生成结构化计划；不可用时返回教学 fallback。"""

        try:
            result = await self.llm_service.chat(
                messages=[
                    LLMMessage(
                        role="system",
                        content=(
                            "你是一个 PlannerAgent。请把用户任务拆成 3 到 5 个可执行步骤。"
                            "只返回 JSON，不要返回 Markdown。JSON 格式为："
                            '{"title":"计划标题","goal":"目标","steps":['
                            '{"title":"步骤标题","description":"步骤说明","expected_output":"预期输出"}'
                            "]}"
                        ),
                    ),
                    LLMMessage(role="user", content=task),
                ],
                temperature=0.2,
                max_tokens=1200,
            )
            return self._parse_llm_plan(task=task, content=result.content)
        except AppException:
            # 没配置 API Key 或 provider 出错时，仍然给出可运行的教学计划。
            # 这样第 18 章不会因为外部服务不可用而无法验证主流程。
            return self._build_fallback_plan(task)
```

#### 18.6.4.1 代码讲解
​        这里要求模型只返回 JSON。
​        原因是后端要把计划保存成结构化数据。如果模型返回一大段 Markdown，前端很难稳定解析步骤。
​        这里捕获 `AppException` 后返回 fallback 计划。这样即使本机没有配置 `LLM_API_KEY`，也能跑通：

```Plain
接口
事件保存
前端计划面板
```

​        如果你已经配置了 DeepSeek 或其他 OpenAI 兼容模型，`source` 会更可能是 `llm`；如果模型不可用，`source` 会是 `fallback`。

### 18.6.5 解析 JSON 和保存事件 payload
​        继续在 `planner_service.py` 中编写：

```Python
    # ===================== 第4步：解析 LLM 返回的 JSON 计划 =====================
    def _parse_llm_plan(self, task: str, content: str) -> AgentPlan:
        """把模型返回文本解析成 AgentPlan。"""

        try:
            data = json.loads(self._strip_code_fence(content))
        except json.JSONDecodeError:
            return self._build_fallback_plan(task)

        steps = [
            create_plan_step(
                title=str(item.get("title", "")).strip() or "未命名步骤",
                description=str(item.get("description", "")).strip() or "补充步骤说明",
                expected_output=str(item.get("expected_output", "")).strip()
                or "完成该步骤的可检查结果",
            )
            for item in data.get("steps", [])
            if isinstance(item, dict)
        ]
        if not steps:
            return self._build_fallback_plan(task)

        return create_agent_plan(
            title=str(data.get("title", "")).strip() or "任务执行计划",
            goal=str(data.get("goal", "")).strip() or task,
            steps=steps[:5],
            source="llm",
        )

    # ===================== 第5步：处理模型可能返回的代码块包裹 =====================
    def _strip_code_fence(self, content: str) -> str:
        """去掉 ```json ... ``` 这类包裹，提升 JSON 解析成功率。"""

        clean_content = content.strip()
        if clean_content.startswith("```"):
            lines = clean_content.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            return "\n".join(lines).strip()
        return clean_content

    # ===================== 第7步：把 AgentPlan 转成事件 payload =====================
    def _plan_to_payload(self, plan: AgentPlan) -> dict:
        """把计划对象转换成可以存入 JSONB 的字典。"""

        return {
            "id": str(plan.id),
            "plan_id": str(plan.id),
            "title": plan.title,
            "goal": plan.goal,
            "source": plan.source,
            "steps": [
                {
                    "id": str(step.id),
                    "title": step.title,
                    "description": step.description,
                    "expected_output": step.expected_output,
                    "status": step.status.value,
                }
                for step in plan.steps
            ],
        }
```

#### 18.6.5.1 代码讲解
​        模型有时会返回带代码块包裹的内容：

~~~Plain
```json
{ ... }
```
~~~

​        所以 `_strip_code_fence()` 会先去掉外层包裹，再把内部字符串交给 `json.loads()`。`_parse_llm_plan()` 也不是直接相信模型输出，而是先处理 JSON 解析失败，再处理没有 `steps` 的情况，最后给单个空字段补默认值。这样即使模型返回格式不够稳定，接口也不会把半成品结构直接交给前端。
​        `_plan_to_payload()` 负责把 `AgentPlan` 转成 JSONB 可保存的字典。这里同时保存 `id` 和 `plan_id`：`id` 方便前端按统一计划类型读取，`plan_id` 则保留事件语义，明确这个字段表示计划 ID。

### 18.6.6 扩展会话 Schema
​        打开 `api/app/schemas/session.py`，新增：

```Python
class PlanCreateRequest(BaseModel):
    task: str = Field(min_length=1, max_length=4000)
```

​        继续新增响应结构：

```Python
class PlanStepResponse(BaseModel):
    id: UUID
    title: str
    description: str
    expected_output: str
    status: str


class PlanResponse(BaseModel):
    id: UUID
    title: str
    goal: str
    source: str
    steps: list[PlanStepResponse]


class PlanCreateResponse(BaseModel):
    plan: PlanResponse
    event: SessionEventResponse
```

#### 18.6.6.1 代码讲解
​        `PlanCreateResponse` 同时返回：

```Plain
plan   方便前端立即展示
event  方便前端追加到事件列表
```

​        这样前端不需要生成计划后再额外请求一次事件列表。

### 18.6.7 新增会话计划接口
​        打开 `api/app/api/routes/sessions.py`。
​        新增依赖：

```Python
def build_planner_service(
    db_session: AsyncSession = Depends(get_db_session),
) -> PlannerService:
    return PlannerService(UnitOfWork(db_session), LLMService())
```

​        新增转换函数：

```Python
def to_plan_response(plan: AgentPlan) -> PlanResponse:
    return PlanResponse(
        id=plan.id,
        title=plan.title,
        goal=plan.goal,
        source=plan.source,
        steps=[
            PlanStepResponse(
                id=step.id,
                title=step.title,
                description=step.description,
                expected_output=step.expected_output,
                status=step.status.value,
            )
            for step in plan.steps
        ],
    )
```

​        新增接口：

```Python
@router.post(
    "/{session_id}/plan",
    response_model=ApiResponse[PlanCreateResponse],
)
async def create_plan(
    session_id: UUID,
    payload: PlanCreateRequest,
    service: PlannerService = Depends(build_planner_service),
) -> ApiResponse[PlanCreateResponse]:
    plan, event = await service.create_plan(
        session_id=session_id,
        task=payload.task,
    )
    return ApiResponse(
        data=PlanCreateResponse(
            plan=to_plan_response(plan),
            event=to_event_response(event),
        )
    )
```

#### 18.6.7.1 代码讲解
​        接口路径放在会话下面：

```Plain
/api/sessions/{session_id}/plan
```

​        原因是计划不是孤立存在的，它属于某一个会话。
​        这个接口后续会成为真实 Agent 流程的一部分：

```Plain
用户消息
  |
  v
生成计划
  |
  v
执行计划
  |
  v
产生工具事件和最终回答
```

### 18.6.8 扩展前端类型和 API
​        打开 `ui/app/types.ts`，新增：

```TypeScript
export type PlanStep = {
  id: string;
  title: string;
  description: string;
  expected_output: string;
  status: string;
};

export type AgentPlan = {
  id: string;
  title: string;
  goal: string;
  source: string;
  steps: PlanStep[];
};

export type PlanCreateData = {
  plan: AgentPlan;
  event: SessionEventItem;
};
```

​        打开 `ui/app/lib/session-api.ts`，新增：

```TypeScript
export function createPlan(
  sessionId: string,
  task: string,
): Promise<PlanCreateData> {
  return requestApi<PlanCreateData>(`/api/sessions/${sessionId}/plan`, {
    method: "POST",
    body: JSON.stringify({ task }),
  });
}
```

#### 18.6.8.1 代码讲解
​        前端的 `AgentPlan` 对齐后端 `PlanResponse`。
​        `createPlan()` 只负责发送请求，不处理页面状态。页面状态仍然放在 zustand store 中。

### 18.6.9 在 session-store 中加入计划状态
​        打开 `ui/app/stores/session-store.ts`，新增状态：

```TypeScript
latestPlan: AgentPlan | null;
planning: boolean;
```

​        新增 action：

```TypeScript
createPlan: async () => {
  const sessionId = get().selectedSessionId;
  if (!sessionId) {
    set({ actionError: "请先选择一个会话" });
    return;
  }

  const messageState = get().messages;
  const currentMessages =
    messageState.type === "ready" ? messageState.data : [];
  const latestUserMessage = [...currentMessages]
    .reverse()
    .find((message) => message.role === "user");
  const task = get().draft.trim() || latestUserMessage?.content.trim() || "";
  if (!task) {
    set({ actionError: "请输入任务，或先发送一条用户消息" });
    return;
  }

  set({ actionError: null, planning: true });
  try {
    const result = await createPlan(sessionId, task);
    set((state) => {
      const currentEvents =
        state.events.type === "ready" ? state.events.data : [];
      const events = [...currentEvents, result.event];
      return {
        events: { type: "ready", data: events },
        latestPlan: result.plan,
      };
    });
    await get().refreshSessions();
  } catch (error) {
    set({ actionError: getErrorMessage(error) });
  } finally {
    set({ planning: false });
  }
}
```

#### 18.6.9.1 代码讲解
​        生成计划时，任务来源有两个优先级：

```Plain
1. 当前输入框内容
2. 最近一条用户消息
```

​        这样用户有两种自然用法：可以先在输入框里写任务，直接点击计划面板生成计划；也可以先把任务作为消息发送出去，再让 PlannerAgent 根据最近一条用户消息生成计划。前者更像“先规划再发送”，后者更像“围绕已有会话继续规划”，两种路径最终都会落到同一个 `createPlan()` 动作。
​        生成成功后，前端会做两件事：

```Plain
把 plan_created 事件追加到 events
把 result.plan 保存为 latestPlan
```

### 18.6.10 从事件恢复最新计划
​        继续在 `session-store.ts` 中新增：

```TypeScript
function toPlan(event: SessionEventItem): AgentPlan | null {
  if (event.type !== "plan_created") {
    return null;
  }
  const payload = event.payload as Partial<AgentPlan>;
  if (
    !payload.id ||
    !payload.title ||
    !payload.goal ||
    !payload.source ||
    !Array.isArray(payload.steps)
  ) {
    return null;
  }
  return {
    id: String(payload.id),
    title: String(payload.title),
    goal: String(payload.goal),
    source: String(payload.source),
    steps: payload.steps,
  };
}

function getLatestPlan(events: SessionEventItem[]) {
  return [...events]
    .reverse()
    .map(toPlan)
    .find((plan): plan is AgentPlan => plan !== null) ?? null;
}
```

#### 18.6.10.1 代码讲解
​        这段代码解决的是“刷新页面后计划还在不在”的问题。
​        计划已经保存成事件，所以重新加载会话详情时，可以从事件列表中找到最后一个 `plan_created`：

```Plain
events
  |
  v
倒序查找 plan_created
  |
  v
恢复 latestPlan
```

​        这样计划面板不是临时 UI 状态，而是来自后端持久化事件。

### 18.6.11 创建计划面板组件
​        创建 `ui/app/components/plan-panel.tsx`：

```TypeScript
import { GitBranch, Loader2, Sparkles } from "lucide-react";

import type { AgentPlan } from "../types";

type PlanPanelProps = {
  disabled: boolean;
  onCreatePlan: () => void;
  plan: AgentPlan | null;
  planning: boolean;
};


// ===================== 第1步：展示当前会话的最新计划 =====================
export function PlanPanel({
  disabled,
  onCreatePlan,
  plan,
  planning,
}: PlanPanelProps) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-slate-950">计划面板</h2>
          <p className="mt-1 text-sm text-slate-500">
            根据当前任务生成 PlannerAgent 步骤
          </p>
        </div>
        <button
          className="inline-flex h-9 shrink-0 items-center gap-2 rounded-md border border-slate-200 bg-slate-950 px-3 text-sm font-medium text-white disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-200 disabled:text-slate-500"
          disabled={disabled || planning}
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
      </div>

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

#### 18.6.11.1 代码讲解
​        计划面板只负责展示和触发生成，不直接请求后端。
​        它接收：

```Plain
plan
planning
disabled
onCreatePlan
```

​        `plan.source` 会显示计划来源：

```Plain
llm
fallback
```

​        这样本地开发时可以清楚知道当前计划是否来自真实模型。

### 18.6.12 接入聊天工作台
​        打开 `ui/app/components/chat-workspace.tsx`，引入计划面板：

```TypeScript
import { PlanPanel } from "./plan-panel";
```

​        在右侧 aside 里加入：

```TypeScript
<PlanPanel
  disabled={!selectedSession}
  onCreatePlan={onCreatePlan}
  plan={plan}
  planning={planning}
/>
```

​        打开 `ui/app/page.tsx`，传入 store 状态：

```TypeScript
<ChatWorkspace
  onCreatePlan={workspace.createPlan}
  plan={workspace.latestPlan}
  planning={workspace.planning}
```

  *...*
​        />

```Plain

```

#### 18.6.12.1 代码讲解
​        计划面板被放在聊天工作台右侧。
​        这意味着它不再是独立教学面板，而是开始成为真实 Agent 工作台的一部分。
​        后续第 19 章执行步骤时，计划面板会继续扩展状态展示。

## 18.7 关键理解
​        PlannerAgent 的职责不是回答用户，而是生成执行计划。
​        它的输出应该结构化：

```Plain
目标
步骤列表
每步说明
每步预期输出
```

​        计划保存成事件，可以让前端时间线看到 Agent 做了什么，也方便后续 SSE 流式推送。

## 18.8 技术难点与亮点
​        本章的技术难点集中在“模型输出不稳定”和“计划状态不能只停留在页面上”这两件事。LLM 可能返回非法 JSON，也可能返回被 Markdown 代码块包裹的 JSON，还可能漏掉字段；服务层必须把这些情况收束成稳定的 `AgentPlan`。同时，计划生成属于会话动作，刷新页面后仍然应该能看到，因此不能只存在 zustand 临时状态里，而要写入 `session_events`。
​        项目亮点在于 PlannerAgent 已经从概念演示进入真实工作台。它使用会话 ID 定位上下文，把计划保存为 `plan_created` 事件，前端又能从事件恢复最新计划。此时右侧计划面板已经不只是教学组件，而是后续 ReActAgent 执行步骤、更新状态和展示工具结果的入口。

## 18.9 面试考点
​        面试里可以围绕 PlannerAgent 和 ReActAgent 的职责边界展开。PlannerAgent 负责把任务变成结构化计划，ReActAgent 负责拿着计划逐步执行；计划必须结构化，是因为后续步骤状态、工具调用和前端展示都依赖稳定字段。LLM 返回 JSON 不稳定时，后端要处理代码块包裹、解析失败、缺少步骤和字段缺失，而不是把原始字符串交给前端。计划暂时保存成事件，是因为当前阶段更关注会话时间线和可观察动作；如果未来需要编辑、版本管理或多人协作，再单独拆出计划表会更合适。

## 18.10 运行验证
​        下面命令默认在项目根目录执行。

### 18.10.1 检查后端代码

```Bash
cd api
uv run python -m compileall app
```

### 18.10.2 检查前端类型

```Bash
cd ../ui
pnpm typecheck
```

### 18.10.3 重新构建并启动服务
​        第 18 章修改了 API 和 UI：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
docker compose build --pull=false api ui
docker compose up -d --force-recreate api ui nginx
```

​        如果刚启动后立刻访问接口看到 `502 Bad Gateway`，先确认 API 已经健康：

```Bash
docker compose ps
```

​        如果 `atlas-api` 已经是 healthy，再单独重启 Nginx：

```Bash
docker compose restart nginx
```

### 18.10.4 创建会话

```Bash
curl -X POST http://localhost:8088/api/sessions \
  -H "Content-Type: application/json" \
  -d '{"title":"第 18 章计划测试"}'
```

​        记录返回的 `id`。

### 18.10.5 生成计划

```Bash
curl -X POST http://localhost:8088/api/sessions/{session_id}/plan \
  -H "Content-Type: application/json" \
  -d '{"task":"帮我规划一个 AI Agent 项目"}'
```

​        预期返回：

```Plain
plan.steps 至少有 3 条
event.type 是 plan_created
```

### 18.10.6 查询事件

```Bash
curl http://localhost:8088/api/sessions/{session_id}/events
```

​        预期事件列表中包含：

```Plain
plan_created
```

### 18.10.7 验证页面
​        访问：

```Plain
http://localhost:8088
```

​        操作步骤：
​        验证页面时，先创建或选择一个会话，再在输入框中写入任务，然后点击右侧计划面板里的“生成”。如果接口正常，计划面板会出现计划标题、目标、来源和步骤列表，每个步骤都应当包含标题、说明和预期输出。刷新页面后重新进入同一个会话，最新计划仍然应该从事件列表中恢复出来。

## 18.11 常见问题

### 18.11.1 计划来源显示 `fallback` 是不是错误
​        不是。`fallback` 通常表示本机没有配置 LLM，或者模型调用失败、返回内容无法解析成合法 JSON。这个状态不会影响主流程验证，因为本章需要确保即使外部模型不可用，计划接口、事件保存和前端展示仍然可以跑通。

### 18.11.2 计划生成后刷新页面还在吗
​        还在。计划会保存成 `plan_created` 事件，前端重新加载会话详情时会读取事件列表，并倒序找到最新的计划事件恢复到 `latestPlan`。这也是本章选择事件持久化，而不是只用组件状态的原因。

### 18.11.3 创建会话或生成计划接口返回 `502 Bad Gateway` 怎么办
​        这通常说明 Nginx 没有连上 API。常见场景是刚重建容器后，Nginx 仍然握着旧的 API 容器地址。先执行 `docker compose ps` 确认 `atlas-api` 已经 healthy，再执行 `docker compose restart nginx`，让网关重新解析后端容器。

### 18.11.4 为什么不直接执行计划
​        执行计划需要 ReActAgent、步骤状态流转、工具选择、工具结果事件和最终回答，这些能力不应该塞进 PlannerAgent 这一章。第 18 章只负责把任务变成可执行计划，第 19 章才会让计划进入逐步执行。

### 18.11.5 为什么不新增 `plans` 表
​        当前阶段计划只是会话中的一次 Agent 动作，保存成事件已经能满足展示、恢复和后续执行读取。等计划需要编辑、版本管理、协作或多版本对比时，再把它从事件 payload 中独立成 `plans` 表会更稳妥。

## 18.12 本章小结
​        本章完成了 PlannerAgent 的第一个真实闭环。后端新增计划领域模型和 `PlannerService`，可以调用 LLM 生成结构化计划，也能在模型不可用或 JSON 解析失败时生成 fallback 计划；计划会以 `plan_created` 事件保存到当前会话，并通过新的会话计划接口返回给前端。前端新增计划类型、计划 API、计划状态和计划面板，并能从事件列表中恢复最新计划。
​        第 19 章会实现 ReActAgent 步骤执行，让计划从“生成出来”进入“逐步运行”。到那时，`pending` 状态会开始变化，计划面板也会成为观察执行进度的核心入口。
