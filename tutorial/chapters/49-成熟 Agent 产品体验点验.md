# 第四十九章. 成熟 Agent 产品体验点验

## 49.1 本章目标

​        学完本章后，你将能够：

​        从实现顺序看，第一，理解为什么最终阶段要做产品体验验收；第二，新增产品体验验收清单接口；第三，把自然对话、计划执行、工具预览、记忆、多 Agent、Harness、浏览器和 VNC 放到同一张验收表里；第四，区分“已有自动化证据”和“必须人工观察”的验收项；第五，在设置页查看最终验收清单；第六，使用 Docker Compose 完成端到端验收。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

## 49.2 最终效果

​        本章结束后，后端新增接口：

```Plain
GET /api/acceptance/checks
```

​        通过网关访问：

```Bash
curl http://localhost:8088/api/acceptance/checks
```

​        会返回类似结构：

```JSON
{
  "code": 200,
  "message": "success",
  "data": {
    "summary": {
      "total": 11,
      "ready": 6,
      "needs_manual_check": 5
    },
    "items": [
      {
        "key": "natural_conversation",
        "title": "自然对话入口",
        "category": "conversation",
        "status": "needs_manual_check",
        "evidence": "页面发送一条任务消息后，应自动进入规划和执行流程。",
        "verify_steps": ["访问 http://localhost:8088。"],
        "related_routes": ["POST /api/sessions"]
      }
    ]
  }
}
```

​        访问：

```Plain
http://localhost:8088
```

​        点击左侧“设置”，页面中会新增：

```Plain
产品体验验收
```

​        面板会展示：

​        放到工程语境里看，第一，验收项总数；第二，已有自动化证据数量；第三，需要人工确认数量；第四，每条验收项的证据、验证步骤和相关接口。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

## 49.3 本章要解决的问题

​        前面章节已经逐步实现了很多能力：

```Plain
会话
消息
SSE
计划
工具调用
文件
Shell
浏览器
VNC
MCP
A2A
多 Agent
长期记忆
Harness
诊断
安全边界
```

​        但是能力都存在，不等于产品体验已经完整。

​        最终阶段最容易出现的问题是：

​        展开来看，第一，接口都能调通，但页面流程不顺；第二，单个工具能用，但没有进入统一时间线；第三，Harness 能跑，但没有和产品体验验收关联；第四，记忆接口存在，但没有确认是否真的进入上下文；第五，浏览器截图能返回，但 VNC 观察没有被纳入最终检查；第六，失败、停止、重试接口都在，但没有形成验收路径。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        所以本章做一件事：

```Plain
把成熟 Agent 产品的核心体验整理成一张最终验收清单。
```

​        这张清单不是替代真实测试，也不是替代人工体验。

​        它的作用是让项目最后阶段有一个统一入口，明确：

```Plain
哪些能力已经具备代码和接口证据
哪些体验必须打开页面人工确认
每一项应该怎么验证
出了问题应该看哪些接口
```

## 49.4 本章技术方案

​        本章新增 `ProductAcceptanceService`。

​        服务返回：

```Plain
ProductAcceptanceChecklist
  |
  +-- summary
  |     +-- total
  |     +-- ready
  |     +-- needs_manual_check
  |
  +-- items
        +-- natural_conversation
        +-- agent_plan_execution
        +-- streaming_timeline
        +-- tool_preview_surface
        +-- context_and_memory
        +-- multi_agent_collaboration
        +-- harness_regression
        +-- browser_vnc_observation
        +-- mcp_a2a_events
        +-- failure_recovery
        +-- compose_startup
```

​        每条验收项包含：

```Plain
key             稳定标识
title           展示标题
category        分类
status          ready 或 needs_manual_check
evidence        当前项目已有证据
verify_steps    验证步骤
related_routes  相关接口
```

​        本章新增和修改文件：

```Plain
README.md
api/README.md
ui/README.md
api/app/domain/acceptance/__init__.py
api/app/domain/acceptance/entities.py
api/app/application/product_acceptance_service.py
api/app/schemas/acceptance.py
api/app/presentation/http/routes/acceptance.py
api/app/presentation/http/router.py
api/tests/test_product_acceptance_service.py
ui/app/types.ts
ui/app/lib/acceptance-api.ts
ui/app/components/product-acceptance-panel.tsx
ui/app/components/settings-workspace.tsx
docs/course/chapters/49-product-experience-acceptance.md
```

