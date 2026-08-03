# 第二十四章. 多 Agent 协作统筹

## 24.1 本章目标

​        学完本章后，你将能够：

​        具体来说，第一，理解多 Agent 协作和 A2A 远程 Agent 的区别；第二，设计 Manager / Worker / Reviewer 三类协作角色；第三，编写多 Agent 协作领域对象和应用服务；第四，提供多 Agent 角色列表和协作运行接口；第五，把多 Agent 协作注册成 AgentTool；第六，让计划执行时可以自动命中多 Agent 工具；第七，在前端工具预览中展示多 Agent 分工、执行、评审和汇总结果。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

## 24.2 最终效果

​        本章结束后，新增接口：

```Plain
GET  /api/multi-agent/roles
POST /api/multi-agent/run
```

​        访问：

```Plain
http://localhost:8088
```

​        创建会话后，发送任务：

```Plain
请让多个 Agent 分工协作，帮我制定一个功能上线计划并评审风险
```

​        然后点击：

```Plain
创建计划 -> 执行计划
```

​        工具预览中会出现：

```Plain
multi_agent_collaborate
Manager Agent
Worker Agent / Researcher
Worker Agent / Planner
Worker Agent / QA
Reviewer Agent
```

​        这说明多 Agent 协作已经进入真实会话执行链路，而不是单独的演示按钮。

## 24.3 本章要解决的问题

​        第 23 章已经完成了 A2A 工具接入。

​        A2A 解决的是：

```Plain
当前系统如何调用一个远程 Agent？
```

​        多 Agent 协作要解决的是：

```Plain
当前系统内部如何组织多个 Agent 分工、执行、评审和汇总？
```

​        两者关系是：

```Plain
A2A：跨系统调用远程 Agent
多 Agent：本系统内组织多个角色协作
```

​        一个成熟 Agent 系统不能只做“单个 Agent 调工具”。复杂任务通常需要：

```Plain
Manager    读懂目标，拆任务
Worker     执行具体子任务
Reviewer   检查质量和风险
Manager    汇总最终答案
```

​        本章先实现一个确定性的多 Agent 编排闭环。它不会马上启动多个真实 LLM 实例，而是先把数据结构、接口、工具事件和前端展示跑通。

​        这样做的好处是：

​        换句话说，第一，本地验证稳定，不依赖模型输出是否随机；第二，后续接真实多 Agent Runner 时，不需要重做前端和事件协议；第三，用户能先在页面中看到多 Agent 协作过程。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

## 24.4 技术方案

​        本章新增一条链路：

```Plain
用户任务
  |
  v
PlannerAgent 创建计划
  |
  v
ReActAgentService 执行步骤
  |
  v
multi_agent_collaborate 工具
  |
  v
MultiAgentService
  |
  +-- Manager 拆任务
  +-- Worker 执行子任务
  +-- Reviewer 评审结果
  +-- Manager 汇总答案
  |
  v
session_events.tool_called
  |
  v
前端工具预览卡片
```

​        本章暂时不做这些内容：

​        从实现顺序看，第一，不启动多个真实 LLM Agent；第二，不做多 Agent 并发执行；第三，不做角色配置页面；第四，不做长期记忆参与分工；第五，不做复杂 Harness 评测。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        这些内容会在后续 Agent Runner、Memory 和 Harness 章节继续增强。

## 24.5 新增和修改的文件

```Plain
README.md
backend/api/README.md
backend/api/app/domain/multi_agent/__init__.py
backend/api/app/domain/multi_agent/entities.py
backend/api/app/application/multi_agent_service.py
backend/api/app/schemas/multi_agent.py
backend/api/app/presentation/http/routes/multi_agent.py
backend/api/app/presentation/http/router.py
backend/api/app/infrastructure/agent_tools/multi_agent.py
backend/api/app/infrastructure/agent_tools/builtin.py
backend/api/app/application/react_agent_service.py
frontend/web/app/types.ts
frontend/web/app/lib/multi-agent-api.ts
frontend/web/app/components/multi-agent-panel.tsx
frontend/web/app/components/tool-preview-panel.tsx
frontend/web/app/components/chat-workspace.tsx
frontend/web/app/page.tsx
docs/course/chapters/36-multi-agent-orchestration.md
```

