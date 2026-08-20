import { ArrowDown } from "lucide-react";

import { AgentRunBlock } from "./conversation/agent-run-block";
import { MessageBubble } from "./conversation/message-bubble";
import { ReasoningBlock } from "./conversation/reasoning-block";
import {
  ErrorBlock,
  RunningBlock,
  TaskStatusCard,
  TimelineEmptyState,
  TimelineLoadingState,
} from "./conversation/timeline-state";
import {
  buildAgentRunViewModel,
  buildReasoningMap,
} from "./conversation/view-model";
import { useAutoScroll } from "../hooks/use-auto-scroll";
import { useTypewriter } from "../hooks/use-typewriter";
import type {
  AgentPlan,
  AgentTaskItem,
  ChatMessage,
  LoadState,
  SessionEventItem,
} from "../types";

type ConversationTimelineProps = {
  events: LoadState<SessionEventItem[]>;
  liveAnswer: string;
  liveThinking: string;
  messages: LoadState<ChatMessage[]>;
  onSelectToolEvent: (eventId: string) => void;
  plan: AgentPlan | null;
  planning: boolean;
  executing: boolean;
  selectedToolEventId: string | null;
  task: AgentTaskItem | null;
  onRetry: () => void;
};

export function ConversationTimeline({
  events,
  liveAnswer,
  liveThinking,
  messages,
  onSelectToolEvent,
  plan,
  planning,
  executing,
  selectedToolEventId,
  task,
  onRetry,
}: ConversationTimelineProps) {
  const readyMessages = messages.type === "ready" ? messages.data : [];
  // 会话标识与最新用户消息：驱动“切会话跳底部 / 追问锚定到顶部”的滚动策略。
  const sessionKey = readyMessages[0]?.session_id ?? "empty";
  const lastUserMessageId =
    [...readyMessages].reverse().find((message) => message.role === "user")?.id ??
    null;
  const {
    anchorSpacer,
    bottomRef,
    handleScroll,
    pinnedToBottom,
    scrollRef,
    scrollToBottom,
  } = useAutoScroll({ sessionKey, lastUserMessageId });
  // 思考流打字机节流：模型思考瞬间灌入大段文本，按稳定速度放出更易读。
  const pacedThinking = useTypewriter(liveThinking);

  if (messages.type === "loading" || events.type === "loading") {
    return <TimelineLoadingState />;
  }

  if (messages.type === "error") {
    return <ErrorBlock message={messages.message} />;
  }

  if (events.type === "error") {
    return <ErrorBlock message={events.message} />;
  }

  const viewModel = buildAgentRunViewModel(messages.data, events.data);
  const reasoningMap = buildReasoningMap(events.type === "ready" ? events.data : []);
  // 执行态只属于最新的任务卡；历史卡片一律静止。
  const lastPlanItemId =
    [...viewModel.timelineItems]
      .reverse()
      .find((item) => item.kind === "plan")?.id ?? null;

  if (viewModel.timelineItems.length === 0 && !liveAnswer && !liveThinking) {
    return <TimelineEmptyState />;
  }

  return (
    <>
      <div className="relative flex-1 min-h-0">
        {/* overflow-anchor:none 关掉浏览器原生滚动锚定——
            否则视口贴底时流式内容增长，浏览器会自动跟滚到底部，
            覆盖我们"锁定在用户消息"的滚动策略。 */}
        <div
          className="h-full overflow-x-hidden overflow-y-auto px-8 py-8 [overflow-anchor:none] max-md:px-4"
          onScroll={handleScroll}
          ref={scrollRef}
        >
          {/* 宽内容（代码块、表格）在自己的容器内横向滚动；
              [&>*]:min-w-0 阻止 grid 子项被内容撑宽引发整体横向滚动。 */}
          <div className="mx-auto grid w-full max-w-3xl gap-7 [&>*]:min-w-0">
            {viewModel.timelineItems.map((item) =>
              item.kind === "message" ? (
                <div
                  className="stream-in scroll-mt-2"
                  data-message-anchor={item.message.id}
                  key={item.id}
                >
                  <MessageBubble
                    message={item.message}
                    reasoning={reasoningMap.get(item.message.id)}
                  />
                </div>
              ) : (
                <div className="stream-in" key={item.id}>
                  <AgentRunBlock
                    events={events.data}
                    executing={executing && item.id === lastPlanItemId}
                    livePlan={plan}
                    onSelectToolEvent={onSelectToolEvent}
                    planEvent={item.event}
                    planning={planning && item.id === lastPlanItemId}
                    selectedToolEventId={selectedToolEventId}
                    onRetry={onRetry}
                  />
                </div>
              ),
            )}
            {pacedThinking ? (
              <div className="stream-in ml-11 max-w-4xl">
                <ReasoningBlock reasoning={pacedThinking} streaming={!liveAnswer} />
              </div>
            ) : null}
            {liveAnswer ? (
              <div className="stream-in">
                <MessageBubble
                  message={{
                    id: "live-answer",
                    session_id: "",
                    role: "assistant",
                    content: liveAnswer,
                    created_at: new Date().toISOString(),
                  }}
                />
              </div>
            ) : null}
            <TaskStatusCard task={task} />
            {planning || executing ? (
              <RunningBlock
                text={
                  planning
                    ? "正在理解任务并生成计划..."
                    : "正在执行计划并同步工具结果..."
                }
              />
            ) : null}
            {/* bottomRef 标记内容末尾（在锚定空白之前）：
                贴底判断与"回到底部"都以它为准，空白只是滚动缓冲。 */}
            <div ref={bottomRef} />
            {/* 锚定后的尾部空白：保证最新提问能顶到视口顶部，回答在下方生长。 */}
            {anchorSpacer ? (
              <div aria-hidden className="h-[calc(100dvh-360px)] shrink-0" />
            ) : null}
          </div>
        </div>
        {!pinnedToBottom ? (
          <button
            aria-label="回到对话底部"
            className="absolute bottom-5 left-1/2 z-20 inline-flex -translate-x-1/2 items-center gap-2 rounded-full border border-(--accent)/30 bg-(--surface-3)/95 px-4 py-2 text-sm font-semibold text-(--accent) shadow-2xl shadow-black/40 backdrop-blur-xl transition hover:border-(--accent)/60"
            onClick={() => scrollToBottom("smooth")}
            type="button"
          >
            <ArrowDown size={15} aria-hidden="true" />
            回到底部
          </button>
        ) : null}
      </div>
    </>
  );
}