## 49.5 实施步骤
### 49.5.1 先写产品验收测试

​        创建 `api/tests/test_product_acceptance_service.py`：

```Python
import unittest

from app.application.product_acceptance_service import ProductAcceptanceService


class ProductAcceptanceServiceTest(unittest.TestCase):
    # ===================== 第1步：最终验收清单必须覆盖成熟 Agent 产品核心体验 =====================
    def test_acceptance_items_cover_mature_agent_experience(self) -> None:
        service = ProductAcceptanceService()

        checklist = service.get_checklist()
        item_ids = {item.key for item in checklist.items}

        self.assertIn("natural_conversation", item_ids)
        self.assertIn("agent_plan_execution", item_ids)
        self.assertIn("streaming_timeline", item_ids)
        self.assertIn("tool_preview_surface", item_ids)
        self.assertIn("context_and_memory", item_ids)
        self.assertIn("multi_agent_collaboration", item_ids)
        self.assertIn("harness_regression", item_ids)
        self.assertIn("browser_vnc_observation", item_ids)
        self.assertIn("failure_recovery", item_ids)
        self.assertIn("compose_startup", item_ids)

    # ===================== 第2步：每个验收项都要给出证据、验证步骤和相关接口 =====================
    def test_every_acceptance_item_has_evidence_steps_and_routes(self) -> None:
        service = ProductAcceptanceService()

        checklist = service.get_checklist()

        for item in checklist.items:
            self.assertTrue(item.evidence)
            self.assertTrue(item.verify_steps)
            self.assertTrue(item.related_routes)
            self.assertIn(item.status, {"ready", "needs_manual_check"})

    # ===================== 第3步：汇总信息应能告诉前端有多少项已经具备自动验收证据 =====================
    def test_summary_counts_ready_and_manual_items(self) -> None:
        service = ProductAcceptanceService()

        checklist = service.get_checklist()

        self.assertEqual(checklist.summary.total, len(checklist.items))
        self.assertEqual(
            checklist.summary.ready + checklist.summary.needs_manual_check,
            checklist.summary.total,
        )
        self.assertGreater(checklist.summary.ready, 0)


if __name__ == "__main__":
    unittest.main()
```

#### 49.5.1.1 代码讲解

​        这组测试关注三件事。

​        第一，验收清单不能漏掉关键体验。

​        比如：

```Plain
自然对话
计划执行
流式时间线
工具预览
长期记忆
多 Agent
Harness
浏览器和 VNC
失败恢复
Compose 启动
```

​        第二，每条验收项必须能指导用户操作，所以必须有：

```Plain
evidence
verify_steps
related_routes
```

​        第三，前端需要展示汇总数据，所以要保证：

```Plain
ready + needs_manual_check = total
```

### 49.5.2 定义产品验收领域实体

​        创建 `api/app/domain/acceptance/__init__.py`：

```Python
"""Product acceptance domain package."""
```

​        创建 `api/app/domain/acceptance/entities.py`：

```Python
from dataclasses import dataclass


@dataclass(slots=True)
class ProductAcceptanceItem:
    """一条最终产品体验验收项。"""

    key: str
    title: str
    category: str
    status: str
    evidence: str
    verify_steps: list[str]
    related_routes: list[str]


@dataclass(slots=True)
class ProductAcceptanceSummary:
    """最终验收清单的数量汇总。"""

    total: int
    ready: int
    needs_manual_check: int


@dataclass(slots=True)
class ProductAcceptanceChecklist:
    """最终产品体验验收清单。"""

    summary: ProductAcceptanceSummary
    items: list[ProductAcceptanceItem]
```

#### 49.5.2.1 字段讲解

​        `ProductAcceptanceItem` 是单条验收项。

​        `status` 不是任务执行状态，而是验收证据状态：

```Plain
ready               已经有接口、测试或服务能力作为证据
needs_manual_check  必须打开页面观察交互体验
```

​        为什么需要 `needs_manual_check`？

​        因为 UI 体验不能全部靠接口证明。

​        例如“发送消息后页面是否自然地流式更新”，最终还是要在浏览器里观察。

### 49.5.3 实现 ProductAcceptanceService