## 24.6 实施步骤
### 24.6.1 定义多 Agent 领域对象

​        创建 `backend/api/app/domain/multi_agent/__init__.py`：

```Python
"""Multi-agent collaboration domain package."""
```

​        创建 `backend/api/app/domain/multi_agent/entities.py`：

```Python
from dataclasses import dataclass

@dataclass(slots=True)
class MultiAgentRole:
    """多 Agent 协作中的角色定义。"""

    key: str
    name: str
    responsibility: str
    capability: str

@dataclass(slots=True)
class MultiAgentSubTask:
    """Manager Agent 拆出来的子任务。"""

    id: str
    assignee: str
    title: str
    instruction: str
    expected_output: str
    status: str
    output: str

@dataclass(slots=True)
class MultiAgentReview:
    """Reviewer Agent 对 Worker 输出的评审结果。"""

    reviewer: str
    status: str
    comments: list[str]
    improvement: str

@dataclass(slots=True)
class MultiAgentRunResult:
    """一次完整多 Agent 协作的结果。"""

    kind: str
    task: str
    manager: str
    roles: list[MultiAgentRole]
    subtasks: list[MultiAgentSubTask]
    review: MultiAgentReview
    final_answer: str
```

#### 24.6.1.1 代码讲解

​        这里没有把多 Agent 结果直接写成一个 `dict`，而是先定义领域对象。

​        原因是多 Agent 协作会越来越复杂。后续可能会加入：

​        放到工程语境里看，第一，多个 Worker 并发执行；第二，Reviewer 打分；第三，Manager 根据评审结果重新分派；第四，子任务绑定文件、网页、Shell 输出和记忆片段。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        先把领域对象定义清楚，后面扩展会更稳。

​        字段含义：

​        展开来看，第一，`MultiAgentRole`：描述一个 Agent 角色负责什么；第二，`MultiAgentSubTask`：描述 Manager 拆出来的一项工作；第三，`MultiAgentReview`：描述 Reviewer 的检查意见；第四，`MultiAgentRunResult`：描述一次完整协作结果。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

### 24.6.2 实现多 Agent 应用服务

​        创建 `backend/api/app/application/multi_agent_service.py`：

```Python
from app.domain.multi_agent.entities import (
    MultiAgentReview,
    MultiAgentRole,
    MultiAgentRunResult,
    MultiAgentSubTask,
)

class MultiAgentService:
    """多 Agent 协作编排服务。

    当前版本先实现确定性的 Manager / Worker / Reviewer 协作闭环。
    后续章节会继续把这里升级为更完整的 Agent Runner 和 Harness。
    """

    # ===================== 第1步：定义协作角色 =====================
    def list_roles(self) -> list[MultiAgentRole]:
        """返回当前系统内置的多 Agent 角色。"""

        # 1. 角色定义放在应用服务中，方便 API、工具和前端复用。
        # 2. 本章先固定三类角色，后续设置页会把角色配置抽到可编辑配置中。
        return [
            MultiAgentRole(
                key="manager",
                name="Manager Agent",
                responsibility="理解用户目标，拆解子任务，并决定谁来执行。",
                capability="任务拆解、角色分派、结果汇总。",
            ),
            MultiAgentRole(
                key="worker",
                name="Worker Agent",
                responsibility="执行 Manager 分派的具体子任务。",
                capability="资料整理、方案生成、局部执行。",
            ),
            MultiAgentRole(
                key="reviewer",
                name="Reviewer Agent",
                responsibility="检查 Worker 输出是否满足目标，并给出改进意见。",
                capability="质量评审、风险检查、遗漏补充。",
            ),
        ]

    # ===================== 第2步：运行一次多 Agent 协作 =====================
    def run_collaboration(self, task: str) -> MultiAgentRunResult:
        """围绕一个任务运行 Manager -> Worker -> Reviewer -> 汇总流程。"""

        # 1. 清理任务文本。多 Agent 协作至少需要一个明确目标。
        clean_task = " ".join(task.split())
        if not clean_task:
            clean_task = "整理当前任务的目标、执行步骤和验收标准。"

        # 2. Manager Agent 拆解任务。
        #    本章用确定性规则生成子任务，保证本地验证稳定可复现。
        subtasks = self._plan_subtasks(clean_task)

        # 3. Worker Agent 执行子任务。
        #    这里先用字符串模拟 Worker 输出，后续会替换成真实子 Agent 执行。
        completed_subtasks = [
            self._run_worker_task(subtask, clean_task)
            for subtask in subtasks
        ]

        # 4. Reviewer Agent 评审结果。
        #    评审信息会进入前端工具预览，帮助用户看到“不是只执行，还要检查”。
        review = self._review_outputs(completed_subtasks)

        # 5. Manager Agent 汇总最终回答。
        final_answer = self._summarize(clean_task, completed_subtasks, review)

        # 6. 统一返回结果。AgentTool 会把它序列化为 kind=multi_agent_result。
        return MultiAgentRunResult(
            kind="multi_agent_result",
            task=clean_task,
            manager="Manager Agent",
            roles=self.list_roles(),
            subtasks=completed_subtasks,
            review=review,
            final_answer=final_answer,
        )
```

