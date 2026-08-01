# 第五十三章. 工具预览、浏览器 VNC 与文件工作区细琢

## 53.1 本章目标

​        学完本章后，你将能够：

​        换句话说，第一，理解右侧工具工作区在 AI Agent 产品中的作用；第二，把工具输出从“能显示”整理成“按类型可读”；第三，为工具调用增加类型标签、复制输出和结构化摘要；第四，让 Shell 输出使用等宽字体、长文本滚动和错误高亮；第五，让浏览器工具预览和 VNC 远程桌面联动；第六，统一文件预览和工具预览的视觉风格；第七，保持工具事件、文件预览、VNC 状态和对话时间线之间的职责边界。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

## 53.2 最终效果

​        本章结束后，访问：

```Plain
http://localhost:8088
```

​        发送任务并点击对话流中的工具卡片，右侧工作区会按工具类型展示内容：

```Plain
搜索工具     -> 搜索关键词、来源、标题、摘要、链接
Shell 工具   -> 等宽输出、退出码提示、错误高亮、复制按钮
浏览器工具   -> 页面信息或截图；如果是浏览器工具，还会显示 VNC 远程桌面
MCP 工具     -> server、tool、arguments、content
A2A 工具     -> 远程 Agent、任务 ID、协作步骤、输出消息
多 Agent     -> Manager、子任务、Reviewer、最终结论
文件预览     -> 暗色工作区、刷新、展开预览
```

​        右侧工作区不再只是把 JSON 或文本粗暴丢出来，而是尽量把工具结果整理成可读卡片。

## 53.3 本章要解决的问题

​        第 52 章已经把中间对话区的执行节奏打磨得更清楚。

​        现在还剩一个明显问题：右侧工具工作区的可读性不够统一。

​        工具结果来源很多：

```Plain
SearchTool
ShellTool
BrowserTool
FileTool
MCP Tool
A2A Tool
Multi-Agent Tool
VNC Remote Desktop
```

​        这些工具的输出形态完全不一样。

​        如果前端只用一个 `<pre>` 展示所有内容，会出现几个问题：

​        从实现顺序看，第一，搜索结果看不出标题、摘要和链接层级；第二，Shell 输出没有等宽字体和错误提示；第三，浏览器截图和 VNC 是分开的，观察链路不完整；第四，多 Agent 协作结果没有角色、子任务、评审层次；第五，文件预览视觉风格和暗色工作台不一致。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        所以本章继续打磨右侧工作区。

## 53.4 本章技术方案

​        本章不改后端工具协议。

​        后端工具调用仍然写入：

```Plain
session_events.type = tool_called
session_events.payload.tool_name
session_events.payload.arguments
session_events.payload.output
```

​        前端在 `ToolPreviewPanel` 中做分流：

```Plain
tool_called event
  |
  v
读取 tool_name 和 output
  |
  +-- JSON kind=browser_screenshot -> 截图预览
  +-- JSON kind=search_results     -> 搜索结果卡片
  +-- JSON kind=mcp_tool_result    -> MCP 结果卡片
  +-- JSON kind=a2a_task_result    -> A2A 结果卡片
  +-- JSON kind=multi_agent_result -> 多 Agent 结果卡片
  +-- tool_name=shell_*            -> Shell 输出卡片
  +-- tool_name=browser_*          -> 浏览器普通输出 + VNC
  +-- fallback                     -> 普通工具输出
```

​        本章主要修改：

```Plain
ui/app/components/tool-preview-panel.tsx
ui/app/components/file-preview-panel.tsx
ui/app/components/vnc-panel.tsx
ui/app/components/chat-workspace.tsx
ui/README.md
README.md
docs/course/coverage-matrix.md
```

​        本章暂时不做这些内容：

​        放到工程语境里看，第一，不新增后端工具；第二，不改 SSE 协议；第三，不做工具结果持久化文件下载；第四，不做完整移动端验收，第 54 章会处理；第五，不把 VNC 做成可拖拽浮窗。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

## 53.5 新增和修改的文件

```Plain
README.md
docs/course/coverage-matrix.md
docs/course/chapters/53-tool-workspace-polish.md
ui/README.md
ui/app/components/chat-workspace.tsx
ui/app/components/file-preview-panel.tsx
ui/app/components/tool-preview-panel.tsx
ui/app/components/vnc-panel.tsx
```

## 53.6 实施步骤
### 53.6.1 给工具预览增加类型标签和复制按钮