​        创建 `api/app/application/product_acceptance_service.py`。

​        文件核心结构如下：

```Python
from app.domain.acceptance.entities import (
    ProductAcceptanceChecklist,
    ProductAcceptanceItem,
    ProductAcceptanceSummary,
)


class ProductAcceptanceService:
    """汇总最终 Agent 产品体验验收清单。

    第 49 章不再新增大型业务模块，而是把前面章节已经实现的对话、计划、
    工具、记忆、多 Agent、Harness 和沙箱能力整理成一组可执行验收项。
    """

    def get_checklist(self) -> ProductAcceptanceChecklist:
        """返回成熟 Agent 产品体验验收清单。"""

        # ===================== 第1步：整理端到端对话与执行体验 =====================
        conversation_items = [
            ProductAcceptanceItem(
                key="natural_conversation",
                title="自然对话入口",
                category="conversation",
                status="needs_manual_check",
                evidence="页面发送一条任务消息后，应自动进入规划和执行流程。",
                verify_steps=[
                    "访问 http://localhost:8088。",
                    "创建或选择一个会话。",
                    "直接输入任务并发送，不需要额外点击生成计划或执行按钮。",
                    "确认对话区出现用户消息和 Agent 运行过程。",
                ],
                related_routes=[
                    "POST /api/sessions",
                    "POST /api/sessions/{session_id}/messages/stream",
                ],
            ),
            ProductAcceptanceItem(
                key="agent_plan_execution",
                title="计划生成和步骤执行",
                category="conversation",
                status="ready",
                evidence="Agent Runner 已统一 SSE、同步执行和后台任务链路，并产生 plan_created、step_started、tool_called 等事件。",
                verify_steps=[
                    "发送一个需要多步骤执行的任务。",
                    "确认时间线出现计划步骤。",
                    "确认步骤状态从 pending/running 变为 completed 或 failed。",
                ],
                related_routes=[
                    "POST /api/sessions/{session_id}/plan",
                    "POST /api/sessions/{session_id}/plan/tasks",
                    "GET /api/sessions/{session_id}/events",
                ],
            ),
        ]
```

#### 49.5.3.1 业务讲解

​        这里不是让后端真的去自动打开浏览器验收 UI。

​        后端提供的是“验收说明书的数据结构”。

​        前端拿到这份结构后，可以展示：

​        具体来说，第一，当前要验收什么；第二，为什么认为这个能力已经具备；第三，具体怎么验证；第四，出问题时优先看哪些接口。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        继续在 `get_checklist()` 中整理工具、记忆、多 Agent、Harness 和部署项：

```Python
        tool_items = [
            ProductAcceptanceItem(
                key="tool_preview_surface",
                title="统一工具预览",
                category="tooling",
                status="needs_manual_check",
                evidence="右侧工具预览已收敛文件、Shell、浏览器、搜索、MCP、A2A 和多 Agent 结果。",
                verify_steps=[
                    "发送包含文件、搜索或浏览器动作的任务。",
                    "点击时间线中的工具调用卡片。",
                    "确认右侧抽屉或弹层展示调用参数和结果。",
                ],
                related_routes=[
                    "GET /api/sessions/{session_id}/events",
                    "GET /api/files/{file_id}/preview",
                    "GET /sandbox-api/browser/page",
                ],
            ),
            ProductAcceptanceItem(
                key="browser_vnc_observation",
                title="浏览器截图和 VNC 观察",
                category="tooling",
                status="needs_manual_check",
                evidence="BrowserTool 可打开页面和截图，VNC 面板可以观察沙箱浏览器实时画面。",
                verify_steps=[
                    "发送一个访问网页并截图的任务。",
                    "确认事件中出现 browser_open 或 browser_screenshot。",
                    "确认右侧远程桌面能看到浏览器画面。",
                ],
                related_routes=[
                    "GET /sandbox-api/browser/status",
                    "POST /sandbox-api/browser/page/navigate",
                    "GET /sandbox-api/vnc/status",
                ],
            ),
        ]
```

​        最后计算汇总：

```Python
        items = conversation_items + tool_items + reliability_items
        ready = len([item for item in items if item.status == "ready"])
        needs_manual_check = len(
            [item for item in items if item.status == "needs_manual_check"]
        )
        summary = ProductAcceptanceSummary(
            total=len(items),
            ready=ready,
            needs_manual_check=needs_manual_check,
        )
        return ProductAcceptanceChecklist(summary=summary, items=items)
```