​        后面的私有方法负责三件事：

```Plain
_plan_subtasks()     Manager 拆任务
_run_worker_task()   Worker 执行任务
_review_outputs()    Reviewer 评审结果
_summarize()         Manager 汇总答案
```

#### 24.6.2.1 业务讲解

​        本章的 `MultiAgentService` 是“协作编排器”。

​        它不是普通 CRUD Service，因为它不只是读写一张表，而是在组织一个工作流：

```Plain
输入任务
  |
  v
拆成多个子任务
  |
  v
执行子任务
  |
  v
评审子任务结果
  |
  v
汇总最终结果
```

​        目前 Worker 输出是确定性字符串。这里不是偷懒，而是先稳定协议。

​        等协议稳定后，再把 Worker 替换成真实 LLM Agent，就不会影响：

​        具体来说，第一，API 响应结构；第二，AgentTool 输出结构；第三，前端工具预览结构；第四，会话事件结构。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

### 24.6.3 定义 API Schema

​        创建 `backend/api/app/schemas/multi_agent.py`：

```Python
from pydantic import BaseModel, Field

class MultiAgentRoleResponse(BaseModel):
    key: str  # 程序内部识别角色的稳定标识，例如 manager。
    name: str  # 展示给用户看的角色名称。
    responsibility: str  # 这个角色在协作流程中负责什么。
    capability: str  # 当前角色擅长处理的任务类型。

class MultiAgentSubTaskResponse(BaseModel):
    id: str  # Manager 拆出的子任务 ID。
    assignee: str  # 负责执行该子任务的 Agent 角色。
    title: str  # 子任务标题。
    instruction: str  # Manager 交给 Worker 的具体指令。
    expected_output: str  # 期望 Worker 产出的结果形态。
    status: str  # pending、completed、failed 等状态。
    output: str  # Worker 执行后的输出。

class MultiAgentReviewResponse(BaseModel):
    reviewer: str  # 执行评审的 Agent 名称。
    status: str  # approved 或 needs_revision。
    comments: list[str]  # Reviewer 给出的检查意见。
    improvement: str  # 面向下一轮协作的改进建议。

class MultiAgentRunRequest(BaseModel):
    task: str = Field(min_length=1, max_length=4000)

class MultiAgentRunResponse(BaseModel):
    kind: str  # 固定为 multi_agent_result，前端用它选择预览卡片。
    task: str  # 本次协作围绕的用户任务。
    manager: str  # 负责拆解和汇总的 Agent。
    roles: list[MultiAgentRoleResponse]
    subtasks: list[MultiAgentSubTaskResponse]
    review: MultiAgentReviewResponse
    final_answer: str

class MultiAgentRoleListResponse(BaseModel):
    items: list[MultiAgentRoleResponse]
```

#### 24.6.3.1 字段讲解

​        `kind` 非常关键。

​        后端工具输出最终会写入：

```Plain
session_events.payload.output
```

​        这个字段本质上是字符串。前端需要知道这段字符串应该按什么卡片展示，所以统一使用：

```JSON
{"kind":"multi_agent_result"}
```

​        前端看到 `kind=multi_agent_result`，就展示多 Agent 协作卡片。

