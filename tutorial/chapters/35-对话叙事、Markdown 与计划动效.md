# 第三十五章. 对话叙事、Markdown 与计划动效

## 35.1 对话叙事流与 Markdown 代码陈列

### 35.1.1 本节目标

​        学完本节后，你将能够：

​        换句话说，第一，理解为什么 Agent 产品的主界面应该围绕“对话叙事流”组织；第二，理解普通文本渲染和 Markdown 渲染在 AI 回复中的差异；第三，使用 `react-markdown` 和 `remark-gfm` 渲染代码块、列表、链接和表格；第四，把 AI 回复和最终总结改成 Markdown 展示；第五，把步骤里的工具调用从“大按钮”收敛成轻量内联节点；第六，让主对话区更接近真实 AI Agent 产品的中间内容流。这些点放在一起看，构成了本节叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

### 35.1.2 最终效果

​        本节结束后，访问：

```Plain
http://localhost:8088
```

​        页面仍然是第 34 章的工作台，但中间对话区会发生三个变化：

​        从实现顺序看，第一，AI 回复支持 Markdown；第二，代码块会显示为独立代码区域，不再混在普通文本里；第三，计划步骤下的工具调用变成轻量节点，点击后仍然打开右侧工具详情。这些点放在一起看，构成了本节叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        本节不是最终 UI 封版。本章后文会继续把底部计划条和执行动效做得更像真实任务流，第 36 章会继续重做右侧工具详情。

### 35.1.3 本节要解决的问题

​        第 32–34 章已经把前端从功能面板逐步收敛到了 AI 工作台。

​        但还有一个很明显的问题：

```Plain
AI 对话内容看起来还是像普通文本面板。
```

​        真实 Agent 产品里，AI 回复经常包含：

```Plain
代码
命令
列表
表格
链接
小标题
执行总结
```

​        如果只用：

```TypeScript
<p className="whitespace-pre-wrap">{message.content}</p>
```

​        代码块、列表和表格都会失去结构，用户很难阅读。

​        另外，工具调用也不应该像控制台按钮一样占据很大面积。更好的方式是：

```Plain
中间时间线：轻量展示“正在搜索 / 正在执行命令 / 正在打开网页”
右侧详情：点击工具节点后查看完整参数、输出、截图或文件内容
```

​        所以本节先完成对话流的第一轮产品化对齐。

### 35.1.4 新增和修改的文件

```Plain
README.md
docs/course/coverage-matrix.md
docs/course/outline.md
docs/course/chapters/55-conversation-narrative-markdown.md
frontend/web/README.md
frontend/web/package.json
frontend/web/pnpm-lock.yaml
frontend/web/app/components/markdown-content.tsx
frontend/web/app/components/chat-workspace.tsx
frontend/web/app/components/conversation/message-bubble.tsx
frontend/web/app/components/conversation/agent-run-block.tsx
frontend/web/app/components/conversation/step-card.tsx
```

### 35.1.5 实施步骤
#### 35.1.5.1 安装 Markdown 渲染依赖

​        进入前端目录：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents/frontend/web
```

​        安装依赖：

```Bash
pnpm add react-markdown remark-gfm
```

​        安装后，`frontend/web/package.json` 会新增：

```JSON
"react-markdown": "^10.1.0",
"remark-gfm": "^4.0.1"
```

.1.5.1.1 为什么需要这两个依赖

​        `react-markdown` 负责把 Markdown 字符串转换成 React 组件。

​        `remark-gfm` 负责支持 GitHub Flavored Markdown，例如：

```Plain
表格
任务列表
删除线
自动链接
```

​        AI 回复非常容易包含代码块和列表，因此从这一阶段开始，不再把 AI 消息当普通纯文本处理。

#### 35.1.5.2 新增 MarkdownContent 组件

​        创建 `frontend/web/app/components/markdown-content.tsx`。

​        本节核心代码如下：

```TypeScript
"use client";

import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

type MarkdownContentProps = {
  className?: string;
  content: string;
};

// 中文标点紧跟 URL 时，自动链接有时会把后面的中文也吃进去。
// 这里先做一次文本归一化，让链接边界更稳定。
const cjkRanges = "\\u3000-\\u303F\\u4E00-\\u9FFF\\uFF01-\\uFF60";
const urlFollowedByCjk = new RegExp(
  `(https?:\\/\\/[^\\s${cjkRanges}]+)([${cjkRanges}])`,
  "g",
);

function normalizeAutolinks(value: string) {
  return value.replace(urlFollowedByCjk, "$1 $2");
}

