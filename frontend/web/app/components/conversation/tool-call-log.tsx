"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Terminal } from "lucide-react";

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

/** 工具写入的文件相对路径（file_write / file_replace），用于生成下载链接。 */
function writtenPath(event: SessionEventItem): string {
  const toolName = getString(event.payload.tool_name);
  if (toolName !== "file_write" && toolName !== "file_replace") {
    return "";
  }
  const args = event.payload.arguments as Record<string, unknown> | undefined;
  return args?.path ? getString(args.path) : "";
}

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

/**
 * 执行日志：像终端一样，输出逐行快速「流式」滚动。
 * 运行中最后一条工具的输出按行分批揭示，并自动钉在底部。
 */
export function ToolCallLog({ events, running }: ToolCallLogProps) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
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

  // 揭示进度一变化就钉到底部，形成连续滚动。
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [streamedLines, toolEvents.length]);

  if (!toolEvents.length) {
    return null;
  }

  return (
    <div className="ml-11 max-w-4xl overflow-hidden rounded-xl border border-zinc-700/60 bg-zinc-950 shadow-lg shadow-black/30">
      {/* 终端标题栏：红绿灯 + 标题 + 运行状态 */}
      <div className="flex items-center gap-2 border-b border-zinc-800 bg-zinc-900/80 px-4 py-2">
        <span className="flex gap-1.5" aria-hidden="true">
          <span className="h-2.5 w-2.5 rounded-full bg-rose-500/80" />
          <span className="h-2.5 w-2.5 rounded-full bg-amber-400/80" />
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-500/80" />
        </span>
        <span className="ml-1 flex items-center gap-1.5 font-mono text-[11px] text-zinc-400">
          <Terminal size={12} aria-hidden="true" />
          执行日志
        </span>
        {running ? (
          <span className="ml-auto flex items-center gap-1.5 font-mono text-[11px] text-emerald-400">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
            running
          </span>
        ) : null}
      </div>
      <div
        ref={scrollRef}
        className="max-h-72 overflow-y-auto px-4 py-3 font-mono text-xs leading-6 text-zinc-300"
      >
        {toolEvents.map((event, index) => {
          const output = getString(event.payload.output);
          const status = getString(event.payload.status);
          const isLast = index === toolEvents.length - 1;
          const lines = output.split("\n");
          const visibleLines =
            isLast && running ? lines.slice(0, streamedLines) : lines;
          return (
            <div className="py-0.5" key={event.id ?? index}>
              <div className="text-emerald-400">
                <span className="select-none text-zinc-500">$ </span>
                {commandOf(event)}
                {status === "failed" ? (
                  <span className="ml-2 text-rose-400">[失败]</span>
                ) : null}
                {writtenPath(event) ? (
                  <a
                    className="ml-2 inline-flex items-center gap-1 rounded border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-px text-[10px] font-medium text-emerald-300 no-underline transition hover:bg-emerald-500/20"
                    href={`/api/sessions/${event.session_id}/sandbox-files/download?path=${encodeURIComponent(writtenPath(event))}`}
                    download
                  >
                    ↓ 下载
                  </a>
                ) : null}
              </div>
              {output ? (
                <div className="whitespace-pre-wrap text-zinc-500">
                  {visibleLines.join("\n")}
                </div>
              ) : null}
            </div>
          );
        })}
        {running ? (
          <span className="inline-block h-4 w-2 animate-pulse bg-emerald-400/80 align-text-bottom" />
        ) : null}
      </div>
    </div>
  );
}