### 24.6.4 新增多 Agent API 路由

​        创建 `backend/api/app/presentation/http/routes/multi_agent.py`：

```Python
from fastapi import APIRouter, Depends

from app.application.multi_agent_service import MultiAgentService
from app.domain.multi_agent.entities import (
    MultiAgentReview,
    MultiAgentRole,
    MultiAgentRunResult,
    MultiAgentSubTask,
)
from app.schemas.common import ApiResponse
from app.schemas.multi_agent import (
    MultiAgentReviewResponse,
    MultiAgentRoleListResponse,
    MultiAgentRoleResponse,
    MultiAgentRunRequest,
    MultiAgentRunResponse,
    MultiAgentSubTaskResponse,
)

router = APIRouter(prefix="/multi-agent", tags=["multi-agent"])

# ===================== 第1步：创建多 Agent 应用服务 =====================
def build_multi_agent_service() -> MultiAgentService:
    """创建多 Agent 协作服务。"""

    # 1. 本章服务不依赖数据库，直接创建即可。
    # 2. 后续多 Agent 配置和运行记录变复杂后，再从这里注入仓库或配置管理器。
    return MultiAgentService()

# ===================== 第2步：领域对象转换为 API 响应 =====================
def to_role_response(role: MultiAgentRole) -> MultiAgentRoleResponse:
    # 角色信息会展示在前端环境面板和接口响应中。
    return MultiAgentRoleResponse(
        key=role.key,
        name=role.name,
        responsibility=role.responsibility,
        capability=role.capability,
    )

def to_subtask_response(subtask: MultiAgentSubTask) -> MultiAgentSubTaskResponse:
    # 子任务是 Manager 分派给 Worker 的最小工作单元。
    return MultiAgentSubTaskResponse(
        id=subtask.id,
        assignee=subtask.assignee,
        title=subtask.title,
        instruction=subtask.instruction,
        expected_output=subtask.expected_output,
        status=subtask.status,
        output=subtask.output,
    )

def to_review_response(review: MultiAgentReview) -> MultiAgentReviewResponse:
    # 评审结果用于说明这次协作是否通过 Reviewer 检查。
    return MultiAgentReviewResponse(
        reviewer=review.reviewer,
        status=review.status,
        comments=review.comments,
        improvement=review.improvement,
    )

def to_run_response(result: MultiAgentRunResult) -> MultiAgentRunResponse:
    # 1. MultiAgentRunResult 是领域对象。
    # 2. API 需要转成 Pydantic DTO，保证前端拿到稳定字段。
    return MultiAgentRunResponse(
        kind=result.kind,
        task=result.task,
        manager=result.manager,
        roles=[to_role_response(role) for role in result.roles],
        subtasks=[to_subtask_response(subtask) for subtask in result.subtasks],
        review=to_review_response(result.review),
        final_answer=result.final_answer,
    )

# ===================== 第3步：查询内置多 Agent 角色 =====================
@router.get("/roles", response_model=ApiResponse[MultiAgentRoleListResponse])
async def list_multi_agent_roles(
    service: MultiAgentService = Depends(build_multi_agent_service),
) -> ApiResponse[MultiAgentRoleListResponse]:
    """返回当前多 Agent 协作中可用的角色。"""

    # 1. 从服务读取角色列表。
    # 2. 转成响应 DTO，给前端环境面板和 curl 验证使用。
    return ApiResponse(
        data=MultiAgentRoleListResponse(
            items=[to_role_response(role) for role in service.list_roles()],
        )
    )

# ===================== 第4步：运行一次多 Agent 协作演示 =====================
@router.post("/run", response_model=ApiResponse[MultiAgentRunResponse])
async def run_multi_agent_collaboration(
    payload: MultiAgentRunRequest,
    service: MultiAgentService = Depends(build_multi_agent_service),
) -> ApiResponse[MultiAgentRunResponse]:
    """围绕一个任务运行 Manager -> Worker -> Reviewer -> 汇总流程。"""

    # 1. 接收调用方传来的 task。
    # 2. 应用服务负责编排角色、分派子任务、评审并汇总。
    result = service.run_collaboration(payload.task)

    # 3. 返回结构化协作结果，便于前端展示多 Agent 过程。
    return ApiResponse(data=to_run_response(result))
```