const components: Components = {
  p: ({ children }) => (
    <p className="mb-3 text-base leading-8 text-zinc-400 last:mb-0">
      {children}
    </p>
  ),
  strong: ({ children }) => (
    <strong className="font-semibold text-zinc-100">{children}</strong>
  ),
  code: ({ children, className }) => {
    const value = String(children);
    const block = value.includes("\n") || className?.startsWith("language-");
    if (!block) {
      return (
        <code className="rounded-md border border-white/10 bg-white/[0.07] px-1.5 py-0.5 font-mono text-[0.9em] text-zinc-100">
          {children}
        </code>
      );
    }
    return (
      <code className="block overflow-x-auto whitespace-pre rounded-2xl border border-white/10 bg-black/45 p-4 font-mono text-sm leading-6 text-zinc-100">
        {children}
      </code>
    );
  },
  pre: ({ children }) => <pre className="my-4 overflow-x-auto">{children}</pre>,
};

export function MarkdownContent({ className = "", content }: MarkdownContentProps) {
  return (
    <div className={`break-words ${className}`}>
      <ReactMarkdown components={components} remarkPlugins={[remarkGfm]}>
        {normalizeAutolinks(content)}
      </ReactMarkdown>
    </div>
  );
}
```

.1.5.2.1 这段代码的业务作用

​        `MarkdownContent` 是 AI 回复的统一渲染入口。

​        后续只要是模型返回给用户看的内容，都优先交给它处理：

```Plain
assistant 消息
最终回答
工具总结
文件生成说明
```

​        这样做的好处是，AI 输出代码时会自然显示为代码块，而不是一段难读的普通文字。

#### 35.1.5.3 让 AI 回复使用 MarkdownContent

​        打开 `frontend/web/app/components/conversation/message-bubble.tsx`。

​        用户消息仍然用普通气泡展示，因为用户输入通常是短文本。

​        AI 消息改成：

```TypeScript
<MarkdownContent className="mt-3" content={message.content} />
```

.1.5.3.1 为什么只改 AI 消息

​        用户消息是“任务输入”，更像一条指令。

​        AI 消息是“执行解释和结果输出”，经常包含结构化内容。

​        所以本节先让 AI 消息支持 Markdown。后续如果用户上传 Markdown 片段，也可以再按需要扩展用户消息渲染。

#### 35.1.5.4 让最终总结使用 MarkdownContent

​        打开 `frontend/web/app/components/conversation/agent-run-block.tsx`。

​        原来最终回答只是按换行拆成多个段落：

```TypeScript
<FormattedAnswer value={firstAnswer} />
```

​        本节改成：

```TypeScript
<MarkdownContent content={firstAnswer} />
```

.1.5.4.1 为什么最终总结更需要 Markdown

​        最终总结通常包含：

```Plain
1. 完成了什么
2. 生成了哪些文件
3. 下一步建议
4. 可能附带代码或命令
```

​        这些内容用 Markdown 展示会更清晰。

#### 35.1.5.5 弱化步骤外壳，突出对话流

​        打开 `frontend/web/app/components/conversation/agent-run-block.tsx`。

​        本节把计划区域从厚重卡片改成更轻的折叠行：

```TypeScript
<button className="flex w-full items-center justify-between gap-4 rounded-xl px-2 py-2 text-left transition hover:bg-white/[0.035]">
```

.1.5.5.1 为什么这样改

​        主对话区应该让用户先看到：

```Plain
AI 正在做什么
每一步发生了什么
工具调用了什么
最终结果是什么
```

​        如果每个计划块都像大面板，页面会更像管理后台，而不是 AI 对话产品。

#### 35.1.5.6 把工具调用改成轻量节点

​        打开 `frontend/web/app/components/conversation/step-card.tsx`。

​        工具调用按钮从大块卡片改成轻量节点：

```TypeScript
<button className="inline-flex w-fit max-w-full items-center gap-2 rounded-lg border border-white/10 bg-white/[0.055] px-3 py-1.5 text-left text-sm font-medium text-zinc-500 transition hover:border-blue-500/40 hover:bg-blue-500/10 hover:text-zinc-100">
```

.1.5.6.1 这段代码的业务作用

​        中间对话流只展示工具摘要：

```Plain
正在搜索 ...
正在执行命令 ...
正在打开网页 ...
```

​        完整参数、输出、截图和文件内容仍然交给右侧工具详情。

​        这就是“中间轻、右侧详”的设计：

```Plain
中间：看执行过程
右侧：看工具证据
```

### 35.1.6 关键理解

​        本节最重要的是理解：Agent 产品不是把日志贴到页面上。

​        更好的展示方式是：

```Plain
用户输入任务
AI 用自然语言说明理解
计划和步骤以可折叠时间线展示
工具调用以轻量节点展示
最终结果用 Markdown 输出
```

​        这样用户可以快速读懂任务过程，也可以在需要时打开右侧详情检查证据。

### 35.1.7 运行验证

​        下面命令默认在项目根目录执行。

#### 35.1.7.1 检查前端类型

```Bash
cd frontend/web
pnpm typecheck
```

​        预期没有 TypeScript 报错。

#### 35.1.7.2 构建前端

```Bash
pnpm build
```

​        预期构建成功。

#### 35.1.7.3 Docker 验证

​        回到项目根目录：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
docker compose build ui
docker compose up -d --force-recreate ui nginx
```

