"use client";

import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, Loader2 } from "lucide-react";

import type { SessionEventItem } from "../../types";
import { getString } from "./view-model";

type ToolCallLogProps = {
  events: SessionEventItem[];
  running: boolean;
};

/** 每次揭示的行数：一次多喂几行，滚动更快。 */
const STREAM_STEP = 6;
/** 揭示间隔（毫秒）：约 40fps，接近终端刷新的手感。 */
const STREAM_INTERVAL_MS = 24;
/** 直播条上输出预览的最大长度。 */
const TAIL_LIMIT = 72;

/** 把一次工具调用渲染成一条「命令」文本：shell 显示原始命令，其余显示工具名。 */
function commandOf(event: SessionEventItem): string {
  const toolName = getString(event.payload.tool_name);
  const args = event.payload.arguments as Record<string, unknown> | undefined;
  if (toolName === "shell_run" && args?.command) {
    return getString(args.command);
  }
  if (toolName.startsWith("file_") && args?.path) {
    return `${toolName} ${getString(args.path)}`;
  }
  return toolName;
}

/** 取输出里最后一行非空内容，截断后作为直播预览。 */
function tailOf(output: string): string {
  const lines = output.split("\n").filter((line) => line.trim());
  const tail = lines[lines.length - 1]?.trim() ?? "";
  return tail.length > TAIL_LIMIT ? `${tail.slice(0, TAIL_LIMIT)}…` : tail;
}

/**
 * 执行直播：只保留一行，实时显示当前正在执行的工具命令与最新输出。
 * 运行中末尾输出逐批揭示，形成「正在滚动」的直播手感；结束后定格在最后一条。
 */
export function ToolCallLog({ events, running }: ToolCallLogProps) {
  const toolEvents = useMemo(
    () => events.filter((event) => event.type === "tool_called"),
    [events],
  );

  const last = toolEvents[toolEvents.length - 1];
  const lastOutput = last ? getString(last.payload.output) : "";
  const lastLines = useMemo(() => lastOutput.split("\n"), [lastOutput]);

  // 已揭示的行数：运行中从 0 开始流式增长；结束后一次性显示全部。
  const [streamedLines, setStreamedLines] = useState(() =>
    running ? 0 : lastLines.length,
  );

  // 新工具到来或运行状态变化时重置揭示进度。
  useEffect(() => {
    setStreamedLines(running ? 0 : lastLines.length);
  }, [toolEvents.length, running, lastLines.length]);

  // 运行中逐行快速揭示最后一条输出。
  useEffect(() => {
    if (!running || streamedLines >= lastLines.length) {
      return;
    }
    const timer = window.setTimeout(() => {
      setStreamedLines((previous) =>
        Math.min(previous + STREAM_STEP, lastLines.length),
      );
    }, STREAM_INTERVAL_MS);
    return () => window.clearTimeout(timer);
  }, [running, streamedLines, lastLines.length]);

  if (!last) {
    return null;
  }

  const status = getString(last.payload.status);
  const visibleOutput =
    running && streamedLines < lastLines.length
      ? lastLines.slice(0, streamedLines).join("\n")
      : lastOutput;
  const tail = tailOf(visibleOutput);

  return (
    <div className="ml-11 max-w-4xl">
      <div className="flex items-center gap-2 rounded-lg border border-(--line) bg-(--fill-1) px-3 py-2 font-mono text-xs text-(--text-3)">
        {running ? (
          <Loader2
            className="shrink-0 animate-spin text-(--accent)"
            size={13}
            aria-label="执行中"
          />
        ) : status === "failed" ? (
          <span className="shrink-0 text-rose-400" aria-label="失败">
            ✕
          </span>
        ) : (
          <CheckCircle2
            className="shrink-0 text-emerald-500"
            size={13}
            aria-label="完成"
          />
        )}
        <span className="shrink-0 select-none text-(--text-5)">$</span>
        <span className="shrink-0 text-(--accent)">{commandOf(last)}</span>
        {tail ? (
          <span className="min-w-0 flex-1 truncate text-(--text-5)">
            {tail}
          </span>
        ) : (
          <span className="flex-1" />
        )}
        <span className="shrink-0 text-(--text-5)">
          {toolEvents.length} 次调用
        </span>
      </div>
    </div>
  );
}