​        打开 `backend/api/app/presentation/http/router.py`，注册路由：

```Python
from app.presentation.http.routes import (
    a2a,
    agent_core,
    agent_thinking,
    config,
    files,
    llm,
    mcp,
    multi_agent,
    sandboxes,
    sessions,
    status,
)

api_router.include_router(multi_agent.router)
```

#### 24.6.4.1 业务讲解

​        `/api/multi-agent/run` 是一个直接验证接口。

​        它不是前端最终入口。真实页面中，用户仍然通过：

```Plain
发送任务 -> 创建计划 -> 执行计划
```

​        来触发多 Agent 协作。

​        保留这个接口的原因是：

​        换句话说，第一，便于用 `curl` 快速验证服务是否正常；第二，便于后续测试多 Agent 编排服务；第三，设置页或调试页可以读取同一套角色信息。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

### 24.6.5 把多 Agent 注册成 AgentTool

​        创建 `backend/api/app/infrastructure/agent_tools/multi_agent.py`：

```Python
import json

from app.application.multi_agent_service import MultiAgentService
from app.domain.agent_core.tools import (
    AgentTool,
    ToolDefinition,
    ToolParameter,
    ToolRegistry,
)
from app.domain.multi_agent.entities import MultiAgentRunResult

def register_multi_agent_tools(
    registry: ToolRegistry,
    service: MultiAgentService | None = None,
) -> None:
    """把多 Agent 协作编排注册成 AgentTool。"""

    # 1. 创建或复用多 Agent 应用服务。
    #    测试可以注入 fake service，正常运行时使用内置确定性编排。
    multi_agent_service = service or MultiAgentService()

    # 2. 注册一个通用工具。
    #    ReAct 执行器只需要调用工具，不需要知道 Manager/Worker/Reviewer 细节。
    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="multi_agent_collaborate",
                description="让 Manager、Worker、Reviewer 多个 Agent 围绕一个任务协作。",
                parameters=[
                    ToolParameter(
                        name="task",
                        type="string",
                        description="需要多个 Agent 分工协作完成的任务。",
                    ),
                ],
            ),
            # 3. handler 是工具执行入口。
            #    AgentTool 会先校验 task 参数，再调用这里执行协作流程。
            handler=lambda task: _format_multi_agent_result(
                multi_agent_service.run_collaboration(task=str(task)),
            ),
        )
    )
```

​        打开 `backend/api/app/infrastructure/agent_tools/builtin.py`，注册工具：

```Python
from app.infrastructure.agent_tools.multi_agent import register_multi_agent_tools

def build_builtin_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    register_builtin_tools(registry)
    register_search_tools(registry)
    register_sandbox_tools(registry)
    register_mcp_tools(registry)
    register_a2a_tools(registry)
    register_multi_agent_tools(registry)
    return registry
```

#### 24.6.5.1 为什么要做成工具

​        多 Agent 协作本质上也是 Agent 可以调用的一种能力。

​        如果只做成普通接口，计划执行时就无法自动进入：

```Plain
step_started -> tool_called -> step_completed
```

​        注册成 `AgentTool` 后，多 Agent 协作和文件、Shell、浏览器、搜索、MCP、A2A 都进入同一套工具事件系统。

### 24.6.6 让 ReAct 执行器选择多 Agent 工具

​        打开 `backend/api/app/application/react_agent_service.py`，在工具选择逻辑中加入多 Agent 分支：

```Python
if self._needs_multi_agent(text):
    # 多 Agent 分支：把“分工、协作、评审、汇总”类任务交给协作编排工具。
    # 工具输出会带 kind=multi_agent_result，前端据此展示多 Agent 专用卡片。
    tool = self.registry.get("multi_agent_collaborate")
    arguments = {"task": self._extract_multi_agent_task(text)}
elif self._needs_a2a(text):
    tool = self.registry.get("a2a_call")
    arguments = {
        "agent_key": "demo_researcher",
        "message": self._extract_a2a_message(text),
    }
```

​        再新增判断和参数提取方法：