​        访问：

```Plain
http://localhost:8088
```

​        创建或选择会话后，发送一条包含代码需求的任务，例如：

```Plain
帮我写一个 Python 函数，计算列表中所有偶数的和，并解释代码。
```

​        预期：

​        放到工程语境里看，第一，AI 回复中的代码块有独立背景；第二，列表和加粗能正常显示；第三，计划步骤下的工具调用更轻量；第四，点击工具节点仍然能打开右侧详情。这些点放在一起看，构成了本节叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

### 35.1.8 小结

​        本节完成了对话流产品化的第一步：

​        展开来看，第一，安装了 Markdown 渲染依赖；第二，新增了 `MarkdownContent`；第三，AI 回复和最终总结开始支持 Markdown；第四，工具调用从大按钮收敛为轻量节点；第五，主对话区宽度继续向中间叙事流靠拢。这些点放在一起看，构成了本节叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        本章后文会继续处理底部计划折叠条和执行流动效，让任务执行过程更像连续的 AI 工作流。

## 35.2 任务计划折叠条与执行流动效

### 35.2.1 本节目标

​        学完本节后，你将能够：

​        具体来说，第一，理解为什么计划进度适合放在输入框上方；第二，把计划步骤转换成前端 `PlanProgressView`；第三，新增可折叠的底部任务计划条；第四，让中间对话流减少大面板感，专注展示 AI 说明、步骤和工具节点；第五，根据 `plan_created`、`step_started`、`step_completed`、`task_error` 等事件计算当前步骤；第六，理解“中间讲过程，底部看进度，右侧看证据”的前端分工。这些点放在一起看，构成了本节叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

### 35.2.2 最终效果

​        本节结束后，访问：

```Plain
http://localhost:8088
```

​        发送任务并生成计划后，底部输入框上方会出现任务计划折叠条：

```Plain
当前步骤标题               1 / 3
```

​        点击折叠条可以展开完整步骤列表。

​        中间对话区不再重复展示厚重的计划标题卡片，而是更专注展示：

​        换句话说，第一，AI 对任务的说明；第二，步骤执行流；第三，轻量工具节点；第四，最终总结。这些点放在一起看，构成了本节叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

### 35.2.3 本节要解决的问题

​        前文已经让 AI 回复支持 Markdown，也把工具调用节点变轻了。

​        但还有一个问题：

```Plain
计划既在中间展示，又需要在底部输入区附近持续可见。
```

​        用户真正执行长任务时，会不断关注两个问题：

```Plain
现在做到哪一步了？
总共有几步？
```

​        如果计划只在中间时间线里，用户滚动到后面时就看不到整体进度。

​        所以本节把计划进度放到底部输入区上方。

​        这样页面分工更清晰：

```Plain
中间对话流：讲发生了什么
底部计划条：看当前进度
右侧工作区：看工具证据
```

### 35.2.4 新增和修改的文件

```Plain
README.md
docs/course/chapters/56-plan-progress-streaming.md
frontend/web/README.md
frontend/web/app/components/chat-workspace.tsx
frontend/web/app/components/conversation-timeline.tsx
frontend/web/app/components/conversation/agent-run-block.tsx
frontend/web/app/components/conversation/plan-progress-bar.tsx
frontend/web/app/components/conversation/types.ts
frontend/web/app/components/conversation/view-model.ts
```

### 35.2.5 实施步骤
#### 35.2.5.1 扩展前端计划进度类型

​        打开 `frontend/web/app/components/conversation/types.ts`，新增：

```TypeScript
export type PlanProgressView = {
  activeStep: StepView | null;
  completedCount: number;
  expandedByDefault: boolean;
  failed: boolean;
  running: boolean;
  steps: StepView[];
  title: string;
  totalCount: number;
};
```

