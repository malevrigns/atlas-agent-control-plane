"use client";

import { Loader2 } from "lucide-react";

import type { TodoBoard, TodoItem } from "../../lib/control-plane-api";

const STATUS_LABELS: Record<TodoItem["status"], string> = {
  pending: "待执行",
  in_progress: "进行中",
  done: "完成",
  failed: "失败",
  skipped: "跳过",
};

const STATUS_TONES: Record<TodoItem["status"], string> = {
  pending: "border-(--line) text-(--text-4)",
  in_progress: "border-(--accent)/50 text-(--accent)",
  done: "border-emerald-400/50 text-emerald-300",
  failed: "border-red-400/50 text-red-300",
  skipped: "border-(--line) text-(--text-5)",
};

type TodoBoardPanelProps = {
  board: TodoBoard | null;
  loading: boolean;
};

/**
 * 依赖拓扑看板。next_runnable 是执行机按 depends_on 算出的下一步，
 * 长程任务卡在哪、为什么还不能动，看这一列比看对话更直接。
 */
export function TodoBoardPanel({ board, loading }: TodoBoardPanelProps) {
  if (loading) {
    return (
      <div className="flex items-center gap-2 px-1 py-6 text-sm text-(--text-4)">
        <Loader2 className="animate-spin" size={15} aria-hidden="true" />
        读取清单…
      </div>
    );
  }

  if (!board || board.items.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-(--line) px-4 py-6 text-sm text-(--text-4)">
        还没有计划清单。制定计划后，步骤、依赖和下一个可执行项会出现在这里。
      </div>
    );
  }

  const nextId = board.next_runnable?.id ?? null;
  const titles = new Map(board.items.map((item) => [item.id, item.title]));

  return (
    <ol className="flex flex-col">
      {board.items.map((item) => {
        const isNext = item.id === nextId;
        return (
          <li
            className={`flex items-start gap-3 border-b border-(--line)/60 py-2 last:border-b-0 ${
              isNext ? "bg-(--accent)/5" : ""
            }`}
            key={item.id}
          >
            <span className="mt-0.5 w-5 shrink-0 text-right font-mono text-[11px] text-(--text-5)">
              {item.step_index + 1}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span className="min-w-0 truncate text-sm text-(--text-2)">{item.title}</span>
                <span
                  className={`rounded border bg-(--fill-1) px-1.5 py-0.5 text-[11px] ${STATUS_TONES[item.status]}`}
                >
                  {STATUS_LABELS[item.status]}
                </span>
                {isNext ? (
                  <span className="rounded border border-(--accent)/40 bg-(--fill-1) px-1.5 py-0.5 text-[11px] text-(--accent)">
                    下一步
                  </span>
                ) : null}
              </div>
              {item.description ? (
                <p className="mt-0.5 line-clamp-2 text-xs leading-5 text-(--text-4)">
                  {item.description}
                </p>
              ) : null}
              <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-(--text-5)">
                {item.depends_on.length > 0 ? (
                  <span>
                    依赖 {item.depends_on.map((id) => titles.get(id) ?? id).join("、")}
                  </span>
                ) : null}
                {item.verify_command ? (
                  <code className="rounded border border-(--line) bg-(--fill-2) px-1.5 py-0.5 font-mono text-[10px] text-(--text-4)">
                    {item.verify_command}
                  </code>
                ) : null}
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