```Python
def _needs_multi_agent(self, text: str) -> bool:
    """判断当前步骤是否需要多 Agent 协作编排。"""

    if any(keyword in text for keyword in ["A2A", "a2a", "远程 Agent", "远程智能体"]):
        return False

    keywords = [
        "多 Agent",
        "多Agent",
        "多个 Agent",
        "多个智能体",
        "分工",
        "协作",
        "评审",
        "Reviewer",
        "Manager",
        "Worker",
        "汇总",
    ]
    return any(keyword in text for keyword in keywords)

def _extract_multi_agent_task(self, text: str) -> str:
    """从计划文本中提取多 Agent 协作任务。"""

    clean_text = " ".join(text.split())
    for keyword in ["多 Agent", "多Agent", "多个 Agent", "多个智能体"]:
        clean_text = clean_text.replace(keyword, " ")
    return " ".join(clean_text.split())[:400] or text[:400]
```

#### 24.6.6.1 为什么先判断多 Agent，再判断 A2A

​        本章的多 Agent 是本系统内部编排。

​        A2A 是远程 Agent 调用。

​        用户输入里可能同时出现“Agent”和“协作”，所以 `_needs_multi_agent()` 里先排除明显 A2A 关键词：

```Plain
A2A
远程 Agent
远程智能体
```

​        这样“远程 Agent 协作”仍然走 A2A，“多个 Agent 分工评审”才走本章的多 Agent 工具。

### 24.6.7 前端新增类型和请求函数

​        打开 `frontend/web/app/types.ts`，新增：

```TypeScript
export type MultiAgentRoleItem = {
  key: string; // 程序识别角色的稳定标识，例如 manager。
  name: string; // 展示给用户看的角色名称。
  responsibility: string; // 角色在协作流程中负责什么。
  capability: string; // 角色擅长处理的任务类型。
};

export type MultiAgentRoleListData = {
  items: MultiAgentRoleItem[];
};
```

​        创建 `frontend/web/app/lib/multi-agent-api.ts`：

```TypeScript
import { requestApi } from "./api";
import type { MultiAgentRoleListData } from "../types";

export function fetchMultiAgentRoles(): Promise<MultiAgentRoleListData> {
  return requestApi<MultiAgentRoleListData>("/api/multi-agent/roles");
}
```

#### 24.6.7.1 为什么前端只读取角色，不直接提供运行按钮

​        多 Agent 协作应该在真实对话执行链路中触发。

​        如果页面上额外放一个“运行多 Agent 演示”按钮，用户会误以为它和会话执行无关。

​        所以本章前端只在环境面板展示角色信息。真正执行入口仍然是：

```Plain
发送任务 -> 创建计划 -> 执行计划
```

### 24.6.8 新增多 Agent 环境面板

​        创建 `frontend/web/app/components/multi-agent-panel.tsx`：

```TypeScript
import { GitBranch, RefreshCcw } from "lucide-react";

import type { LoadState, MultiAgentRoleListData } from "../types";

type MultiAgentPanelProps = {
  onRefresh: () => void;
  roles: LoadState<MultiAgentRoleListData>;
};

// ===================== 第1步：展示多 Agent 协作角色 =====================
export function MultiAgentPanel({ onRefresh, roles }: MultiAgentPanelProps) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-base font-semibold text-slate-950">
            <GitBranch size={17} aria-hidden="true" />
            多 Agent 协作
          </h2>
          <p className="mt-1 text-sm leading-5 text-slate-500">
            Manager 拆解任务，Worker 执行子任务，Reviewer 评审结果
          </p>
        </div>
        <button
          className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
          onClick={onRefresh}
          title="刷新多 Agent 角色"
          type="button"
        >
          <RefreshCcw size={16} aria-hidden="true" />
        </button>
      </div>

      <div className="mt-4">
        <RoleList state={roles} />
      </div>
    </div>
  );
}
```

#### 24.6.8.1 组件职责

​        这个组件只负责展示角色。

​        它不创建计划，也不执行工具。这样职责更清楚：

```Plain
MultiAgentPanel        展示协作角色
ToolPreviewPanel       展示工具调用结果
ChatWorkspace          组合聊天区和右侧工作台
page.tsx               组织页面级状态加载
```

### 24.6.9 工具预览支持多 Agent 结果

​        打开 `frontend/web/app/components/tool-preview-panel.tsx`。

