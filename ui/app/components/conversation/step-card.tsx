import {
  AlertCircle,
  Check,
  ChevronDown,
  ChevronUp,
  Circle,
  Loader2,
  Maximize2,
  Search,
  Wrench,
} from "lucide-react";
import { useEffect, useState } from "react";

import type { StepView } from "./types";
import {
  buildToolPills,
  buildToolObservation,
  getStepDisplaySummary,
  getStatusClass,
  getStatusLabel,
  parseToolOutput,
} from "./view-model";

type StepCardProps = {
  highlighted: boolean;
  index: number;
  onOpenStep: (step: StepView) => void;
  onSelectToolEvent: (eventId: string) => void;
  selectedToolEventId: string | null;
  step: StepView;
};

export function StepCard({
  highlighted,
  index,
  onOpenStep,
  onSelectToolEvent,
  selectedToolEventId,
  step,
}: StepCardProps) {
  const running = step.status === "running";
  const completed = step.status === "completed";
  const failed = step.status === "failed";
  const output = parseToolOutput(step.toolEvent);
  const observation = buildToolObservation(step);
  const toolPills = buildToolPills(step, output);
  const errorMessage =
    typeof step.errorEvent?.payload.user_message === "string"
      ? step.errorEvent.payload.user_message
      : "";
  const errorSuggestion =
    typeof step.errorEvent?.payload.suggestion === "string"
      ? step.errorEvent.payload.suggestion
      : "";
  const [expanded, setExpanded] = useState(running || highlighted);
  const showToolSection = expanded && (running || completed || Boolean(step.toolEvent));

  useEffect(() => {
    if (running || highlighted) {
      setExpanded(true);
    }
  }, [highlighted, running]);

  return (
    <div className={`relative ${highlighted ? "stream-in" : ""}`}>
      <div className="absolute -left-[43px] top-2 flex h-7 w-7 items-center justify-center rounded-full border border-zinc-800 bg-[#08090d] shadow-lg shadow-black/30">
        {completed ? (
          <Check className="text-blue-400" size={17} aria-hidden="true" />
        ) : running ? (
          <Loader2
            className="animate-spin text-blue-400"
            size={17}
            aria-hidden="true"
          />
        ) : failed ? (
          <AlertCircle className="text-rose-400" size={17} aria-hidden="true" />
        ) : (
          <Circle className="text-zinc-600" size={12} aria-hidden="true" />
        )}
      </div>

      <div
        className={`grid gap-2 rounded-xl border p-1 transition ${
          highlighted
            ? "border-blue-500/35 bg-blue-500/[0.055] shadow-2xl shadow-blue-950/20"
            : "border-transparent bg-transparent hover:bg-white/[0.035]"
        }`}
      >
        <div
          className="flex w-full items-start justify-between gap-4 rounded-xl px-3 py-2 text-left outline-none transition"
        >
          <button
            aria-label={`查看步骤详情：${step.title}`}
            className="min-w-0 flex-1 text-left outline-none focus-visible:ring-2 focus-visible:ring-blue-500/60"
            onClick={() => onOpenStep(step)}
            type="button"
          >
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-blue-400">
                {String(index + 1).padStart(2, "0")}
              </span>
              <h4 className="truncate text-base font-semibold leading-7 text-zinc-50">
                {step.title}
              </h4>
              <Maximize2
                className="shrink-0 text-zinc-600"
                size={14}
                aria-hidden="true"
              />
            </div>
            <p className="mt-2 line-clamp-2 text-sm leading-6 text-zinc-400">
              {getStepDisplaySummary(step)}
            </p>
          </button>
          <div className="flex shrink-0 items-center gap-2">
            <span className={getStatusClass(step.status)}>
              {getStatusLabel(step.status)}
            </span>
            <button
              aria-label={expanded ? "折叠步骤" : "展开步骤"}
              className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-white/10 bg-white/[0.04] text-zinc-400 transition hover:border-blue-500/40 hover:text-zinc-100"
              onClick={() => setExpanded((value) => !value)}
              title={expanded ? "折叠步骤" : "展开步骤"}
              type="button"
            >
              {expanded ? (
                <ChevronUp size={15} aria-hidden="true" />
              ) : (
                <ChevronDown size={15} aria-hidden="true" />
              )}
            </button>
          </div>
        </div>

        {showToolSection ? (
          <div className="ml-3 grid max-w-3xl gap-3 border-l border-dashed border-zinc-800/90 pl-4">
            <div className="inline-flex w-fit items-center gap-2 rounded-lg border border-white/10 bg-white/[0.06] px-3 py-1.5 text-sm font-medium text-zinc-400">
              <Wrench
                className={running ? "text-blue-400 animate-pulse" : "text-blue-400"}
                size={16}
                aria-hidden="true"
              />
              {running ? "正在使用工具" : observation.title}
            </div>
            <div className="grid gap-2">
              {toolPills.map((label) => (
                <button
                  aria-label={`查看工具详情：${label}`}
                  className="inline-flex w-fit max-w-full items-center gap-2 rounded-lg border border-white/10 bg-white/[0.055] px-3 py-1.5 text-left text-sm font-medium text-zinc-500 transition hover:border-blue-500/40 hover:bg-blue-500/10 hover:text-zinc-100"
                  disabled={!step.toolEvent}
                  key={label}
                  onClick={() =>
                    step.toolEvent && onSelectToolEvent(step.toolEvent.id)
                  }
                  type="button"
                >
                  <Search
                    className="shrink-0 text-blue-400"
                    size={17}
                    aria-hidden="true"
                  />
                  <span className="truncate">{label}</span>
                </button>
              ))}
            </div>
          </div>
        ) : null}

        {failed && (errorMessage || errorSuggestion) ? (
          <div className="ml-3 max-w-3xl rounded-xl border border-rose-500/25 bg-rose-500/10 px-4 py-3 text-sm leading-6 text-rose-100">
            {errorMessage ? <p className="font-semibold">{errorMessage}</p> : null}
            {errorSuggestion ? (
              <p className="mt-1 text-rose-200/80">建议：{errorSuggestion}</p>
            ) : null}
          </div>
        ) : null}

        {step.toolEvent ? (
          <button
            aria-label="查看工具详情"
            className={`ml-3 w-fit rounded-lg border px-3 py-1.5 text-sm font-medium transition ${
              selectedToolEventId === step.toolEvent.id
                ? "border-blue-400 bg-blue-500/15 text-blue-200"
                : "border-white/10 bg-white/[0.04] text-zinc-400 hover:border-blue-500/40 hover:text-zinc-100"
            }`}
            onClick={() => onSelectToolEvent(step.toolEvent!.id)}
            type="button"
          >
            查看工具详情
          </button>
        ) : null}
      </div>
    </div>
  );
}