#### 49.5.3.2 为什么不全部标记为 ready

​        有些能力可以通过接口和测试证明。

​        例如：

```Plain
Harness 用例接口
长期记忆上下文接口
MCP/A2A 工具列表接口
```

​        但有些体验必须人工确认。

​        例如：

```Plain
页面是不是自然对话
时间线是不是持续更新
VNC 画面是不是能观察浏览器
工具详情是不是好理解
```

​        所以本章保留两种状态。

### 49.5.4 新增 API Schema 和路由

​        创建 `api/app/schemas/acceptance.py`：

```Python
from pydantic import BaseModel


class ProductAcceptanceItemResponse(BaseModel):
    key: str
    title: str
    category: str
    status: str
    evidence: str
    verify_steps: list[str]
    related_routes: list[str]


class ProductAcceptanceSummaryResponse(BaseModel):
    total: int
    ready: int
    needs_manual_check: int


class ProductAcceptanceChecklistResponse(BaseModel):
    summary: ProductAcceptanceSummaryResponse
    items: list[ProductAcceptanceItemResponse]
```

​        创建 `api/app/presentation/http/routes/acceptance.py`：

```Python
from fastapi import APIRouter, Depends

from app.application.product_acceptance_service import ProductAcceptanceService
from app.domain.acceptance.entities import (
    ProductAcceptanceChecklist,
    ProductAcceptanceItem,
)
from app.schemas.acceptance import (
    ProductAcceptanceChecklistResponse,
    ProductAcceptanceItemResponse,
    ProductAcceptanceSummaryResponse,
)
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/acceptance", tags=["acceptance"])


def build_product_acceptance_service() -> ProductAcceptanceService:
    return ProductAcceptanceService()


def to_item_response(item: ProductAcceptanceItem) -> ProductAcceptanceItemResponse:
    return ProductAcceptanceItemResponse(
        key=item.key,
        title=item.title,
        category=item.category,
        status=item.status,
        evidence=item.evidence,
        verify_steps=item.verify_steps,
        related_routes=item.related_routes,
    )


def to_checklist_response(
    checklist: ProductAcceptanceChecklist,
) -> ProductAcceptanceChecklistResponse:
    return ProductAcceptanceChecklistResponse(
        summary=ProductAcceptanceSummaryResponse(
            total=checklist.summary.total,
            ready=checklist.summary.ready,
            needs_manual_check=checklist.summary.needs_manual_check,
        ),
        items=[to_item_response(item) for item in checklist.items],
    )


@router.get("/checks", response_model=ApiResponse[ProductAcceptanceChecklistResponse])
async def get_product_acceptance_checks(
    service: ProductAcceptanceService = Depends(build_product_acceptance_service),
) -> ApiResponse[ProductAcceptanceChecklistResponse]:
    # ===================== 第1步：读取最终产品体验验收清单 =====================
    checklist = service.get_checklist()

    # ===================== 第2步：转换为前端可以直接渲染的响应结构 =====================
    return ApiResponse(data=to_checklist_response(checklist))
```

​        打开 `api/app/presentation/http/router.py` 注册：

```Python
from app.presentation.http.routes import (
    a2a,
    acceptance,
    agent_core,
    ...
)

api_router.include_router(acceptance.router)
```

### 49.5.5 前端新增验收类型和 API

​        打开 `ui/app/types.ts`，新增：

```TypeScript
export type ProductAcceptanceItem = {
  key: string;
  title: string;
  category: string;
  status: "ready" | "needs_manual_check";
  evidence: string;
  verify_steps: string[];
  related_routes: string[];
};

export type ProductAcceptanceSummary = {
  total: number;
  ready: number;
  needs_manual_check: number;
};

export type ProductAcceptanceChecklistData = {
  summary: ProductAcceptanceSummary;
  items: ProductAcceptanceItem[];
};
```

​        创建 `ui/app/lib/acceptance-api.ts`：

```TypeScript
import { requestApi } from "./api";
import type { ProductAcceptanceChecklistData } from "../types";


export function fetchProductAcceptanceChecks(): Promise<ProductAcceptanceChecklistData> {
  return requestApi<ProductAcceptanceChecklistData>("/api/acceptance/checks");
}
```

