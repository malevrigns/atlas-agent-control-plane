import { AlertCircle, Check, ClipboardCheck, Loader2 } from "lucide-react";
import { useMemo } from "react";

import type { AgentPlan, SessionEventItem } from "../../types";
import { MarkdownContent } from "../markdown-content";
import { AgentAvatar } from "./agent-avatar";
import { StepCard } from "./step-card";
import type { StepView } from "./types";
import {
  buildToolObservation,
  buildStepViews,
  getString,
  parseToolOutput,
} from "./view-model";

type AgentRunBlockProps = {
  events: SessionEventItem[];
  finalEvent: SessionEventItem | null;
  onSelectToolEvent: (eventId: string) => void;
  onOpenStep: (step: StepView) => void;
  plan: AgentPlan;
  planning: boolean;
  selectedToolEventId: string | null;
};

export function AgentRunBlock({
  events,
  finalEvent,
  onSelectToolEvent,
  onOpenStep,
  plan,
  planning,
  selectedToolEventId,
}: AgentRunBlockProps) {
  const steps = useMemo(() => buildStepViews(plan, events), [events, plan]);
  const runningStep = steps.find((step) => step.status === "running") ?? null;
  const activeStep = finalEvent
    ? null
    : runningStep ?? steps.find((step) => step.status === "pending") ?? null;
  const failed = finalEvent?.type === "task_error";

  return (
    <div className="grid gap-4">
      <div className="flex gap-3">
        <AgentAvatar />
        <div className="max-w-5xl pt-1">
          <div className="text-base font-semibold text-blue-400">AtlasAgent</div>
          <p className="mt-3 text-base leading-8 text-zinc-400">
            我会按“{plan.title}”推进任务。执行过程中会持续展示步骤进度、
            工具调用和最终结果，点击工具节点可以查看右侧详情。
          </p>
        </div>
      </div>

      <div className="ml-4 border-l border-dashed border-zinc-800/90 pl-7">
        <div className="mb-2 flex items-center gap-3 px-2 py-1">
          <StepBadge failed={failed} running={planning || Boolean(runningStep)} />
          <p className="truncate text-sm font-medium text-zinc-500">
            {plan.goal || "正在按计划执行任务"}
          </p>
        </div>
        <div className="grid gap-3 py-3">
          {steps.map((step, index) => (
            <StepCard
              highlighted={activeStep?.id === step.id}
              index={index}
              key={step.id}
              onOpenStep={onOpenStep}
              onSelectToolEvent={onSelectToolEvent}
              selectedToolEventId={selectedToolEventId}
              step={step}
            />
          ))}
        </div>
      </div>

      {finalEvent ? <FinalAnswer event={finalEvent} steps={steps} /> : null}
    </div>
  );
}

function FinalAnswer({
  event,
  steps,
}: {
  event: SessionEventItem;
  steps: StepView[];
}) {
  const failed = event.type === "task_error";
  const eventAnswer = getString(event.payload.final_answer);
  const userMessage = getString(event.payload.user_message);
  const suggestion = getString(event.payload.suggestion);
  const requestId = getString(event.payload.request_id);
  const taskId = getString(event.payload.task_id);
  const firstAnswer = steps
    .map((step) => parseToolOutput(step.toolEvent))
    .find((output) => output?.final_answer)?.final_answer;
  const fallbackAnswer = buildFallbackFinalAnswer(steps);

  return (
    <div className="flex gap-4">
      <AgentAvatar />
      <div className="max-w-5xl pt-1">
        <div className="text-sm font-semibold text-blue-400">AtlasAgent</div>
        <div className="mt-3 rounded-[26px] border border-white/10 bg-white/[0.035] px-5 py-4 text-zinc-300 shadow-xl shadow-black/20">
          <div className="mb-4 flex items-center gap-2 border-b border-white/10 pb-3 text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500">
            <ClipboardCheck className="text-blue-400" size={15} aria-hidden="true" />
            {failed ? "Task Error" : "Final Answer"}
          </div>
          {failed ? (
            <div className="grid gap-3">
              <p className="font-semibold text-rose-100">
                {userMessage || getString(event.payload.message) || "任务执行失败。"}
              </p>
              {suggestion ? (
                <p className="text-base leading-7 text-rose-200/80">
                  建议：{suggestion}
                </p>
              ) : null}
              {requestId || taskId ? (
                <p className="text-sm leading-6 text-zinc-500">
                  {requestId ? `request_id：${requestId}` : ""}
                  {requestId && taskId ? " / " : ""}
                  {taskId ? `task_id：${taskId}` : ""}
                </p>
              ) : null}
            </div>
          ) : eventAnswer ? (
            <MarkdownContent className="text-[15px]" content={eventAnswer} />
          ) : firstAnswer ? (
            <MarkdownContent className="text-[15px]" content={firstAnswer} />
          ) : (
            <MarkdownContent className="text-[15px]" content={fallbackAnswer} />
          )}
        </div>
      </div>
    </div>
  );
}

function buildFallbackFinalAnswer(steps: StepView[]) {
  const completedSteps = steps.filter((step) => step.status === "completed");
  const observations = completedSteps
    .map((step, index) => ({
      index: index + 1,
      observation: buildToolObservation(step),
      step,
    }))
    .filter((item) => item.observation.brief);

  if (!observations.length) {
    return "任务已完成。你可以点击步骤中的工具详情查看每次调用的输入和输出。";
  }

  const lines = observations.map(({ index, observation, step }) => {
    const pills = observation.pills.length
      ? `  \n  相关结果：${observation.pills.slice(0, 3).join("、")}`
      : "";
    return `${index}. **${step.title}**：${observation.brief}${pills}`;
  });

  return [
    "任务已完成，我按计划完成了这些步骤：",
    "",
    ...lines,
    "",
    "你可以点击每个步骤里的工具节点，在右侧查看来源、参数、截图、终端输出或协作详情。",
  ].join("\n");
}

function StepBadge({ failed, running }: { failed: boolean; running: boolean }) {
  if (failed) {
    return (
      <span className="flex h-8 w-8 items-center justify-center rounded-full bg-rose-500 text-white">
        <AlertCircle size={18} aria-hidden="true" />
      </span>
    );
  }
  if (running) {
    return (
      <span className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-500 text-white">
        <Loader2 className="animate-spin" size={18} aria-hidden="true" />
      </span>
    );
  }
  return (
    <span className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-500 text-white">
      <Check size={18} aria-hidden="true" />
    </span>
  );
}
