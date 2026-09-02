"use client";

import {
  Ban,
  CircleAlert,
  CircleCheck,
  ClipboardList,
  Lightbulb,
  ListChecks,
  Loader2,
  ShieldCheck,
  Terminal,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { formatDate } from "../../lib/format";
import type { TraceEntry, TracePhase } from "../../lib/run-trace";

const PHASE_ICONS: Record<TracePhase, LucideIcon> = {
  plan: ClipboardList,
  step: ListChecks,
  tool: Terminal,
  reflect: Lightbulb,
  gate: ShieldCheck,
  todo: ListChecks,
  done: CircleCheck,
  error: CircleAlert,
};

const PHASE_TONES: Record<TracePhase, string> = {
  plan: "border-(--line) text-(--text-3)",
  step: "border-(--line) text-(--text-3)",
  tool: "border-(--accent)/40 text-(--accent)",
  reflect: "border-amber-400/40 text-(--warn-text)",
  gate: "border-(--accent)/40 text-(--accent)",
  todo: "border-(--line) text-(--text-3)",
  done: "border-emerald-400/50 text-(--success-text)",
  error: "border-red-400/50 text-(--error-text)",
};

type RunTimelineProps = {
  entries: TraceEntry[];
  loading: boolean;
};

/**
 * 运行轨迹：agent 这一趟到底做了什么。
 *
 * 与对话时间线的分工是清楚的——那边看"说了什么"，这边看"做了什么"。
 * 长程任务跑几小时、上百条事件，所以这里只给密集单行 + 必要时第二行说明，
 * 不做气泡、不做卡片套卡片。
 */
export function RunTimeline({ entries, loading }: RunTimelineProps) {
  if (loading) {
    return (
      <div className="flex items-center gap-2 px-1 py-6 text-sm text-(--text-4)">
        <Loader2 className="animate-spin" size={15} aria-hidden="true" />
        读取执行轨迹…
      </div>
    );
  }

  if (entries.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-(--line) px-4 py-6 text-sm text-(--text-4)">
        这个任务还没有执行事件。计划、步骤、工具调用与门禁结论都会出现在这里。
      </div>
    );
  }

  return (
    <ol className="flex flex-col">
      {entries.map((entry) => {
        const Icon = PHASE_ICONS[entry.phase];
        const failed = entry.verdict === "failed";
        return (
          <li
            className="flex items-start gap-3 border-b border-(--line)/60 py-2 last:border-b-0"
            key={entry.id}
          >
            <span
              aria-hidden="true"
              className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md border bg-(--fill-1) ${PHASE_TONES[entry.phase]}`}
            >
              <Icon size={13} aria-hidden="true" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                <span
                  className={`text-sm ${failed ? "text-red-300" : "text-(--text-2)"}`}
                >
                  {entry.title}
                </span>
                {entry.verdict === "skipped" ? (
                  <span className="flex items-center gap-1 text-[11px] text-(--text-5)">
                    <Ban size={10} aria-hidden="true" />
                    跳过
                  </span>
                ) : null}
                <span className="ml-auto shrink-0 font-mono text-[11px] text-(--text-5)">
                  {formatDate(entry.createdAt)}
                </span>
              </div>
              {entry.detail ? (
                <p className="mt-0.5 line-clamp-2 break-words text-xs leading-5 text-(--text-4)">
                  {entry.detail}
                </p>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