### 49.5.6 新增产品体验验收面板

​        创建 `ui/app/components/product-acceptance-panel.tsx`。

​        核心代码如下：

```TypeScript
"use client";

import { CheckCircle2, ClipboardCheck, Eye, RefreshCcw } from "lucide-react";
import { useEffect, useState } from "react";

import { fetchProductAcceptanceChecks } from "../lib/acceptance-api";
import type {
  LoadState,
  ProductAcceptanceChecklistData,
  ProductAcceptanceItem,
} from "../types";


// ===================== 第1步：展示最终产品体验验收入口 =====================
export function ProductAcceptancePanel() {
  const [checklist, setChecklist] = useState<
    LoadState<ProductAcceptanceChecklistData>
  >({ type: "loading" });

  async function loadChecklist() {
    // 1. 刷新时先进入 loading，让用户知道正在读取最新验收清单。
    setChecklist({ type: "loading" });
    try {
      // 2. 从主 API 读取最终产品体验验收项。
      const data = await fetchProductAcceptanceChecks();
      setChecklist({ type: "ready", data });
    } catch (error) {
      // 3. 设置页不能因为验收接口失败而整体不可用，所以错误只显示在本面板内。
      const message = error instanceof Error ? error.message : "unknown error";
      setChecklist({ type: "error", message });
    }
  }

  useEffect(() => {
    loadChecklist();
  }, []);

  return (
    <section className="rounded-md border border-slate-200 bg-white p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="flex items-center gap-2 text-base font-semibold text-slate-950">
            <ClipboardCheck size={18} aria-hidden="true" />
            产品体验验收
          </h3>
          <p className="mt-1 text-sm leading-6 text-slate-500">
            汇总自然对话、工具预览、记忆、多 Agent、Harness 和沙箱观察的最终验收项
          </p>
        </div>
        <button
          className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
          onClick={loadChecklist}
          title="刷新验收清单"
          type="button"
        >
          <RefreshCcw size={16} aria-hidden="true" />
        </button>
      </div>

      {checklist.type === "loading" ? (
        <div className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-500">
          正在读取产品体验验收清单...
        </div>
      ) : null}

      {checklist.type === "error" ? (
        <div className="mt-4 rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
          {checklist.message}
        </div>
      ) : null}

      {checklist.type === "ready" ? (
        <ProductAcceptanceReadyView data={checklist.data} />
      ) : null}
    </section>
  );
}
```

#### 49.5.6.1 面板逻辑讲解

​        `ProductAcceptancePanel` 和第 47、48 章的诊断、安全面板一样，都使用：

```Plain
loading
error
ready
```

​        三种状态。

​        这样设置页的每个模块互不影响。

​        如果验收接口失败，只会显示本面板错误，不会让设置页其他模块一起崩掉。

### 49.5.7 接入设置页

​        打开 `ui/app/components/settings-workspace.tsx`，导入：

```TypeScript
import { ProductAcceptancePanel } from "./product-acceptance-panel";
```

​        在 `SettingsReadyView` 中加入：

```TypeScript
<MemorySettingsPanel />
<HarnessPanel />
<ProductAcceptancePanel />
<ObservabilityPanel />
<SecurityPanel />
```

#### 49.5.7.1 为什么放在设置页

​        产品体验验收不是单次对话内容。

​        它是项目最终检查入口，所以和这些面板放在一起更合适：

```Plain
Harness
产品体验验收
系统诊断
安全边界
```

## 49.6 关键理解

​        本章最重要的是理解“最终验收不是再写一堆新功能”。

​        最终验收做的是：

```Plain
确认前面功能能不能组成一个完整产品体验
```

​        第二个重点是理解自动证据和人工观察的区别。

​        接口可以证明：

```Plain
某个能力存在
某个数据能返回
某个服务能调用
```

​        但页面体验还要确认：

```Plain
用户是否只需要自然发送消息
时间线是否好理解
工具详情是否能看懂
VNC 是否真的能观察浏览器
失败和重试是否有清晰反馈
```

​        第三个重点是最终验收要可重复。

​        不要只说：

```Plain
项目看起来差不多了
```

​        而是要有：

```Plain
验收项
证据
步骤
接口
```

## 49.7 技术难点与亮点

