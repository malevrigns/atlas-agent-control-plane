import { Trash2 } from "lucide-react";

import { formatDate } from "../lib/format";
import type { LoadState, SessionItem } from "../types";

type SessionListProps = {
  onDelete: (sessionId: string) => void;
  onSelect: (sessionId: string) => void;
  selectedId: string | null;
  state: LoadState<SessionItem[]>;
};

export function SessionList({
  onDelete,
  onSelect,
  selectedId,
  state,
}: SessionListProps) {
  if (state.type === "loading") {
    return <div className="mt-4 text-sm text-(--text-4)">加载中...</div>;
  }

  if (state.type === "error") {
    return (
      <div className="mt-4 rounded-md border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
        {state.message}
      </div>
    );
  }

  if (state.data.length === 0) {
    return (
      <div className="mt-4 rounded-md border border-dashed border-(--line-strong) px-3 py-8 text-center text-sm text-(--text-4)">
        暂无会话
      </div>
    );
  }

  return (
    <div className="mt-3 min-h-0 flex-1 overflow-y-auto pr-1">
      <div className="grid gap-2">
      {state.data.map((session) => (
        <div
          className={`group flex items-center gap-2 rounded-md border px-3 py-3 transition ${
            selectedId === session.id
              ? "border-(--accent)/50 bg-(--accent)/10"
              : "border-(--line) bg-(--fill-1) hover:border-(--line-strong) hover:bg-(--fill-2)"
          }`}
          key={session.id}
        >
          <button
            className="min-w-0 flex-1 text-left"
            onClick={() => onSelect(session.id)}
            type="button"
          >
            <div className="truncate text-sm font-medium text-(--text-1)">
              {session.title}
            </div>
            <div className="mt-1 text-xs text-(--text-4)">
              {session.status} · {formatDate(session.updated_at)}
            </div>
          </button>
          <button
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-(--text-5) opacity-0 transition hover:bg-rose-500/10 hover:text-rose-300 group-hover:opacity-100"
            onClick={() => onDelete(session.id)}
            title="删除会话"
            type="button"
          >
            <Trash2 size={15} aria-hidden="true" />
          </button>
        </div>
      ))}
      </div>
    </div>
  );
}
