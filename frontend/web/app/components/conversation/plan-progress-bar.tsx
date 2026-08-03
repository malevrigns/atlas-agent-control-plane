"use client";

import { Check, ChevronDown, ChevronUp, Clock3, Loader2, XCircle } from "lucide-react";
import { useEffect, useState } from "react";

import type { PlanProgressView } from "./types";

type PlanProgressBarProps = {
  progress: PlanProgressView | null;
};

export function PlanProgressBar({ progress }: PlanProgressBarProps) {
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (progress?.expandedByDefault) {
      setExpanded(true);
    }
  }, [progress?.expandedByDefault, progress?.title]);

  if (!progress || progress.totalCount === 0) {
    return null;
  }

  const activeTitle =
    progress.activeStep?.title ||
    progress.activeStep?.description ||
    (progress.failed ? "任务执行失败" : "任务已完成");

  return (
    <div className="mb-3 overflow-hidden rounded-2xl border border-white/10 bg-[#111421]/92 shadow-2xl shadow-black/25 ring-1 ring-blue-500/10 backdrop-blur-2xl">
      <button
        aria-expanded={expanded}
        className="flex min-h-11 w-full items-center justify-between gap-3 px-4 py-2.5 text-left"
        onClick={() => setExpanded((value) => !value)}
        type="button"
      >
        <div className="flex min-w-0 items-center gap-3">
          <ProgressIcon failed={progress.failed} running={progress.running} />
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-zinc-200">
              {activeTitle}
            </div>
            <div className="mt-0.5 truncate text-xs text-zinc-500">
              {progress.title}
            </div>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-3 text-sm text-zinc-400">
          <span>
            {progress.completedCount} / {progress.totalCount}
          </span>
          {expanded ? (
            <ChevronDown size={17} aria-hidden="true" />
          ) : (
            <ChevronUp size={17} aria-hidden="true" />
          )}
        </div>
      </button>

      {expanded ? (
        <div className="border-t border-white/10 bg-black/10 px-4 py-3">
          <div className="grid gap-2">
            {progress.steps.map((step, index) => (
              <div
                className="flex items-start gap-3 rounded-xl px-2 py-2 text-sm text-zinc-400"
                key={step.id}
              >
                <StepStatusIcon status={step.status} />
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium text-zinc-200">
                    {index + 1}. {step.title}
                  </div>
                  <div className="mt-1 line-clamp-2 text-xs leading-5 text-zinc-500">
                    {step.summary || step.expected_output || step.description}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function ProgressIcon({
  failed,
  running,
}: {
  failed: boolean;
  running: boolean;
}) {
  if (failed) {
    return (
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-rose-500/15 text-rose-300">
        <XCircle size={16} aria-hidden="true" />
      </span>
    );
  }
  if (running) {
    return (
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-blue-500/15 text-blue-300">
        <Loader2 className="animate-spin" size={16} aria-hidden="true" />
      </span>
    );
  }
  return (
    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-300">
      <Check size={16} aria-hidden="true" />
    </span>
  );
}

function StepStatusIcon({ status }: { status: string }) {
  if (status === "completed") {
    return (
      <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-300">
        <Check size={13} aria-hidden="true" />
      </span>
    );
  }
  if (status === "running") {
    return (
      <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-blue-500/15 text-blue-300">
        <Loader2 className="animate-spin" size={13} aria-hidden="true" />
      </span>
    );
  }
  if (status === "failed") {
    return (
      <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-rose-500/15 text-rose-300">
        <XCircle size={13} aria-hidden="true" />
      </span>
    );
  }
  return (
    <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-white/[0.06] text-zinc-500">
      <Clock3 size={13} aria-hidden="true" />
    </span>
  );
}
