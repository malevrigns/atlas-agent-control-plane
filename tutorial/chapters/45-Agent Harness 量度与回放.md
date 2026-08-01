# 第四十五章. Agent Harness 量度与回放

## 45.1 本章目标

​        学完本章后，你将能够：

​        从实现顺序看，第一，理解为什么 Agent 项目需要 Harness，而不只是普通单元测试；第二，使用固定任务集保存回归评测用例；第三，为 Agent 事件流编写基础断言；第四，区分稳定模拟评测和真实模型评测；第五，通过接口运行 Harness 用例并查看断言结果；第六，在前端设置页增加 Harness 运行和回放入口；第七，为后续测试、调试和可观测性章节打基础。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

## 45.2 最终效果

​        本章结束后，会新增一组 Harness 接口：

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

​        放到工程语境里看，第一，查看固定评测任务集；第二，点击“模拟运行”；第三，查看 required event、required tool、forbidden event 等断言结果；第四，点击“回放”，查看这次运行产生的事件流。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

## 45.3 本章要解决的问题

​        前面章节已经有了 Planner、ReAct、工具选择、上下文工程、长期记忆、多 Agent、重试和恢复。

​        但是 Agent 系统有一个很现实的问题：

```Plain
今天改了提示词，昨天能跑通的工具调用还正常吗？
今天换了模型，任务规划是不是退化了？
今天重构了事件结构，前端还能正确展示过程吗？
```

​        如果每次都靠手动打开页面、输入任务、肉眼判断，就会有三个问题：

​        展开来看，第一，结果不稳定，真实模型和外部网页会变化；第二，覆盖不系统，容易只验证自己刚改过的地方；第三，失败难复盘，无法快速看到哪一步事件、工具或产物缺失。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        所以本章加入 Agent Harness。

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

## 45.4 本章技术方案

​        本章先实现稳定的 `simulate` 模式。

​        它不会调用真实 LLM、搜索引擎、浏览器或外部网站，而是根据用例预期生成一组稳定事件，再用同一套断言逻辑评估事件流。

​        这样设计不是偷懒，而是为了把 Harness 的基础设施先做稳：

​        具体来说，第一，固定任务集怎么保存？；第二，事件流怎么评估？；第三，断言结果怎么表达？；第四，失败任务怎么回放？；第五，前端怎么查看评测结果？。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        后续如果要加入真实模型模式，只需要把真实 Agent Runner 的事件流传给同一个：

```Plain
evaluate_events()
```

​        本章会新增：

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

​        本章暂时不做：

​        换句话说，第一，不把 Harness 运行结果落库；第二，不做真实模型批量评测；第三，不做自动评分大模型；第四，不做 CI 自动执行；第五，不做复杂指标报表。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        这些内容会在测试、调试、可观测性和生产化章节继续扩展。

## 45.5 实施步骤
### 45.5.1 创建固定任务集

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

#### 45.5.1.1 代码讲解

​        `eval_cases.yaml` 是 Harness 的固定任务集。

​        每条用例包含：

​        从实现顺序看，第一，`id`：稳定标识，接口运行时会用它定位用例；第二，`title`：页面展示标题；第三，`task`：要交给 Agent 的任务文本；第四，`description`：为什么要测这条任务；第五，`tags`：分类标签，后续可以按 browser、memory、multi_agent 过滤；第六，`expectation`：断言规则。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        `required_events` 表示事件流里必须出现这些事件。

​        `required_tools` 表示事件流里必须出现这些工具调用。

​        `forbidden_events` 表示不能出现这些事件。例如 `task_error` 出现时，就说明这条任务失败。

### 45.5.2 定义 Harness 领域实体

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

#### 45.5.2.1 代码讲解

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

​        放到工程语境里看，第一，运行模式；第二，用例 ID；第三，prompt 摘要；第四，事件流；第五，断言结果；第六，开始和结束时间。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        本章先把 `events` 保留为 `dict`，因为 Harness 以后可能评估来自不同来源的事件：真实 Runner、模拟 Runner、历史回放、测试 fixture。

### 45.5.3 实现 AgentHarnessService

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

#### 45.5.3.1 业务流程

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

#### 45.5.3.2 为什么先做 simulate

​        真实 Agent 运行会依赖模型、搜索、浏览器、网络和沙箱状态。它适合做最终验收，但不适合作为每次开发改动后的最小回归验证。

​        `simulate` 模式让我们先稳定这些基础设施：

​        展开来看，第一，用例读取；第二，断言逻辑；第三，回放接口；第四，前端结果展示。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        等这些稳定后，再把真实 Runner 的事件流接进来。

### 45.5.4 编写断言逻辑

​        `evaluate_events()` 是本章最重要的函数：

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