​        新增结果类型：

```TypeScript
type MultiAgentResultPayload = {
  kind: "multi_agent_result";
  task: string;
  manager: string;
  roles: Array<{
    key: string;
    name: string;
    responsibility: string;
    capability: string;
  }>;
  subtasks: Array<{
    id: string;
    assignee: string;
    title: string;
    instruction: string;
    expected_output: string;
    status: string;
    output: string;
  }>;
  review: {
    reviewer: string;
    status: string;
    comments: string[];
    improvement: string;
  };
  final_answer: string;
};
```

​        新增解析函数：

```TypeScript
function parseMultiAgentResult(value: string): MultiAgentResultPayload | null {
  try {
    // 1. MultiAgentTool 的 output 也是 JSON 字符串。
    //    kind 字段用来区分它和截图、搜索、MCP、A2A 等其他工具结果。
    const payload = JSON.parse(value) as Partial<MultiAgentResultPayload>;

    // 2. 做最小结构检查。
    //    只在关键字段存在时进入多 Agent 专用卡片，避免普通文本被误判。
    if (
      payload.kind === "multi_agent_result" &&
      typeof payload.task === "string" &&
      typeof payload.manager === "string" &&
      Array.isArray(payload.roles) &&
      Array.isArray(payload.subtasks) &&
      payload.review &&
      typeof payload.review === "object" &&
      typeof payload.final_answer === "string"
    ) {
      const review = payload.review as Partial<MultiAgentResultPayload["review"]>;

      // 3. 归一化数组元素。
      //    后端字段如果以后扩展，前端仍然只读取当前需要展示的字段。
      return {
        kind: "multi_agent_result",
        task: payload.task,
        manager: payload.manager,
        roles: payload.roles.map((item) => ({
          key: getString(item.key),
          name: getString(item.name),
          responsibility: getString(item.responsibility),
          capability: getString(item.capability),
        })),
        subtasks: payload.subtasks.map((item) => ({
          id: getString(item.id),
          assignee: getString(item.assignee),
          title: getString(item.title),
          instruction: getString(item.instruction),
          expected_output: getString(item.expected_output),
          status: getString(item.status),
          output: getString(item.output),
        })),
        review: {
          reviewer: getString(review.reviewer),
          status: getString(review.status),
          comments: Array.isArray(review.comments)
            ? review.comments.map((comment) => getString(comment))
            : [],
          improvement: getString(review.improvement),
        },
        final_answer: payload.final_answer,
      };
    }
  } catch {
    // 4. 不是 JSON 或不是多 Agent 结构时，交给普通文本预览。
    return null;
  }
  return null;
}
```

​        再在工具详情里加入：

```TypeScript
const multiAgentResult = parseMultiAgentResult(output);
```

​        并在展示分支中加入：

```TypeScript
{multiAgentResult ? (
  <MultiAgentResultPreview result={multiAgentResult} />
) : null}
```

#### 24.6.9.1 业务讲解

​        前端工具预览不应该通过工具名硬编码所有展示逻辑。

​        更稳定的方式是让工具输出带 `kind`：

```Plain
browser_screenshot
search_results
mcp_tool_result
a2a_task_result
multi_agent_result
```

​        这样后续新增工具时，可以继续新增一种结构化结果，而不破坏旧工具。

### 24.6.10 把多 Agent 状态接入页面

​        打开 `frontend/web/app/page.tsx`，新增状态：

```TypeScript
const [multiAgentRoles, setMultiAgentRoles] = useState<
  LoadState<MultiAgentRoleListData>
>({ type: "loading" });
```

​        在初始化状态请求中加入：

```TypeScript
const [
  apiData,
  databaseData,
  sandboxData,
  vncData,
  mcpServerData,
  mcpToolData,
  a2aConceptData,
  a2aCardData,
  a2aAgentData,
  multiAgentRoleData,
] = await Promise.all([
  requestApi<ApiStatusData>("/api/status"),
  requestApi<DatabaseStatusData>("/api/status/database"),
  fetchCurrentSandbox(),
  fetchVncStatus(),
  fetchMcpServers(),
  fetchMcpTools(),
  fetchA2aConcepts(),
  fetchA2aAgentCard(),
  fetchA2aAgents(),
  fetchMultiAgentRoles(),
]);
```

