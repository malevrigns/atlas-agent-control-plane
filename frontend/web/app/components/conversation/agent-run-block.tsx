import { ClipboardCheck } from "lucide-react";
import { useMemo, useState } from "react";

import type { AgentPlan, SessionEventItem } from "../../types";
import { MarkdownContent } from "../markdown-content";
import { AgentAvatar } from "./agent-avatar";
import { ReasoningBlock } from "./reasoning-block";
import { TaskRunCard } from "./task-run-card";
import { ToolCallLog } from "./tool-call-log";
import type { StepView } from "./types";
import {
  buildStepViews,
  buildToolObservation,
  getString,
  parsePlanPayload,
  parseToolOutput,
} from "./view-model";

type AgentRunBlockProps = {
  events: SessionEventItem[];
  /** 仅最新一张卡在会话执行中时为 true——历史卡片永远是 false。 */
  executing: boolean;
  /** store 里实时更新的计划（执行中步骤状态来自 SSE），仅当 id 匹配时覆盖事件快照。 */
  livePlan: AgentPlan | null;
  onSelectToolEvent: (eventId: string) => void;
  /** 本卡片对应的 plan_created 事件——一张卡只负责一次任务运行。 */
  planEvent: SessionEventItem;
  planning: boolean;
  selectedToolEventId: string | null;
  onRetry?: () => void;
};

export function AgentRunBlock({
  events,
  executing,
  livePlan,
  onSelectToolEvent,
  planEvent,
  planning,
  selectedToolEventId,
  onRetry,
}: AgentRunBlockProps) {
  const plan = useMemo(() => {
    const parsed = parsePlanPayload(planEvent.payload);
    return livePlan && livePlan.id === parsed.id ? livePlan : parsed;
  }, [livePlan, planEvent]);
  // 只认属于本次运行的终结事件：优先按 plan_id 匹配；
  // 旧数据没有 plan_id 时退回时间窗（本计划之后、下一个计划之前），
  // 并排除直答路径的 task_done（mode=chat），避免旧任务卡吞掉新对话的结果。
  const finalEvent = useMemo(() => {
    const terminals = events.filter(
      (event) => event.type === "task_done" || event.type === "task_error",
    );
    if (plan.id) {
      const byPlanId = terminals.find(
        (event) => getString(event.payload.plan_id) === plan.id,
      );
      if (byPlanId) {
        return byPlanId;
      }
    }
    const nextPlanAt = events.find(
      (event) =>
        event.type === "plan_created" && event.created_at > planEvent.created_at,
    )?.created_at;
    return (
      terminals.find(
        (event) =>
          event.created_at > planEvent.created_at &&
          (!nextPlanAt || event.created_at < nextPlanAt) &&
          getString(event.payload.mode) !== "chat",
      ) ?? null
    );
  }, [events, plan.id, planEvent]);
  const steps = useMemo(() => buildStepViews(plan, events), [events, plan]);
  const runningStep = steps.find((step) => step.status === "running") ?? null;
  const failed = finalEvent?.type === "task_error";
  // 不用 steps.some(pending) 推断运行中——被中断的历史任务没有终结事件，
  // 会导致旧卡片永远转圈；执行态只信当前会话的 planning/executing。
  const running = !finalEvent && (planning || executing || Boolean(runningStep));
  // 规划阶段的模型思考已随 plan_created 落库，这里提供事后回看。
  const planReasoning = getString(planEvent.payload.reasoning);

  return (
    <div className="grid gap-4 [&>*]:min-w-0">
      {planReasoning ? (
        <div className="ml-11 max-w-4xl">
          <ReasoningBlock reasoning={planReasoning} />
        </div>
      ) : null}

      <div className="flex gap-3">
        <AgentAvatar />
        <div className="min-w-0 flex-1 pt-1">
          <TaskRunCard
            failed={failed}
            onSelectToolEvent={onSelectToolEvent}
            running={running}
            selectedToolEventId={selectedToolEventId}
            steps={steps}
            title={plan.title || plan.goal || "任务执行计划"}
          />
        </div>
      </div>

      <ToolCallLog events={events} running={running} />

      {finalEvent ? <FinalAnswer event={finalEvent} steps={steps} onRetry={onRetry} /> : null}
    </div>
  );
}

function FinalAnswer({
  event,
  steps,
  onRetry,
}: {
  event: SessionEventItem;
  steps: StepView[];
  onRetry?: () => void;
}) {
  const failed = event.type === "task_error";
  const [copied, setCopied] = useState(false);
  const eventAnswer = getString(event.payload.final_answer);
  const answerReasoning = getString(event.payload.reasoning);
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
      <div className="min-w-0 flex-1 pt-1">
        <div className="text-sm font-semibold text-(--accent)">AtlasAgent</div>
        <div className="mt-3 rounded-[26px] border border-(--line) bg-(--fill-1) px-5 py-4 text-(--text-2) shadow-xl shadow-black/20">
          <div className="mb-4 flex items-center gap-2 border-b border-(--line) pb-3 text-xs font-semibold uppercase tracking-[0.18em] text-(--text-4)">
            <ClipboardCheck className="text-(--accent)" size={15} aria-hidden="true" />
            {failed ? "Task Error" : "Final Answer"}
          </div>
          {!failed && answerReasoning ? (
            <div className="mb-4">
              <ReasoningBlock reasoning={answerReasoning} />
            </div>
          ) : null}
          {failed ? (
            <div className="grid gap-3">
              <p className="font-semibold text-(--error-text)">
                {userMessage || getString(event.payload.message) || "任务执行失败。"}
              </p>
              {suggestion ? (
                <p className="text-base leading-7 text-(--text-3)">
                  建议：{suggestion}
                </p>
              ) : null}
              {requestId || taskId ? (
                <div className="flex flex-wrap items-center gap-2 text-sm leading-6 text-(--text-3)">
                  <span>
                    {requestId ? `request_id：${requestId}` : ""}
                    {requestId && taskId ? " / " : ""}
                    {taskId ? `task_id：${taskId}` : ""}
                  </span>
                  <button
                    className="rounded-md border border-(--line) px-2 py-0.5 text-xs text-(--text-3) transition hover:border-(--accent)/50 hover:text-(--text-1)"
                    onClick={() => {
                      const id = [requestId, taskId].filter(Boolean).join(" / ");
                      navigator.clipboard?.writeText(id).then(() => {
                        setCopied(true);
                        window.setTimeout(() => setCopied(false), 1500);
                      });
                    }}
                    type="button"
                  >
                    {copied ? "已复制" : "复制"}
                  </button>
                </div>
              ) : null}
              {onRetry ? (
                <button
                  className="mt-1 w-fit rounded-lg border border-(--accent)/40 bg-(--accent)/10 px-4 py-2 text-sm font-medium text-(--accent) transition hover:bg-(--accent)/20"
                  onClick={onRetry}
                  type="button"
                >
                  重新执行
                </button>
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