.2.5.1.1 字段含义

​        从实现顺序看，第一，`activeStep`：当前正在执行或即将执行的步骤；第二，`completedCount`：已完成步骤数量；第三，`totalCount`：总步骤数量；第四，`expandedByDefault`：任务运行时是否默认展开计划条；第五，`failed`：任务是否已经失败；第六，`running`：任务是否正在规划或执行；第七，`steps`：完整步骤列表，用于展开后展示；第八，`title`：计划标题。这些点放在一起看，构成了本节叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

.2.5.1.2 为什么这样设计

​        底部计划条不应该直接读取原始事件。

​        原始事件适合做数据来源，但组件需要的是更稳定的展示模型：

```Plain
当前步骤
进度数字
是否运行中
是否失败
完整步骤列表
```

​        所以先定义 `PlanProgressView`，再让组件只关心这个结构。

#### 35.2.5.2 从事件生成计划进度模型

​        打开 `frontend/web/app/components/conversation/view-model.ts`，新增：

```TypeScript
export function buildPlanProgressView(
  plan: AgentPlan | null,
  events: SessionEventItem[],
  planning: boolean,
  executing: boolean,
): PlanProgressView | null {
  if (!plan) {
    return null;
  }

  const steps = buildStepViews(plan, events);
  const completedCount = steps.filter((step) => step.status === "completed").length;
  const failed = Boolean(events.find((event) => event.type === "task_error"));
  const runningStep = steps.find((step) => step.status === "running") ?? null;
  const pendingStep = steps.find((step) => step.status === "pending") ?? null;
  const activeStep = failed ? null : runningStep ?? pendingStep;
  const running = planning || executing || Boolean(runningStep);

  return {
    activeStep,
    completedCount,
    expandedByDefault: running,
    failed,
    running,
    steps,
    title: plan.title || "任务执行计划",
    totalCount: steps.length,
  };
}
```

.2.5.2.1 这段代码的业务流程

​        这段函数把后端事件转换成底部计划条需要的数据。

​        流程是：

```Plain
拿到计划 plan
  |
  v
用 buildStepViews() 计算每个步骤状态
  |
  v
统计 completedCount
  |
  v
找到 runningStep 或 pendingStep
  |
  v
生成 PlanProgressView
```

.2.5.2.2 为什么使用 runningStep 和 pendingStep

​        如果某一步已经开始，就展示它。

​        如果还没有步骤开始，就展示第一个待执行步骤。

​        如果任务失败，就不再展示 activeStep，而是让计划条显示失败状态。

#### 35.2.5.3 新增 PlanProgressBar 组件

​        创建 `frontend/web/app/components/conversation/plan-progress-bar.tsx`。

​        核心结构如下：

```TypeScript
"use client";

import { Check, ChevronDown, ChevronUp, Clock3, Loader2, XCircle } from "lucide-react";
import { useEffect, useState } from "react";

import type { PlanProgressView } from "./types";

type PlanProgressBarProps = {
  progress: PlanProgressView | null;
};

export function PlanProgressBar({ progress }: PlanProgressBarProps) {
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (progress?.expandedByDefault) {
      setExpanded(true);
    }
  }, [progress?.expandedByDefault, progress?.title]);

  if (!progress || progress.totalCount === 0) {
    return null;
  }

  const activeTitle =
    progress.activeStep?.title ||
    progress.activeStep?.description ||
    (progress.failed ? "任务执行失败" : "任务已完成");

  return (
    <div className="mb-3 overflow-hidden rounded-2xl border border-white/10 bg-[#111421]/92">
      <button
        aria-expanded={expanded}
        onClick={() => setExpanded((value) => !value)}
        type="button"
      >
        <span>{activeTitle}</span>
        <span>{progress.completedCount} / {progress.totalCount}</span>
      </button>
      {expanded ? (
        <div>
          {progress.steps.map((step, index) => (
            <div key={step.id}>
              {index + 1}. {step.title}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
```

.2.5.3.1 这段代码的业务作用

​        `PlanProgressBar` 是底部计划条。

​        它负责两种状态：

```Plain
折叠：展示当前步骤 + 进度数字
展开：展示完整步骤列表
```

​        任务运行时，`expandedByDefault` 会让它自动展开。这样用户发送任务后，能立刻看到任务被拆成了哪些步骤。

#### 35.2.5.4 把计划条接入输入区

​        打开 `frontend/web/app/components/chat-workspace.tsx`，先构建进度模型：

