import { BellOff, BrainCircuit, Square } from "lucide-react";

import { workspaceButton } from "../lib/design-tokens";
import type { SessionItem } from "../types";

type SessionControlBarProps = {
  clearingUnread: boolean;
  onClearUnread: () => void;
  onOpenContext: () => void;
  onStop: () => void;
  selectedSession: SessionItem | null;
  stopping: boolean;
};

export function SessionControlBar({
  clearingUnread,
  onClearUnread,
  onOpenContext,
  onStop,
  selectedSession,
  stopping,
}: SessionControlBarProps) {
  const isRunning = selectedSession?.status === "running";
  const hasUnread = Boolean(selectedSession && selectedSession.unread_count > 0);

  return (
    <div className="flex h-16 shrink-0 items-center justify-between bg-transparent px-8 backdrop-blur-2xl max-sm:h-auto max-sm:items-start max-sm:gap-3 max-sm:px-5 max-sm:py-3">
      <div className="min-w-0">
        <div className="truncate text-xl font-semibold text-zinc-50">
          {selectedSession ? selectedSession.title : "新任务"}
        </div>
        <p className="mt-1 text-sm text-zinc-600">
          {isRunning ? "正在执行任务" : "描述任务后，Agent 会自动规划并执行"}
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          aria-label="查看上下文"
          className={workspaceButton.icon}
          disabled={!selectedSession}
          onClick={onOpenContext}
          title="查看上下文"
          type="button"
        >
          <BrainCircuit size={15} aria-hidden="true" />
        </button>
        <button
          aria-label="清除未读消息"
          className={workspaceButton.icon}
          disabled={!selectedSession || !hasUnread || clearingUnread}
          onClick={onClearUnread}
          title="清除未读"
          type="button"
        >
          <BellOff size={15} aria-hidden="true" />
        </button>
        <button
          aria-label="停止当前任务"
          className="flex h-9 w-9 items-center justify-center rounded-full border border-rose-500/30 bg-rose-500/5 text-rose-300 transition hover:bg-rose-500/10 disabled:cursor-not-allowed disabled:border-white/10 disabled:bg-white/[0.03] disabled:text-zinc-800"
          disabled={!selectedSession || !isRunning || stopping}
          onClick={onStop}
          title="停止任务"
          type="button"
        >
          <Square size={14} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