​        打开 `ui/app/components/tool-preview-panel.tsx`。

​        先新增图标导入：

```TypeScript
import {
  Check,
  Clipboard,
} from "lucide-react";
```

​        继续新增 `CopyButton`：

```TypeScript
function CopyButton({
  tone = "dark",
  value,
}: {
  tone?: "dark" | "light";
  value: string;
}) {
  const [copied, setCopied] = useState(false);

  async function copyValue() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      setCopied(false);
    }
  }

  return (
    <button
      className={
        tone === "light"
          ? "inline-flex h-9 items-center gap-1 rounded-md border border-slate-200 px-3 text-xs font-medium text-slate-600 hover:bg-slate-50"
          : "inline-flex h-8 items-center gap-1 rounded-full border border-white/10 bg-white/[0.04] px-3 text-xs font-medium text-zinc-400 hover:text-zinc-50"
      }
      onClick={copyValue}
      title="复制工具输出"
      type="button"
    >
      {copied ? (
        <Check size={14} aria-hidden="true" />
      ) : (
        <Clipboard size={14} aria-hidden="true" />
      )}
      {copied ? "已复制" : "复制"}
    </button>
  );
}
```

​        再新增工具类型标签：

```TypeScript
function ToolKindBadge({
  kind,
  tone = "dark",
}: {
  kind: string;
  tone?: "dark" | "light";
}) {
  const className =
    tone === "light"
      ? "rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] font-semibold text-slate-600"
      : "rounded-full border border-blue-500/25 bg-blue-500/10 px-2 py-0.5 text-[11px] font-semibold text-blue-200";
  return <span className={className}>{kind}</span>;
}
```

#### 53.6.1.1 代码讲解

​        `CopyButton` 的业务职责很小：

```Plain
接收字符串
  |
  v
写入浏览器剪贴板
  |
  v
短暂显示“已复制”
```

​        这里没有把复制状态放进 zustand。

​        原因是复制状态只属于这个按钮本身，不需要被其他组件共享。

​        `tone` 用来兼容两种场景：

​        展开来看，第一，`dark`：右侧暗色工具工作区；第二，`light`：展开详情弹层的浅色头部。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        `ToolKindBadge` 用来让用户快速知道当前结果是什么类型。

​        例如：

```Plain
Search
Shell
Browser
MCP
A2A
Multi-Agent
```

### 53.6.2 根据工具名和输出判断工具类型

​        继续在 `tool-preview-panel.tsx` 中新增：

```TypeScript
function getToolKind(toolName: string, output: string) {
  if (parseScreenshot(output)) {
    return "Browser Screenshot";
  }
  if (parseSearchResults(output) || toolName.startsWith("search_")) {
    return "Search";
  }
  if (parseMcpToolResult(output) || toolName.startsWith("mcp_")) {
    return "MCP";
  }
  if (parseA2aTaskResult(output) || toolName.startsWith("a2a_")) {
    return "A2A";
  }
  if (parseMultiAgentResult(output) || toolName.startsWith("multi_agent_")) {
    return "Multi-Agent";
  }
  if (toolName.startsWith("browser_")) {
    return "Browser";
  }
  if (toolName.startsWith("shell_")) {
    return "Shell";
  }
  if (toolName.startsWith("file_")) {
    return "File";
  }
  return "Tool";
}
```

#### 53.6.2.1 为什么同时看 output 和 toolName

​        有些工具输出是结构化 JSON。

​        例如截图：

```JSON
{"kind":"browser_screenshot","mime_type":"image/png","base64_data":"..."}
```

​        这种情况最可靠的判断方式是 `kind`。

​        但 Shell 工具目前输出的是普通文本：

```Plain
会话：...
命令：...
状态：...
退出码：...
```

​        它没有 JSON `kind`，所以要看 `toolName`：

```TypeScript
toolName.startsWith("shell_")
```

​        这种“双通道判断”可以兼容当前后端，也给未来结构化输出留空间。

### 53.6.3 让工具详情头部显示类型和复制按钮

​        在 `ToolCallDetail` 中，先取出工具类型：

```TypeScript
const previewKind = getToolKind(toolName, output);
```

​        头部右侧增加：

```TypeScript
<ToolKindBadge kind={previewKind} />
<CopyButton value={output || JSON.stringify(event.payload, null, 2)} />
```

​        展开弹层里也增加浅色版本：

