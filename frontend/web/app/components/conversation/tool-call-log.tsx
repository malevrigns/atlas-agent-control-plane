"use client";

import { useEffect, useRef } from "react";
import { Terminal } from "lucide-react";

import type { SessionEventItem } from "../../types";
import { getString } from "./view-model";

type ToolCallLogProps = {
  events: SessionEventItem[];
  running: boolean;
};

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
 * 执行日志：把本轮的工具调用逐条滚动展示，像终端一样。
 * 运行中自动滚到底部，新命令一到就顶到最新。
 */
export function ToolCallLog({ events, running }: ToolCallLogProps) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const toolEvents = events.filter((event) => event.type === "tool_called");

  useEffect(() => {
    if (running && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [toolEvents.length, running]);

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
        className="max-h-56 overflow-y-auto bg-black/40 px-4 py-3 font-mono text-xs leading-6 text-(--text-2)"
      >
        {toolEvents.map((event, index) => {
          const output = getString(event.payload.output);
          const status = getString(event.payload.status);
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
                <div className="whitespace-pre-wrap text-(--text-4)">{output}</div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
