import { Trash2 } from "lucide-react";

import { formatDate } from "../lib/format";
import type { LoadState, SessionItem } from "../types";

type SessionListProps = {
  onDelete: (sessionId: string) => void;
  onSelect: (sessionId: string) => void;
  selectedId: string | null;
  state: LoadState<SessionItem[]>;
};

/** 会话状态到呼吸点样式：执行中呼吸、异常红点、其余灰点。 */
function statusDotClass(status: string) {
  if (["running", "planning", "executing", "waiting", "retrying"].includes(status)) {
    return "live";
  }
  if (["failed", "error"].includes(status)) {
    return "bad";
  }
  return "idle";
}

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
      <div className="mt-4 rounded-xl border border-dashed border-(--line-strong) px-3 py-8 text-center text-sm text-(--text-4)">
        暂无会话
      </div>
    );
  }

  return (
    <div className="mt-3 min-h-0 flex-1 overflow-y-auto pr-1">
      <div className="grid gap-2">
        {state.data.map((session, index) => {
          const selected = selectedId === session.id;
          return (
            <div
              className={`cockpit-item group relative flex items-center gap-2 overflow-hidden rounded-xl border px-3 py-3 transition-all duration-200 ${
                selected
                  ? "border-(--accent)/45 bg-(--accent)/12 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]"
                  : "border-(--line) bg-(--fill-1) hover:translate-x-0.5 hover:border-(--line-strong) hover:bg-(--fill-2)"
              }`}
              key={session.id}
              style={{ animationDelay: `${Math.min(index * 30, 300)}ms` }}
            >
              {/* 左缘渐变状态条：选中常亮，悬停半亮。 */}
              <span
                aria-hidden="true"
                className={`absolute inset-y-2 left-0 w-[3px] rounded-full bg-gradient-to-b from-blue-400 to-violet-500 transition-opacity ${
                  selected ? "opacity-100" : "opacity-0 group-hover:opacity-60"
                }`}
              />
              <button
                className="min-w-0 flex-1 pl-1.5 text-left"
                onClick={() => onSelect(session.id)}
                type="button"
              >
                <div className="truncate text-sm font-medium text-(--text-1)">
                  {session.title}
                </div>
                <div className="mt-1 flex items-center gap-1.5 text-xs text-(--text-4)">
                  <span
                    aria-hidden="true"
                    className={`status-dot ${statusDotClass(session.status)}`}
                  />
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
          );
        })}
      </div>
    </div>
  );
}
