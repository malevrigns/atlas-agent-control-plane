"use client";

import {
  Check,
  ChevronDown,
  Clock3,
  Loader2,
  XCircle,
} from "lucide-react";
import { useState } from "react";

import type { StepView } from "./types";
import { getStepDisplaySummary } from "./view-model";

type TaskRunCardProps = {
  title: string;
  steps: StepView[];
  running: boolean;
  failed: boolean;
  selectedToolEventId: string | null;
  onSelectToolEvent: (eventId: string) => void;
};

/**
 * 任务执行卡：一张卡片承载整次运行——
 * 头部是状态与进度（n/m），展开区逐条列出步骤与一行摘要。
 * 运行中实时更新，完成后即最终形态；点击步骤行可打开右侧工具详情。
 */
export function TaskRunCard({
  title,
  steps,
  running,
  failed,
  selectedToolEventId,
  onSelectToolEvent,
}: TaskRunCardProps) {
  const [expanded, setExpanded] = useState(true);
  const completedCount = steps.filter((step) => step.status === "completed").length;

  const headline = failed
    ? "任务执行失败"
    : running
      ? "正在执行任务"
      : "任务已完成";

  return (
    <div className="overflow-hidden rounded-2xl border border-(--line) bg-(--surface) shadow-xl shadow-black/10">
      <button
        aria-expanded={expanded}
        className="flex min-h-14 w-full items-center justify-between gap-3 px-5 py-3.5 text-left"
        onClick={() => setExpanded((value) => !value)}
        type="button"
      >
        <div className="flex min-w-0 items-center gap-3">
          <HeadIcon failed={failed} running={running} />
          <div className="min-w-0">
            <div className="text-[15px] font-semibold text-(--text-1)">{headline}</div>
            <div className="mt-0.5 truncate text-xs text-(--text-4)">{title}</div>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-3 text-sm text-(--text-3)">
          <span>
            {completedCount} / {steps.length}
          </span>
          <ChevronDown
            aria-hidden="true"
            className={`transition-transform ${expanded ? "rotate-180" : ""}`}
            size={16}
          />
        </div>
      </button>

      {expanded ? (
        <div className="grid gap-4 border-t border-(--line-soft) px-5 py-4">
          {steps.map((step, index) => {
            const toolEventId = step.toolEvent?.id ?? null;
            const selected = Boolean(toolEventId) && toolEventId === selectedToolEventId;
            return (
              <button
                className={`flex items-start gap-3 rounded-xl p-1.5 text-left transition ${
                  selected
                    ? "bg-(--accent)/10 ring-1 ring-(--accent)/40"
                    : toolEventId
                      ? "hover:bg-(--fill-1)"
                      : "cursor-default"
                }`}
                key={step.id}
                onClick={() => {
                  if (toolEventId) onSelectToolEvent(toolEventId);
                }}
                title={toolEventId ? "查看该步骤的工具详情" : undefined}
                type="button"
              >
                <StepIcon status={step.status} />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold leading-6 text-(--text-1)">
                    {index + 1}. {step.title}
                  </div>
                  <p className="mt-0.5 line-clamp-2 text-sm leading-6 text-(--text-4)">
                    {getStepDisplaySummary(step)}
                  </p>
                </div>
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

function HeadIcon({ failed, running }: { failed: boolean; running: boolean }) {
  if (failed) {
    return (
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-rose-500/15 text-rose-400">
        <XCircle size={18} aria-hidden="true" />
      </span>
    );
  }
  if (running) {
    return (
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-(--accent)/15 text-(--accent)">
        <Loader2 className="animate-spin" size={18} aria-hidden="true" />
      </span>
    );
  }
  return (
    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-500">
      <Check size={18} aria-hidden="true" />
    </span>
  );
}

function StepIcon({ status }: { status: string }) {
  if (status === "completed") {
    return (
      <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-500">
        <Check size={14} aria-hidden="true" />
      </span>
    );
  }
  if (status === "running") {
    return (
      <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-(--accent)/15 text-(--accent)">
        <Loader2 className="animate-spin" size={14} aria-hidden="true" />
      </span>
    );
  }
  if (status === "failed") {
    return (
      <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-rose-500/15 text-rose-400">
        <XCircle size={14} aria-hidden="true" />
      </span>
    );
  }
  return (
    <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-(--fill-2) text-(--text-4)">
      <Clock3 size={14} aria-hidden="true" />
    </span>
  );
}