```TypeScript
<ToolKindBadge kind={previewKind} tone="light" />
<CopyButton
  value={output || JSON.stringify(event.payload, null, 2)}
  tone="light"
/>
```

#### 53.6.3.1 这段代码的业务流程

​        用户点击中间时间线的工具节点后：

```Plain
右侧打开 ToolPreviewPanel
  |
  v
读取 selectedToolEventId 对应事件
  |
  v
显示工具名、类型标签、时间、复制按钮
  |
  v
按工具类型渲染内容
```

​        复制按钮优先复制工具输出。

​        如果工具没有输出，就复制完整事件 payload，方便排查。

### 53.6.4 新增普通工具输出和 Shell 输出组件

​        新增普通文本工具输出：

```TypeScript
function PlainToolPreview({
  output,
  title,
}: {
  output: string;
  title: string;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-black/30">
      <div className="border-b border-white/10 px-3 py-2 text-xs font-semibold text-zinc-400">
        {title}
      </div>
      <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words p-4 text-xs leading-5 text-zinc-200">
        {output || "<no output>"}
      </pre>
    </div>
  );
}
```

​        新增 Shell 专用输出：

```TypeScript
function ShellOutputPreview({ output }: { output: string }) {
  const failed = /退出码：([1-9]\d*)/.test(output) || /状态：(failed|error)/i.test(output);
  return (
    <div
      className={`rounded-xl border ${
        failed
          ? "border-rose-500/30 bg-rose-500/10"
          : "border-emerald-500/20 bg-emerald-500/[0.06]"
      }`}
    >
      <div className="flex items-center justify-between gap-3 border-b border-white/10 px-3 py-2">
        <div className="flex items-center gap-2 text-xs font-semibold text-zinc-200">
          <Terminal
            className={failed ? "text-rose-300" : "text-emerald-300"}
            size={15}
            aria-hidden="true"
          />
          Shell 输出
        </div>
        <span
          className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${
            failed ? "bg-rose-500/15 text-rose-200" : "bg-emerald-500/15 text-emerald-200"
          }`}
        >
          {failed ? "error" : "ok"}
        </span>
      </div>
      <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words p-4 font-mono text-xs leading-6 text-zinc-100">
        {output || "<no output>"}
      </pre>
    </div>
  );
}
```

​        渲染分支改成：

```TypeScript
{screenshot ? (
  <ScreenshotPreview screenshot={screenshot} />
) : searchResults ? (
  <SearchResultsPreview results={searchResults} />
) : mcpResult ? (
  <McpResultPreview result={mcpResult} />
) : a2aResult ? (
  <A2aResultPreview result={a2aResult} />
) : multiAgentResult ? (
  <MultiAgentResultPreview result={multiAgentResult} />
) : toolName.startsWith("shell_") ? (
  <ShellOutputPreview output={output} />
) : toolName.startsWith("browser_") ? (
  <PlainToolPreview output={output} title="浏览器工具输出" />
) : (
  <PlainToolPreview output={output} title="工具输出" />
)}
```

#### 53.6.4.1 为什么 Shell 要单独处理

​        Shell 输出有两个特点。

​        第一，它需要等宽字体。

​        命令输出经常包含目录树、日志、表格、错误堆栈。如果用普通字体，很难看齐。

​        第二，它需要错误高亮。

​        课程里的 Shell 工具输出已经包含：

```Plain
退出码：0
```

​        或者：

```Plain
退出码：1
```

​        前端可以从文本里判断是否失败，然后给出绿色或红色状态。

### 53.6.5 浏览器工具联动 VNC

​        打开 `ui/app/components/tool-preview-panel.tsx`，引入：

```TypeScript
import type { LoadState, SessionEventItem, VncStatusData } from "../types";
import { VncPanel } from "./vnc-panel";
```

​        扩展 props：

```TypeScript
type ToolPreviewPanelProps = {
  events: LoadState<SessionEventItem[]>;
  onClose: () => void;
  onRefreshVnc: () => void;
  selectedToolEventId: string | null;
  vnc: LoadState<VncStatusData>;
};
```

​        在 `ToolCallView` 中，如果选中的是浏览器工具，就显示远程桌面：

```TypeScript
{getString(latestToolEvent.payload.tool_name).startsWith("browser_") ? (
  <VncPanel onRefresh={onRefreshVnc} state={vnc} />
) : null}
```

​        打开 `ui/app/components/chat-workspace.tsx`，把 VNC 状态传进去：

```TypeScript
<ToolPreviewPanel
  events={events}
  onClose={() => setSelectedToolEventId(null)}
  onRefreshVnc={onRefreshVnc}
  selectedToolEventId={selectedToolEventId}
  vnc={vnc}