```TypeScript
const eventItems = events.type === "ready" ? events.data : [];
const planProgress = buildPlanProgressView(
  plan,
  eventItems,
  planning,
  executingPlan,
);
```

​        再把计划条放到输入框上方：

```TypeScript
<PlanProgressBar progress={planProgress} />
```

.2.5.4.1 为什么放在输入框上方

​        输入区是用户持续关注的位置。

​        任务运行时，用户经常会看底部：

```Plain
还能不能输入？
任务能不能停止？
当前执行到哪一步？
```

​        把计划条放在输入框上方，可以让这些信息聚在一起。

#### 35.2.5.5 调整中间时间线

​        打开 `frontend/web/app/components/conversation-timeline.tsx`。

​        本节不再让 `plan_created` 事件在中间生成一块厚重的计划卡。

​        中间时间线保留：

```Plain
用户消息
AI 回复
步骤执行流
工具节点
最终总结
```

.2.5.5.1 为什么这样调整

​        计划进度已经在底部持续可见。

​        中间区域如果再重复展示完整计划，会让页面显得像控制台。

​        更好的体验是：

```Plain
底部看总体进度
中间看过程细节
```

#### 35.2.5.6 弱化 AgentRunBlock 的计划标题卡

​        打开 `frontend/web/app/components/conversation/agent-run-block.tsx`。

​        原来这里有一个可折叠的计划标题卡。

​        本节改成更轻的说明：

```TypeScript
<p className="mt-3 text-base leading-8 text-zinc-400">
  我会按“{plan.title}”推进任务。执行过程中会持续展示步骤进度、
  工具调用和最终结果，点击工具节点可以查看右侧详情。
</p>
```

​        然后直接展示步骤流。

.2.5.6.1 这样改后的效果

​        中间对话区更像：

```Plain
AtlasAgent：我会按计划推进任务
  - 步骤 1
    - 工具节点
  - 步骤 2
    - 工具节点
最终回答
```

​        而不是：

```Plain
大计划卡
大步骤卡
大工具按钮
```

### 35.2.6 关键理解

​        本节最重要的是前端信息分层。

​        不要把所有信息都塞进同一个区域。

```Plain
中间对话流：解释和过程
底部计划条：进度和当前步骤
右侧工作区：工具调用证据
```

​        这样用户既能快速知道任务进展，也能在需要时展开细节。

### 35.2.7 运行验证

​        下面命令默认在项目根目录执行。

#### 35.2.7.1 检查前端类型

```Bash
cd frontend/web
pnpm typecheck
```

​        预期没有 TypeScript 报错。

#### 35.2.7.2 构建前端

```Bash
pnpm build
```

​        预期构建成功。

#### 35.2.7.3 Docker 构建和启动

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
docker compose build ui
docker compose up -d --force-recreate ui nginx
```

#### 35.2.7.4 页面验证

​        访问：

```Plain
http://localhost:8088
```

​        创建或选择会话，发送一个需要多步骤执行的任务。

​        预期：

​        放到工程语境里看，第一，底部输入框上方出现计划进度条；第二，折叠状态显示当前步骤和 `已完成 / 总数`；第三，点击计划条可以展开完整步骤列表；第四，中间对话区不再重复显示厚重计划标题卡；第五，步骤流和工具节点仍然可以打开右侧详情。这些点放在一起看，构成了本节叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

### 35.2.8 小结

​        本节完成了任务进度体验的进一步收敛：

​        展开来看，第一，新增 `PlanProgressView`；第二，新增 `buildPlanProgressView()`；第三，新增底部 `PlanProgressBar`；第四，把计划进度放到输入框上方；第五，中间对话流去掉厚重计划标题卡；第六，页面更接近连续任务执行体验。这些点放在一起看，构成了本节叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        下一章会继续把右侧工具详情、浏览器截图、VNC 和文件预览做最终对齐。

## 35.3 本章小结

​        完成“对话叙事流与 Markdown 代码陈列”和“任务计划折叠条与执行流动效”两个阶段后，这条能力链已经形成闭环。读者仍然可以在每个阶段结束时单独运行验证，但理解上应把两者视作一个连续决策：先建立可靠边界，再让上层能力真正依赖它。

---

[← 第三十四章. 工具工作区、响应式与可访问性](34-工具工作区、响应式与可访问性.md) · [返回目录](../README.md) · [第三十六章. 工具详情、浏览器观察与搜索稳定性 →](36-工具详情、浏览器观察与搜索稳定性.md)
