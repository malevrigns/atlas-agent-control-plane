import {
  Bot,
  Camera,
  Check,
  Clipboard,
  FileText,
  FolderOpen,
  GitBranch,
  Globe,
  Hammer,
  Monitor,
  Maximize2,
  Network,
  Plug,
  RefreshCcw,
  Search,
  Terminal,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { formatDateTime } from "../lib/format";
import type { LoadState, SessionEventItem, VncStatusData } from "../types";
import { buildToolObservation } from "./conversation/view-model";
import type { StepView } from "./conversation/types";
import { VncPanel } from "./vnc-panel";

type ToolPreviewPanelProps = {
  events: LoadState<SessionEventItem[]>; // 会话事件列表，用来定位当前点击的工具调用。
  onClose: () => void; // 关闭右侧工具详情抽屉。
  onRefreshVnc: () => void; // 刷新 Sandbox VNC 状态。
  selectedToolEventId: string | null; // 中间对话流里选中的工具调用事件。
  vnc: LoadState<VncStatusData>; // 远程桌面状态，浏览器工具预览会复用它。
};

type ScreenshotPayload = {
  kind: "browser_screenshot";
  mime_type: string;
  base64_data: string;
  size: number;
};

type SearchResultsPayload = {
  kind: "search_results";
  provider: string;
  query: string;
  items: Array<{
    title: string;
    url: string;
    snippet: string;
  }>;
};

type SearchErrorPayload = {
  kind: "search_error";
  provider: string;
  query: string;
  message: string;
  items: [];
};

type McpToolResultPayload = {
  kind: "mcp_tool_result";
  server_name: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  content: Array<Record<string, unknown>>;
};

type A2aTaskResultPayload = {
  kind: "a2a_task_result";
  agent_key: string;
  remote_agent: string;
  task_id: string;
  status: string;
  input_message: Array<{ kind: string; text: string }>;
  output_message: Array<{ kind: string; text: string }>;
  steps: Array<{ index: number; action: string; detail: string }>;
};

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

// ===================== 第1步：统一展示工具调用、文件和沙箱观察 =====================
export function ToolPreviewPanel({
  events,
  onClose,
  onRefreshVnc,
  selectedToolEventId,
  vnc,
}: ToolPreviewPanelProps) {
  const [expandedEvent, setExpandedEvent] = useState<SessionEventItem | null>(
    null,
  );
  const toolEvents = useMemo(() => getToolEvents(events), [events]);
  const selectedToolEvent =
    toolEvents.find((event) => event.id === selectedToolEventId) ?? null;
  const activeToolEvent = selectedToolEvent ?? toolEvents[0] ?? null;
  const activeToolName = getString(activeToolEvent?.payload.tool_name);
  const activeToolKind = activeToolEvent
    ? getToolKind(activeToolName, getString(activeToolEvent.payload.output))
    : "Tool";

  return (
    <section className="flex h-full flex-col overflow-hidden border border-(--line) bg-(--surface) shadow-2xl shadow-black/25">
      <div className="border-b border-(--line) bg-(--surface-2)/95 p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="mb-2 text-xs font-medium uppercase tracking-[0.18em] text-(--accent)/70">
              AtlasAgent Computer
            </div>
            <h2 className="flex items-center gap-2 text-lg font-semibold text-(--text-1)">
              <Monitor size={18} aria-hidden="true" />
              {activeToolName || "当前工具详情"}
            </h2>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <ToolKindBadge kind={activeToolKind} />
              <p className="text-sm leading-5 text-(--text-4)">
                点击对话流里的工具节点后，在这里查看参数、输出和观察证据
              </p>
            </div>
          </div>
          <button
            aria-label="关闭工具详情"
            className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-(--line) bg-(--fill-1) text-(--text-3) hover:bg-(--fill-2) hover:text-(--text-1)"
            onClick={onClose}
            title="关闭工具详情"
            type="button"
          >
            <X size={17} aria-hidden="true" />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-auto bg-(--surface) p-4">
        <ToolCallView
          events={events}
          onExpand={setExpandedEvent}
          onRefreshVnc={onRefreshVnc}
          toolEvent={activeToolEvent}
          vnc={vnc}
        />
      </div>

      {expandedEvent ? (
        <ToolResultDialog
          event={expandedEvent}
          onClose={() => setExpandedEvent(null)}
        />
      ) : null}
    </section>
  );
}

function ToolCallView({
  events,
  onExpand,
  onRefreshVnc,
  toolEvent,
  vnc,
}: {
  events: LoadState<SessionEventItem[]>;
  onExpand: (event: SessionEventItem) => void;
  onRefreshVnc: () => void;
  toolEvent: SessionEventItem | null;
  vnc: LoadState<VncStatusData>;
}) {
  if (events.type === "loading") {
    return <EmptyState icon={RefreshCcw} text="正在读取工具事件..." />;
  }

  if (events.type === "error") {
    return <p className="text-sm text-rose-600">{events.message}</p>;
  }

  if (!toolEvent) {
    return <EmptyState icon={Bot} text="点击对话流里的工具节点查看详情。" />;
  }

  const toolName = getString(toolEvent.payload.tool_name);
  const isBrowserTool = toolName.startsWith("browser_");

  return (
    <div className="grid gap-4">
      <ToolCallDetail event={toolEvent} onExpand={onExpand} />
      {isBrowserTool ? (
        <div className="grid gap-3">
          <div className="rounded-[22px] border border-(--accent)/20 bg-blue-500/[0.06] px-4 py-3">
            <div className="flex items-center gap-2 text-sm font-semibold text-(--accent)">
              <Monitor size={16} aria-hidden="true" />
              浏览器实时观察
            </div>
            <p className="mt-1 text-xs leading-5 text-blue-100/60">
              截图是工具调用的结果，远程桌面用于持续观察 Sandbox 中的浏览器画面。
            </p>
          </div>
          <VncPanel onRefresh={onRefreshVnc} state={vnc} />
        </div>
      ) : null}
    </div>
  );
}

function ToolCallDetail({
  event,
  onExpand,
}: {
  event: SessionEventItem;
  onExpand: (event: SessionEventItem) => void;
}) {
  // 1. 从 tool_called 事件中取出工具名和输出。
  //    后端所有工具结果都会先进入 session_events，再由这个面板统一展示。
  const toolName = getString(event.payload.tool_name);
  const output = getString(event.payload.output);
  const previewKind = getToolKind(toolName, output);
  const observation = buildObservationFromEvent(event);

  // 2. 尝试把 output 解析成不同工具的结构化结果。
  //    解析成功就用专门卡片展示，解析失败就回退为普通文本。
  const screenshot = parseScreenshot(output);
  const searchResults = parseSearchResults(output);
  const searchError = parseSearchError(output);
  const mcpResult = parseMcpToolResult(output);
  const a2aResult = parseA2aTaskResult(output);
  const multiAgentResult = parseMultiAgentResult(output);

  // 3. 根据工具类型选择图标，让用户快速分辨这次调用属于哪类能力。
  const Icon = getToolIcon(
    toolName,
    screenshot,
    searchResults ?? searchError,
    mcpResult,
    a2aResult,
    multiAgentResult,
  );

  return (
    <div className="overflow-hidden rounded-[24px] border border-(--line) bg-(--fill-1) shadow-sm">
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-3 border-b border-(--line) bg-white/[0.025] px-4 py-3">
            <h3 className="flex min-w-0 items-center gap-2 truncate text-sm font-semibold text-(--text-1)">
              <Icon className="shrink-0 text-(--accent)" size={17} aria-hidden="true" />
              {toolName || "tool_called"}
            </h3>
            <div className="flex shrink-0 items-center gap-2">
              <ToolKindBadge kind={previewKind} />
              <CopyButton value={output || JSON.stringify(event.payload, null, 2)} />
              <button
                aria-label="展开工具详情"
                className="inline-flex h-8 items-center gap-1 rounded-full border border-(--line) bg-(--fill-1) px-3 text-xs font-medium text-(--text-3) hover:text-(--text-1)"
                onClick={() => onExpand(event)}
                title="展开工具详情"
                type="button"
              >
                <Maximize2 size={14} aria-hidden="true" />
                展开详情
              </button>
              <span className="text-xs text-(--text-5)">
                {formatDateTime(event.created_at)}
              </span>
            </div>
          </div>
          <div className="grid gap-4 p-4">
            <ToolObservationCard
              brief={observation.brief}
              pills={observation.pills}
              title={observation.title}
            />
            {screenshot ? (
              <ScreenshotPreview screenshot={screenshot} />
            ) : searchResults ? (
              <SearchResultsPreview results={searchResults} />
            ) : searchError ? (
              <SearchErrorPreview error={searchError} />
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
            <ToolArguments value={event.payload.arguments} />
          </div>
        </div>
      </div>
    </div>
  );
}

function ToolResultDialog({
  event,
  onClose,
}: {
  event: SessionEventItem;
  onClose: () => void;
}) {
  const toolName = getString(event.payload.tool_name);
  const output = getString(event.payload.output);
  const previewKind = getToolKind(toolName, output);
  const screenshot = parseScreenshot(output);
  const searchResults = parseSearchResults(output);
  const searchError = parseSearchError(output);
  const mcpResult = parseMcpToolResult(output);
  const a2aResult = parseA2aTaskResult(output);
  const multiAgentResult = parseMultiAgentResult(output);
  const observation = buildObservationFromEvent(event);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 bg-black/70 p-6 backdrop-blur-sm max-sm:p-3">
      <div
        aria-labelledby="tool-result-title"
        aria-modal="true"
        className="mx-auto flex h-full max-w-5xl flex-col overflow-hidden rounded-[28px] border border-(--line) bg-(--surface) shadow-2xl shadow-black/70"
        role="dialog"
      >
        <div className="flex items-center justify-between gap-3 border-b border-(--line) bg-(--surface-2)/95 px-5 py-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h2
                className="truncate text-base font-semibold text-(--text-1)"
                id="tool-result-title"
              >
                {toolName || "工具详情"}
              </h2>
              <ToolKindBadge kind={previewKind} />
            </div>
            <p className="mt-1 text-xs text-(--text-4)">
              {formatDateTime(event.created_at)}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <CopyButton value={output || JSON.stringify(event.payload, null, 2)} />
            <button
              aria-label="关闭工具详情"
              className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-(--line) bg-(--fill-1) text-(--text-3) hover:bg-(--fill-2) hover:text-(--text-1)"
              onClick={onClose}
              title="关闭"
              type="button"
            >
              <X size={17} aria-hidden="true" />
            </button>
          </div>
        </div>

        <div className="grid flex-1 grid-cols-[320px_1fr] overflow-hidden max-lg:grid-cols-1">
          <aside className="overflow-auto border-r border-(--line) bg-white/[0.025] p-4 max-lg:border-b max-lg:border-r-0">
            <ToolObservationCard
              brief={observation.brief}
              pills={observation.pills}
              title={observation.title}
            />
            <ToolArguments value={event.payload.arguments} />
          </aside>
          <main className="overflow-auto p-5">
            {screenshot ? (
              <img
                alt="浏览器截图大图"
                className="mx-auto max-h-full w-full object-contain"
                src={`data:${screenshot.mime_type};base64,${screenshot.base64_data}`}
              />
            ) : searchResults ? (
              <SearchResultsPreview results={searchResults} />
            ) : searchError ? (
              <SearchErrorPreview error={searchError} />
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
          </main>
        </div>
      </div>
    </div>
  );
}

function ToolArguments({ value }: { value: unknown }) {
  const entries = getArgumentEntries(value);
  return (
    <div className="mt-3">
      <div className="mb-1 text-xs font-medium text-(--text-4)">调用参数</div>
      {entries.length ? (
        <div className="grid gap-2">
          {entries.map(([key, entryValue]) => (
            <div
              className="rounded-2xl border border-(--line) bg-(--field) px-3 py-2"
              key={key}
            >
              <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-(--text-5)">
                {key}
              </div>
              <div className="mt-1 break-words text-xs leading-5 text-(--text-2)">
                {formatArgumentValue(entryValue)}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded-2xl border border-(--line) bg-(--field) px-3 py-2 text-xs text-(--text-4)">
          这个工具没有显式参数。
        </div>
      )}
    </div>
  );
}

function ToolObservationCard({
  brief,
  pills,
  title,
}: {
  brief: string;
  pills: string[];
  title: string;
}) {
  return (
    <section className="rounded-[22px] border border-(--accent)/20 bg-blue-500/[0.06] px-4 py-3">
      <div className="flex items-center gap-2 text-sm font-semibold text-(--accent)">
        <Check size={15} aria-hidden="true" />
        {title}
      </div>
      <p className="mt-2 text-sm leading-6 text-blue-100/70">{brief}</p>
      {pills.length ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {pills.map((label) => (
            <span
              className="rounded-full border border-(--accent)/20 bg-(--accent)/10 px-3 py-1 text-xs font-medium text-blue-100/80"
              key={label}
            >
              {label}
            </span>
          ))}
        </div>
      ) : null}
    </section>
  );
}

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
      aria-label={copied ? "工具输出已复制" : "复制工具输出"}
      className={
        tone === "light"
          ? "inline-flex h-9 items-center gap-1 rounded-md border border-(--line) px-3 text-xs font-medium text-(--text-3) hover:bg-(--fill-1)"
          : "inline-flex h-8 items-center gap-1 rounded-full border border-(--line) bg-(--fill-1) px-3 text-xs font-medium text-(--text-3) hover:text-(--text-1)"
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

function ToolKindBadge({
  kind,
  tone = "dark",
}: {
  kind: string;
  tone?: "dark" | "light";
}) {
  const className =
    tone === "light"
      ? "rounded-full border border-(--line) bg-(--fill-1) px-2 py-0.5 text-[11px] font-semibold text-(--text-3)"
      : "rounded-full border border-(--accent)/25 bg-(--accent)/10 px-2 py-0.5 text-[11px] font-semibold text-(--accent)";
  return <span className={className}>{kind}</span>;
}

function PlainToolPreview({
  output,
  title,
}: {
  output: string;
  title: string;
}) {
  return (
    <div className="rounded-xl border border-(--line) bg-(--field)">
      <div className="border-b border-(--line) px-3 py-2 text-xs font-semibold text-(--text-3)">
        {title}
      </div>
      <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words p-4 text-xs leading-5 text-(--text-2)">
        {output || "<no output>"}
      </pre>
    </div>
  );
}

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
      <div className="flex items-center justify-between gap-3 border-b border-(--line) px-3 py-2">
        <div className="flex items-center gap-2 text-xs font-semibold text-(--text-2)">
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
      <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words p-4 font-mono text-xs leading-6 text-(--text-1)">
        {output || "<no output>"}
      </pre>
    </div>
  );
}

function ScreenshotPreview({ screenshot }: { screenshot: ScreenshotPayload }) {
  return (
    <div className="mt-3 overflow-hidden rounded-2xl border border-(--line) bg-(--fill-1)">
      <img
        alt="浏览器截图"
        className="max-h-64 w-full object-contain"
        src={`data:${screenshot.mime_type};base64,${screenshot.base64_data}`}
      />
      <div className="border-t border-(--line) px-3 py-2 text-xs text-(--text-4)">
        {screenshot.mime_type} · {screenshot.size} bytes
      </div>
    </div>
  );
}

function SearchResultsPreview({ results }: { results: SearchResultsPayload }) {
  return (
    <div className="mt-3 rounded-2xl border border-(--line) bg-(--fill-1)">
      <div className="border-b border-(--line) px-3 py-2">
        <div className="text-xs font-medium text-(--text-4)">搜索结果</div>
        <div className="mt-1 text-sm font-semibold text-(--text-1)">
          {results.query}
        </div>
        <div className="mt-1 text-xs text-(--text-4)">
          provider: {results.provider}
        </div>
      </div>
      <div className="grid gap-2 p-3">
        {results.items.map((item) => (
          <a
            className="block rounded-md border border-(--line) px-3 py-2 transition hover:border-(--accent)/40 hover:bg-(--fill-1)"
            href={item.url}
            key={`${item.title}-${item.url}`}
            rel="noreferrer"
            target="_blank"
          >
            <div className="line-clamp-1 text-sm font-semibold text-(--text-1)">
              {item.title || item.url}
            </div>
            <div className="mt-1 line-clamp-1 text-xs text-(--accent)">
              {item.url}
            </div>
            <p className="mt-1 line-clamp-2 text-xs leading-5 text-(--text-3)">
              {item.snippet || "暂无摘要"}
            </p>
          </a>
        ))}
      </div>
    </div>
  );
}

function SearchErrorPreview({ error }: { error: SearchErrorPayload }) {
  return (
    <div className="mt-3 rounded-2xl border border-amber-500/20 bg-amber-500/10 p-4">
      <div className="text-xs font-medium uppercase tracking-[0.14em] text-amber-300">
        搜索暂不可用
      </div>
      <div className="mt-2 text-sm font-semibold text-(--text-1)">
        {error.query}
      </div>
      <p className="mt-2 text-sm leading-6 text-amber-100/80">
        {error.message || "搜索页面暂时无法访问，请稍后重试。"}
      </p>
      <div className="mt-3 text-xs text-amber-200/70">
        provider: {error.provider}
      </div>
    </div>
  );
}

function McpResultPreview({ result }: { result: McpToolResultPayload }) {
  return (
    <div className="mt-3 rounded-2xl border border-(--line) bg-(--fill-1)">
      <div className="border-b border-(--line) px-3 py-2">
        <div className="text-xs font-medium text-(--text-4)">MCP 工具结果</div>
        <div className="mt-1 text-sm font-semibold text-(--text-1)">
          {result.server_name}.{result.tool_name}
        </div>
      </div>
      <div className="grid gap-3 p-3">
        <div>
          <div className="mb-1 text-xs font-medium text-(--text-4)">
            MCP 参数
          </div>
          <div className="grid gap-2">
            {getArgumentEntries(result.arguments).map(([key, value]) => (
              <div
                className="rounded-xl border border-(--line) bg-(--fill-1) px-3 py-2 text-xs text-(--text-2)"
                key={key}
              >
                <span className="font-semibold text-(--text-4)">{key}：</span>
                {formatArgumentValue(value)}
              </div>
            ))}
          </div>
        </div>
        <div>
          <div className="mb-1 text-xs font-medium text-(--text-4)">
            MCP 返回内容
          </div>
          <div className="grid max-h-56 gap-2 overflow-auto">
            {result.content.map((item, index) => (
              <div
                className="rounded-xl border border-(--line) bg-(--fill-1) px-3 py-2 text-xs leading-5 text-(--text-2)"
                key={`${result.tool_name}-${index}`}
              >
                {renderMcpContentItem(item)}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function A2aResultPreview({ result }: { result: A2aTaskResultPayload }) {
  // 这个组件只负责展示 A2A 工具结果。
  // 数据已经在 parseA2aTaskResult 中做过结构检查，所以这里可以直接渲染。
  return (
    <div className="mt-3 rounded-2xl border border-(--line) bg-(--fill-1)">
      <div className="border-b border-(--line) px-3 py-2">
        <div className="text-xs font-medium text-(--text-4)">A2A 远程 Agent</div>
        <div className="mt-1 text-sm font-semibold text-(--text-1)">
          {result.remote_agent}
        </div>
        <div className="mt-1 text-xs text-(--text-4)">
          {result.agent_key} · {result.task_id} · {result.status}
        </div>
      </div>
      <div className="grid gap-3 p-3">
        <div>
          <div className="mb-1 text-xs font-medium text-(--text-4)">
            远程输出
          </div>
          <div className="rounded-md bg-(--fill-1) p-2 text-xs leading-5 text-(--text-2)">
            {result.output_message.map((part) => part.text).join("\n") || "暂无输出"}
          </div>
        </div>
        <div>
          <div className="mb-1 text-xs font-medium text-(--text-4)">
            协作步骤
          </div>
          <div className="grid gap-2">
            {result.steps.map((step) => (
              <div
                className="rounded-md border border-(--line) bg-(--fill-1) px-2 py-1.5"
                key={`${step.index}-${step.action}`}
              >
                <div className="text-xs font-semibold text-(--text-1)">
                  {step.index}. {step.action}
                </div>
                <p className="mt-1 text-xs leading-5 text-(--text-3)">
                  {step.detail}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function MultiAgentResultPreview({ result }: { result: MultiAgentResultPayload }) {
  // 这个组件展示 Manager / Worker / Reviewer 的协作结果。
  // 数据已经经过 parseMultiAgentResult 检查，因此这里只负责布局。
  return (
    <div className="mt-3 rounded-2xl border border-(--line) bg-(--fill-1)">
      <div className="border-b border-(--line) px-3 py-2">
        <div className="text-xs font-medium text-(--text-4)">多 Agent 协作</div>
        <div className="mt-1 text-sm font-semibold text-(--text-1)">
          {result.manager}
        </div>
        <p className="mt-1 text-xs leading-5 text-(--text-4)">{result.task}</p>
      </div>
      <div className="grid gap-3 p-3">
        <div>
          <div className="mb-1 text-xs font-medium text-(--text-4)">
            子任务分派
          </div>
          <div className="grid gap-2">
            {result.subtasks.map((subtask) => (
              <div
                className="rounded-md border border-(--line) bg-(--fill-1) px-2 py-1.5"
                key={subtask.id}
              >
                <div className="flex items-center justify-between gap-2 text-xs">
                  <span className="font-semibold text-(--text-1)">
                    {subtask.title}
                  </span>
                  <span className="text-(--text-4)">{subtask.status}</span>
                </div>
                <p className="mt-1 text-xs text-(--text-4)">{subtask.assignee}</p>
                <p className="mt-1 text-xs leading-5 text-(--text-2)">
                  {subtask.output}
                </p>
              </div>
            ))}
          </div>
        </div>
        <div className="rounded-md border border-emerald-500/25 bg-emerald-500/10 px-3 py-2">
          <div className="text-xs font-semibold text-emerald-100">
            {result.review.reviewer} · {result.review.status}
          </div>
          <ul className="mt-1 list-inside list-disc text-xs leading-5 text-emerald-200/80">
            {result.review.comments.map((comment) => (
              <li key={comment}>{comment}</li>
            ))}
          </ul>
          <p className="mt-1 text-xs leading-5 text-emerald-200/80">
            {result.review.improvement}
          </p>
        </div>
        <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-md bg-(--fill-1) p-3 text-xs leading-5 text-(--text-2)">
          {result.final_answer}
        </pre>
      </div>
    </div>
  );
}

function EmptyState({
  icon: Icon,
  text,
}: {
  icon: typeof Bot;
  text: string;
}) {
  return (
    <div className="flex items-center gap-2 rounded-md border border-(--line) bg-(--fill-1) px-3 py-2 text-sm text-(--text-4)">
      <Icon size={16} aria-hidden="true" />
      <span>{text}</span>
    </div>
  );
}

function getToolEvents(state: LoadState<SessionEventItem[]>): SessionEventItem[] {
  if (state.type !== "ready") {
    return [];
  }
  return [...state.data]
    .filter((event) => event.type === "tool_called")
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
}

function getToolIcon(
  toolName: string,
  screenshot: ScreenshotPayload | null,
  searchResults: SearchResultsPayload | SearchErrorPayload | null,
  mcpResult: McpToolResultPayload | null,
  a2aResult: A2aTaskResultPayload | null,
  multiAgentResult: MultiAgentResultPayload | null,
) {
  if (screenshot) {
    return Camera;
  }
  if (searchResults || toolName.startsWith("search_")) {
    return Search;
  }
  if (mcpResult || toolName.startsWith("mcp_")) {
    return Plug;
  }
  if (a2aResult || toolName.startsWith("a2a_")) {
    return Network;
  }
  if (multiAgentResult || toolName.startsWith("multi_agent_")) {
    return GitBranch;
  }
  if (toolName.startsWith("browser_")) {
    return Globe;
  }
  if (toolName.startsWith("shell_")) {
    return Terminal;
  }
  if (toolName.startsWith("file_")) {
    return FileText;
  }
  if (toolName.includes("list")) {
    return FolderOpen;
  }
  return Hammer;
}

function getToolKind(toolName: string, output: string) {
  if (parseScreenshot(output)) {
    return "Browser Screenshot";
  }
  if (parseSearchResults(output) || parseSearchError(output) || toolName.startsWith("search_")) {
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

function parseScreenshot(value: string): ScreenshotPayload | null {
  try {
    const payload = JSON.parse(value) as Partial<ScreenshotPayload>;
    if (
      payload.kind === "browser_screenshot" &&
      typeof payload.mime_type === "string" &&
      typeof payload.base64_data === "string" &&
      typeof payload.size === "number"
    ) {
      return payload as ScreenshotPayload;
    }
  } catch {
    return null;
  }
  return null;
}

function parseSearchResults(value: string): SearchResultsPayload | null {
  try {
    // SearchTool 的 output 是 JSON 字符串。
    // 只有 kind=search_results 时，才按搜索结果卡片渲染；其他工具输出继续走普通文本。
    const payload = JSON.parse(value) as Partial<SearchResultsPayload>;
    if (
      payload.kind === "search_results" &&
      typeof payload.provider === "string" &&
      typeof payload.query === "string" &&
      Array.isArray(payload.items)
    ) {
      return {
        kind: "search_results",
        provider: payload.provider,
        query: payload.query,
        items: payload.items.map((item) => ({
          title: getString(item.title),
          url: getString(item.url),
          snippet: getString(item.snippet),
        })),
      };
    }
  } catch {
    return null;
  }
  return null;
}

function parseSearchError(value: string): SearchErrorPayload | null {
  try {
    const payload = JSON.parse(value) as Partial<SearchErrorPayload>;
    if (
      payload.kind === "search_error" &&
      typeof payload.provider === "string" &&
      typeof payload.query === "string" &&
      typeof payload.message === "string"
    ) {
      return {
        kind: "search_error",
        provider: payload.provider,
        query: payload.query,
        message: payload.message,
        items: [],
      };
    }
  } catch {
    return null;
  }
  return null;
}

function parseMcpToolResult(value: string): McpToolResultPayload | null {
  try {
    // McpAgentTool 的 output 是 JSON 字符串。
    // 只有 kind=mcp_tool_result 时，才按 MCP 工具卡片渲染。
    const payload = JSON.parse(value) as Partial<McpToolResultPayload>;
    if (
      payload.kind === "mcp_tool_result" &&
      typeof payload.server_name === "string" &&
      typeof payload.tool_name === "string" &&
      payload.arguments &&
      typeof payload.arguments === "object" &&
      Array.isArray(payload.content)
    ) {
      return {
        kind: "mcp_tool_result",
        server_name: payload.server_name,
        tool_name: payload.tool_name,
        arguments: payload.arguments as Record<string, unknown>,
        content: payload.content.map((item) =>
          item && typeof item === "object" ? item : { value: item },
        ),
      };
    }
  } catch {
    return null;
  }
  return null;
}

function parseA2aTaskResult(value: string): A2aTaskResultPayload | null {
  try {
    // 1. A2aAgentTool 的 output 是 JSON 字符串。
    //    如果不是 JSON，说明它不是 A2A 结构化结果，直接返回 null。
    const payload = JSON.parse(value) as Partial<A2aTaskResultPayload>;

    // 2. kind 是工具结果协议的分流字段。
    //    只有 kind=a2a_task_result 时，才按远程 Agent 协作结果卡片渲染。
    if (
      payload.kind === "a2a_task_result" &&
      typeof payload.agent_key === "string" &&
      typeof payload.remote_agent === "string" &&
      typeof payload.task_id === "string" &&
      typeof payload.status === "string" &&
      Array.isArray(payload.input_message) &&
      Array.isArray(payload.output_message) &&
      Array.isArray(payload.steps)
    ) {
      // 3. 做一次轻量归一化。
      //    后端返回的数组元素即使缺字段，前端也尽量用空字符串兜底。
      return {
        kind: "a2a_task_result",
        agent_key: payload.agent_key,
        remote_agent: payload.remote_agent,
        task_id: payload.task_id,
        status: payload.status,
        input_message: payload.input_message.map((item) => ({
          kind: getString(item.kind),
          text: getString(item.text),
        })),
        output_message: payload.output_message.map((item) => ({
          kind: getString(item.kind),
          text: getString(item.text),
        })),
        steps: payload.steps.map((item, index) => ({
          index: typeof item.index === "number" ? item.index : index + 1,
          action: getString(item.action),
          detail: getString(item.detail),
        })),
      };
    }
  } catch {
    // 4. 解析失败不是页面错误。
    //    其他工具的普通文本输出也会走到这里，所以静默返回 null。
    return null;
  }
  return null;
}

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

function buildObservationFromEvent(event: SessionEventItem) {
  const title = getString(event.payload.title) || getString(event.payload.tool_name);
  const syntheticStep: StepView = {
    completedAt: event.created_at,
    description: title,
    errorEvent: null,
    expected_output: "",
    id: getString(event.payload.step_id) || event.id,
    startedAt: null,
    status: "completed",
    summary: getString(event.payload.output),
    title: title || "工具调用",
    toolEvent: event,
  };
  return buildToolObservation(syntheticStep);
}

function getArgumentEntries(value: unknown): Array<[string, unknown]> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return [];
  }
  return Object.entries(value as Record<string, unknown>);
}

function formatArgumentValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return value
      .map((item) =>
        typeof item === "string" || typeof item === "number" || typeof item === "boolean"
          ? String(item)
          : "结构化项",
      )
      .join("、");
  }
  return "结构化参数，已传给工具执行";
}

function renderMcpContentItem(item: Record<string, unknown>): string {
  const text = getString(item.text);
  if (text) {
    return text;
  }
  const type = getString(item.type) || getString(item.kind);
  if (type) {
    return `${type} 内容已返回，完整结构可通过复制工具输出查看。`;
  }
  return "MCP 返回了结构化内容，完整结构可通过复制工具输出查看。";
}

function getString(value: unknown): string {
  return typeof value === "string" ? value : "";
}