​        新增刷新方法：

```TypeScript
async function refreshMultiAgent() {
  setMultiAgentRoles({ type: "loading" });
  try {
    const roles = await fetchMultiAgentRoles();
    setMultiAgentRoles({ type: "ready", data: roles });
  } catch (error) {
    const message = error instanceof Error ? error.message : "unknown error";
    setMultiAgentRoles({ type: "error", message });
  }
}
```

​        最后把它传给 `ChatWorkspace` 和 `ToolPreviewPanel`。

## 24.7 关键理解

​        本章最重要的是区分三类能力：

```Plain
普通工具调用：一个 Agent 调一个工具
A2A：当前系统调用远程 Agent
多 Agent：当前系统内部组织多个角色协作
```

​        多 Agent 不等于“多调几个工具”。

​        它更强调：

​        从实现顺序看，第一，谁负责拆解？；第二，谁负责执行？；第三，谁负责检查？；第四，如果检查不通过，如何改进？；第五，最终结果如何汇总给用户？。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        本章先完成确定性闭环。后续真实多 Agent Runner 会继续升级：

```Plain
Manager 由 LLM 生成子任务
Worker 可以调用不同工具
Reviewer 可以基于验收标准打分
Harness 可以反复执行和评估
Memory 可以影响任务分派
```

## 24.8 运行验证

​        下面命令默认在项目根目录执行：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
```

### 24.8.1 编译后端

```Bash
cd backend/api
uv run python -m compileall app
```

### 24.8.2 检查前端类型

```Bash
cd ../../frontend/web
pnpm typecheck
```

### 24.8.3 启动服务

​        回到项目根目录：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
docker compose build api ui
docker compose up -d --force-recreate api ui nginx
```

​        如果只是后端路由没有生效，优先重建并重启 API 和 Nginx：

```Bash
docker compose build api
docker compose up -d --force-recreate api nginx
```

### 24.8.4 验证多 Agent 角色接口

```Bash
curl http://localhost:8088/api/multi-agent/roles
```

​        预期返回中包含：

```Plain
Manager Agent
Worker Agent
Reviewer Agent
```

### 24.8.5 验证多 Agent 协作运行接口

```Bash
curl -X POST http://localhost:8088/api/multi-agent/run \
  -H "Content-Type: application/json" \
  -d '{"task":"请让多个 Agent 分工协作，帮我制定一个功能上线计划并评审风险"}'
```

​        预期返回中包含：

```Plain
multi_agent_result
subtasks
review
final_answer
```

### 24.8.6 验证工具注册

```Bash
curl http://localhost:8088/api/agent-core/tools
```

​        预期工具列表中包含：

```Plain
multi_agent_collaborate
```

### 24.8.7 页面验证

​        访问：

```Plain
http://localhost:8088
```

​        操作：

​        放到工程语境里看，第一，创建或选择一个会话；第二，输入：`请让多个 Agent 分工协作，帮我制定一个功能上线计划并评审风险`；第三，点击发送；第四，点击创建计划；第五，点击执行计划；第六，打开右侧“工具预览”。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        预期看到：

​        展开来看，第一，环境页签里出现“多 Agent 协作”角色面板；第二，工具页签里出现 `multi_agent_collaborate`；第三，工具详情里能看到子任务分派、Worker 输出、Reviewer 评审和最终汇总。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

## 24.9 本章小结

​        本章完成了多 Agent 协作的第一版闭环：

​        具体来说，第一，定义了多 Agent 领域对象；第二，实现了 Manager / Worker / Reviewer 协作服务；第三，新增多 Agent 角色和运行接口；第四，把多 Agent 协作注册成 AgentTool；第五，ReAct 执行器可以自动选择 `multi_agent_collaborate`；第六，前端环境面板展示多 Agent 角色；第七，前端工具预览展示多 Agent 协作结果。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        从这一章开始，系统不再只是“一个 Agent 调工具”，而是具备了内部多角色协作的基础形态。

---

[← 第二十三章. A2A 协议与工具接入](23-A2A%20协议与工具接入.md) · [返回目录](../README.md) · [第二十五章. 设置面板落成 →](25-设置面板落成.md)