#### 45.5.4.1 代码讲解

​        这里故意只依赖事件字典。

​        因为 Harness 不应该只服务于某一个接口。未来事件可能来自：

​        具体来说，第一，SSE 真实运行；第二，后台任务历史记录；第三，数据库中保存的事件；第四，本章模拟事件；第五，单元测试中的 fixture。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        只要事件结构里有：

```Plain
type
payload.tool_name
payload.file_name
```

​        Harness 就能评估它。

### 45.5.5 新增 API Schema 和路由

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

### 45.5.6 编写单元测试

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

#### 45.5.6.1 测试重点

​        这组测试不访问数据库、Redis、LLM、浏览器或外部网络。

​        它只验证 Harness 的核心规则：

​        换句话说，第一，模拟运行能产生通过结果；第二，缺少关键工具调用时会失败；第三，保存的运行结果可以回放。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

### 45.5.7 新增前端 API 函数

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

#### 45.5.7.1 代码讲解

​        这里不让组件直接写 `fetch()`。

​        组件只关心三个动作：

​        从实现顺序看，第一，读取任务集；第二，运行某条用例；第三，回放某次运行。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        接口路径、统一响应解析和错误处理都放在 `lib` 层。

### 45.5.8 新增 HarnessPanel 组件

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

#### 45.5.8.1 组件职责

​        `HarnessPanel` 是自包含组件。

​        它自己负责：

​        放到工程语境里看，第一，加载 Harness 用例；第二，运行用例；第三，保存最近运行结果；第四，请求回放；第五，展示断言和事件。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        `page.tsx` 不需要新增状态，这样页面文件不会继续膨胀。

### 45.5.9 接入设置页

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

#### 45.5.9.1 为什么放在设置页

​        Harness 是工程验证能力，不是普通聊天交互。

​        它适合放在“设置/工程能力”区域，和模型、工具、记忆、多 Agent 配置放在一起。

​        主工作台仍然专注于：

```Plain
用户输入任务 -> Agent 执行 -> 展示过程和结果
```

## 45.6 关键理解

​        本章最重要的是理解 Harness 和普通测试的区别。

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

## 45.7 运行验证

​        下面命令默认在项目根目录执行：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
```

### 45.7.1 运行后端测试

```Bash
cd api
uv run python -m unittest tests/test_agent_harness_service.py -v
```

​        预期看到：

```Plain
OK
```

### 45.7.2 编译后端代码

```Bash
uv run python -m compileall app
```

### 45.7.3 检查前端类型

```Bash
cd ../ui
pnpm typecheck
```

### 45.7.4 启动服务

​        回到项目根目录：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
docker compose up -d api ui nginx
```

### 45.7.5 验证 Harness 接口

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

### 45.7.6 页面验证

​        访问：

```Plain
http://localhost:8088
```

​        操作：

​        展开来看，第一，点击左侧“设置”；第二，找到 “Agent Harness” 面板；第三，点击任意用例的“模拟运行”；第四，确认断言列表显示通过或失败；第五，点击“回放”；第六，确认事件回放区域出现 message_created、plan_created、tool_called、task_done 等事件。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

## 45.8 常见问题

- 问题：为什么本章不直接跑真实模型？

​        解释：真实模型和外部工具会带来网络、密钥和结果随机性。本章先把 Harness 基础设施做成稳定闭环，后续真实模式复用同一套断言。

- 问题：Harness 运行记录为什么重启后丢失？

​        解释：第 45 章先用进程内存保存结果，目的是讲清楚 Harness 流程。后续如果要做团队共享报告，可以新增数据库表。

- 问题：`mode=real` 为什么报错？

​        解释：本章只开放 `simulate`。真实运行需要考虑 LLM、Sandbox、浏览器、搜索、超时和成本控制，会在后续测试和生产化章节逐步接入。

- 问题：为什么 Harness 放在设置页？

​        解释：它是工程验证入口，不是普通对话流程。对话体验仍然在主工作台，Harness 用来检查回归和复盘失败。

## 45.9 本章小结

​        本章完成了 Agent Harness 的最小闭环：

​        具体来说，第一，新增固定评测任务集；第二，新增 Harness 领域实体；第三，新增 Harness 应用服务；第四，新增 Harness 接口；第五，新增 Harness 单元测试；第六，前端设置页新增 Agent Harness 面板；第七，支持模拟运行、断言结果和事件回放。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        从这一章开始，项目不再只靠手动页面验证。后续改模型、改提示词、改工具系统时，可以用固定任务集检查核心 Agent 链路是否退化。

## 45.10 下一章预告

​        第 46 章会进入生产构建、一键启动与 Nginx，继续完善 Dockerfile、启动脚本、健康检查、迁移流程和网关配置。