/>
```

#### 53.6.5.1 这段代码的业务流程

​        用户点击浏览器工具节点：

```Plain
browser_open / browser_screenshot
  |
  v
右侧 ToolPreviewPanel 打开
  |
  v
显示工具输出或截图
  |
  v
同时显示 VNCPanel
```

​        这样浏览器工具的“结果”和“实时画面”在同一个工作区里。

​        用户不需要到别的区域找远程桌面。

### 53.6.6 统一文件预览的暗色工作区

​        打开 `ui/app/components/file-preview-panel.tsx`。

​        把外层白色卡片改成暗色工具工作区：

```TypeScript
<div className="overflow-hidden rounded-[24px] border border-white/10 bg-[#08090d] shadow-2xl shadow-black/50">
```

​        头部增加分区标识：

```TypeScript
<div className="mb-1 text-xs font-medium uppercase tracking-[0.18em] text-zinc-600">
  File Preview
</div>
```

​        内容预览使用等宽块：

```TypeScript
<pre className="whitespace-pre-wrap break-words rounded-2xl border border-white/10 bg-black/30 p-4 text-xs leading-5 text-zinc-200">
  {preview.data.content}
  {preview.data.truncated ? "\n\n预览已裁剪，可在文件服务中查看完整内容。" : ""}
</pre>
```

#### 53.6.6.1 为什么文件预览也要统一

​        文件预览虽然不是 `tool_called` 事件，但它也是右侧工作区的一部分。

​        如果工具预览是暗色沉浸式，文件预览是白底管理后台风格，用户会感觉像进入了两个系统。

​        本章把它们统一成同一个工作台视觉语言。

### 53.6.7 统一 VNC 面板视觉

​        打开 `ui/app/components/vnc-panel.tsx`。

​        把外层改成：

```TypeScript
<div className="rounded-[24px] border border-white/10 bg-[#08090d] p-5 shadow-2xl shadow-black/50">
```

​        把状态卡片改成暗色状态：

```TypeScript
<div className="flex items-center gap-2 rounded-2xl border border-emerald-500/25 bg-emerald-500/10 p-3 text-sm text-emerald-200">
  <Monitor size={16} />
  <span>{getConnectionText(connectionState, data.message)}</span>
</div>
```

​        远程桌面容器：

```TypeScript
<div className="h-[260px] overflow-hidden rounded-2xl border border-white/10 bg-black">
  <div className="h-full w-full" ref={screenRef} />
</div>
```

#### 53.6.7.1 为什么 VNC 要放进工具工作区

​        截图回答的是：

```Plain
某一刻页面是什么样
```

​        VNC 回答的是：

```Plain
浏览器现在正在发生什么
```

​        当 Agent 执行浏览器任务时，两者应该在同一个观察区里出现。

## 53.7 关键理解

​        本章最重要的是“统一入口，不统一内容”。

​        右侧工具工作区要统一：

```Plain
标题
关闭
复制
展开
最近工具调用
基础视觉风格
```

​        但不同工具的内容不能强行统一。

```Plain
搜索结果要像搜索结果
Shell 输出要像终端
截图要像图片
多 Agent 要像协作记录
文件要像文件预览
VNC 要像远程桌面
```

​        第二个重点是不要为了前端好看就随便改后端协议。

​        本章先在前端兼容当前协议：

​        具体来说，第一，JSON `kind` 能解析就结构化展示；第二，没有 JSON 的 Shell 输出就按工具名展示；第三，解析不了就回退普通文本。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        这样不会破坏已有工具。

​        第三个重点是工具工作区服务于真实对话。

​        本章没有新增孤立演示页。所有入口仍然来自：

```Plain
发送任务 -> 工具调用 -> 点击工具卡片 -> 右侧工作区
```

## 53.8 技术难点与亮点

​        技术难点：

​        换句话说，第一，工具输出格式不同，不能只靠一种组件展示；第二，Shell 输出是普通文本，需要前端识别退出码；第三，浏览器截图和 VNC 来自不同数据源，需要在同一工作区组合；第四，文件预览不是工具事件，但视觉上要和工具工作区一致；第五，复制按钮要处理浏览器权限失败。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        项目亮点：

​        从实现顺序看，第一，右侧工具工作区更接近成熟 Agent 产品的观察面板；第二，工具输出可以复制，方便调试和复盘；第三，Shell 输出有等宽字体、滚动区域和错误高亮；第四，浏览器工具结果可以联动 VNC 远程桌面；第五，文件预览和工具预览视觉统一。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

## 53.9 面试考点

​        放到工程语境里看，第一，为什么工具结果需要按类型渲染，而不是统一 `<pre>`？；第二，前端如何兼容结构化 JSON 输出和普通文本输出？；第三，为什么 Shell 输出适合使用等宽字体？；第四，浏览器截图和 VNC 的产品价值有什么区别？；第五，工具工作区为什么应该从对话流里的工具卡片打开？。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

## 53.10 运行验证

​        下面命令默认在项目根目录执行：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
```