​        技术难点：

​        换句话说，第一，很多体验无法只靠接口自动证明；第二，最终验收需要同时覆盖后端、前端、沙箱、工具、记忆和部署；第三，验收清单要能被测试，不能只是文档里的文字。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        项目亮点：

​        从实现顺序看，第一，最终体验验收进入 API 和设置页；第二，验收项覆盖对话、计划、工具、记忆、多 Agent、Harness、浏览器和部署；第三，每项都提供证据、验证步骤和相关接口；第四，为第 50 章最终交付和二次开发指南打基础。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

## 49.8 面试考点

​        放到工程语境里看，第一，为什么最终验收不能只看单个接口？；第二，Agent 产品体验验收应该覆盖哪些链路？；第三，哪些能力可以自动测试，哪些必须人工观察？；第四，为什么 Harness 不能完全替代产品体验验收？；第五，为什么工具调用需要进入统一事件流和统一预览？。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

## 49.9 运行验证

​        下面命令默认在项目根目录执行：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
```

### 49.9.1 运行第 49 章后端测试

```Bash
cd api
uv run python -m unittest tests/test_product_acceptance_service.py -v
```

​        预期看到：

```Plain
Ran 3 tests
OK
```

### 49.9.2 编译后端代码

```Bash
uv run python -m compileall app
```

​        预期没有 Python 语法错误。

### 49.9.3 检查前端类型和构建

```Bash
cd ../ui
pnpm typecheck
pnpm build
```

​        预期 TypeScript 和 Next.js 构建都通过。

### 49.9.4 Docker 构建和启动

​        本章改了 API 和 UI，建议重新构建镜像：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
BUILD=true ./scripts/start.sh
```

### 49.9.5 验收接口验证

```Bash
curl http://localhost:8088/api/acceptance/checks
```

​        预期能看到：

```Plain
natural_conversation
agent_plan_execution
streaming_timeline
tool_preview_surface
context_and_memory
multi_agent_collaboration
harness_regression
browser_vnc_observation
failure_recovery
compose_startup
```

### 49.9.6 页面验收

​        访问：

```Plain
http://localhost:8088
```

​        操作：

​        展开来看，第一，点击左侧“设置”；第二，确认出现“产品体验验收”面板；第三，确认面板顶部显示验收项总数、已有证据和人工确认数量；第四，查看每条验收项是否包含证据、验证步骤和相关接口；第五，回到“工作台”，发送一个真实任务；第六，确认对话区出现用户消息、计划、步骤、工具调用和最终结果；第七，点击工具调用卡片，确认右侧预览或弹层可以看到详情。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

## 49.10 常见问题

- 问题：`/api/acceptance/checks` 返回 404 怎么办？

​        解释：API 容器还是旧镜像。执行 `BUILD=true ./scripts/start.sh`，或者重新构建并重启 API、UI、Nginx。

- 问题：为什么有些验收项是“人工确认”？

​        解释：页面交互、流式体验、VNC 画面和工具预览的可读性必须在浏览器里观察，不能只靠接口证明。

- 问题：这个验收清单是不是替代 Harness？

​        解释：不是。Harness 更像固定任务回归测试，产品体验验收更关注最终用户链路。两者互补。

- 问题：为什么本章不继续大改前端 UI？

​        解释：本章目标是收敛和验收。如果发现体验缺口，应通过验收清单记录，然后在第 50 章二次开发指南或后续迭代继续优化。

## 49.11 本章小结

​        本章完成了成熟 Agent 产品体验验收入口：

​        具体来说，第一，新增产品验收领域实体；第二，新增 `ProductAcceptanceService`；第三，新增 `/api/acceptance/checks` 接口；第四，新增第 49 章后端测试；第五，前端设置页新增“产品体验验收”面板；第六，验收清单覆盖对话、计划、工具、记忆、多 Agent、Harness、浏览器、VNC、失败恢复和 Compose 启动。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        从这一章开始，项目具备了一张最终体验验收表。后续做二次开发时，可以先看这张表，确认改动有没有破坏核心 Agent 产品链路。

## 49.12 下一章预告

​        第 50 章会整理最终发布与二次开发指南，说明如何在当前项目基础上新增工具、扩展 MCP/A2A、调整前端预览、替换模型和继续生产化演进。
