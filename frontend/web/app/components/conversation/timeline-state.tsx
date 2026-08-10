import { Sparkles } from "lucide-react";

import type { AgentTaskItem } from "../../types";
import { AgentAvatar } from "./agent-avatar";

type ErrorBlockProps = {
  message: string;
};

type RunningBlockProps = {
  text: string;
};

type TaskStatusCardProps = {
  task: AgentTaskItem | null;
};

export function TimelineEmptyState() {
  return (
    <div className="flex min-h-0 flex-1 items-center justify-center overflow-y-auto px-8 py-10 text-center max-sm:items-start max-sm:px-5 max-sm:py-6">
      <div className="max-w-xl">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-3xl border border-(--accent)/30 bg-(--accent)/10 text-(--accent) shadow-2xl shadow-blue-950/30 max-sm:h-11 max-sm:w-11 max-sm:rounded-2xl">
          <Sparkles className="max-sm:h-5 max-sm:w-5" size={22} aria-hidden="true" />
        </div>
        <h2 className="mt-5 text-2xl font-semibold text-(--text-1) max-sm:mt-4 max-sm:text-lg">
          直接描述任务，Agent 会开始规划和执行
        </h2>
        <p className="mt-3 text-base leading-7 text-(--text-4) max-sm:text-sm max-sm:leading-6">
          对话区会连续展示任务理解、执行计划、步骤进度、工具调用和最终结果；需要查看细节时，点击工具节点打开右侧工作台。
        </p>
      </div>
    </div>
  );
}

export function TimelineLoadingState() {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-8 py-8 text-sm text-(--text-4) max-sm:px-5 max-sm:py-5">
      对话加载中...
    </div>
  );
}

export function ErrorBlock({ message }: ErrorBlockProps) {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-8 max-sm:p-5">
      <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
        {message}
      </div>
    </div>
  );
}

export function TaskStatusCard({ task }: TaskStatusCardProps) {
  if (
    !task ||
    ["completed", "succeeded", "failed", "stopped", "cancelled"].includes(
      task.status,
    )
  ) {
    return null;
  }

  return (
    <RunningBlock
      text={
        task.status === "waiting"
          ? "后台任务等待外部资源或人工继续"
          : `后台任务正在执行：${task.status}`
      }
    />
  );
}

export function RunningBlock({ text }: RunningBlockProps) {
  return (
    <div className="flex gap-4">
      <AgentAvatar loading />
      <div className="rounded-2xl border border-(--accent)/20 bg-(--accent)/10 px-5 py-4 text-base font-semibold text-(--accent) shadow-2xl shadow-blue-950/20">
        {text}
      </div>
    </div>
  );
}