### 53.10.1 检查前端类型

```Bash
cd ui
pnpm typecheck
```

​        预期没有 TypeScript 报错。

### 53.10.2 构建前端

```Bash
pnpm build
```

​        预期构建成功。

### 53.10.3 检查后端测试

```Bash
cd /Users/atlas/Desktop/github/atlas-agents/api
uv run python -m unittest discover -s tests -v
```

​        预期测试通过。

### 53.10.4 Docker 构建和启动

​        本章改的是 UI，建议重新构建 UI 镜像：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
docker compose build ui
docker compose up -d --force-recreate ui nginx
```

​        如果想完整验证所有服务：

```Bash
BUILD=true ./scripts/start.sh
```

### 53.10.5 页面验证

​        访问：

```Plain
http://localhost:8088
```

​        操作：

​        展开来看，第一，创建或选择一个会话；第二，发送包含搜索、Shell、浏览器或多 Agent 关键词的任务；第三，等工具卡片出现在中间时间线；第四，点击工具卡片；第五，确认右侧工具工作区打开；第六，确认顶部显示工具类型标签和复制按钮；第七，如果是搜索工具，确认能看到标题、摘要、链接和来源；第八，如果是 Shell 工具，确认输出是等宽字体，并能根据退出码显示 `ok` 或 `error`；第九，如果是浏览器工具，确认右侧能看到浏览器输出和 VNC 远程桌面区域；第十，点击“展开详情”，确认弹层能查看更大的结果；第十一，点击文件附件，确认文件预览也使用暗色工作区风格。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

## 53.11 常见问题

- 问题：复制按钮没有反应怎么办？

​        解释：浏览器剪贴板 API 需要安全上下文。本地 `localhost` 通常可用。如果浏览器权限被禁用，按钮不会让页面崩溃，只是不会进入“已复制”状态。

- 问题：Shell 输出没有显示错误高亮怎么办？

​        解释：当前前端根据 `退出码：非 0` 或 `状态：failed/error` 判断失败。如果后端 Shell 输出格式变化，需要同步调整正则。

- 问题：浏览器工具下没有 VNC 面板怎么办？

​        解释：只有工具名以 `browser_` 开头时才显示 VNC。先确认中间时间线选中的工具是 `browser_open`、`browser_screenshot` 或其他浏览器工具。

- 问题：VNC 黑屏怎么办？

​        解释：优先检查 Sandbox 是否健康，以及第 28 章的 Xvfb、x11vnc、websockify 是否启动。可以执行 `curl http://localhost:8088/sandbox-api/vnc/status`。

- 问题：为什么不把所有工具输出都改成 JSON？

​        解释：这是可以继续优化的方向，但本章目标是前端工作区打磨。先兼容当前协议，避免为了 UI 改动影响已有工具链。

## 53.12 本章小结

​        本章完成了右侧工具工作区的产品化打磨：

​        具体来说，第一，工具详情增加类型标签和复制按钮；第二，普通工具输出进入统一暗色预览框；第三，Shell 输出使用等宽字体、滚动和错误高亮；第四，浏览器工具预览联动 VNC 远程桌面；第五，文件预览改成暗色工作区风格；第六，VNC 面板视觉和右侧工作区统一。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        从这一章开始，用户不只是能看到工具结果，还能更容易理解每次工具调用做了什么、是否成功、结果在哪里继续查看。

## 53.13 下一章预告

​        第 54 章会做前端响应式、可访问性和视觉最终验收，确保桌面端、窄屏、长任务和键盘操作场景都能正常使用。
