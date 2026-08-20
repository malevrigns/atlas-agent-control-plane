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
    <div className="ml-11 max-w-4xl overflow-hidden rounded-2xl border border-(--line) bg-(--surface) shadow-xl shadow-black/10">
      <div className="flex items-center gap-2 border-b border-(--line-soft) px-4 py-2.5 text-xs font-semibold uppercase tracking-[0.18em] text-(--text-4)">
        <Terminal className="text-(--accent)" size={14} aria-hidden="true" />
        执行日志
      </div>
      <div
        ref={scrollRef}
        className="max-h-64 overflow-y-auto bg-black/40 px-4 py-3 font-mono text-xs leading-6 text-(--text-2)"
      >
        {toolEvents.map((event, index) => {
          const output = getString(event.payload.output);
          const status = getString(event.payload.status);
          const isLast = index === toolEvents.length - 1;
          const lines = output.split("\n");
          const visibleLines =
            isLast && running ? lines.slice(0, streamedLines) : lines;
          return (
            <div className="py-1" key={event.id ?? index}>
              <div className="text-(--accent)">
                <span className="select-none">$ </span>
                {commandOf(event)}
                {status === "failed" ? (
                  <span className="ml-2 text-rose-400">[失败]</span>
                ) : null}
              </div>
              {output ? (
                <div className="whitespace-pre-wrap text-(--text-4)">
                  {visibleLines.join("\n")}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
