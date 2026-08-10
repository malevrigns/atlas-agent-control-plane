import type { ChatMessage } from "../../types";
import { MarkdownContent } from "../markdown-content";
import { AgentAvatar } from "./agent-avatar";
import { ReasoningBlock } from "./reasoning-block";

type MessageBubbleProps = {
  message: ChatMessage;
  /** 该回答对应的模型推理过程（来自 task_done 事件），有则可展开查看。 */
  reasoning?: string;
};

export function MessageBubble({ message, reasoning }: MessageBubbleProps) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end pt-2">
        <div className="max-w-[82%] break-words rounded-2xl border border-(--line) bg-(--surface-4)/90 px-5 py-3 text-base font-semibold leading-7 text-(--text-1) shadow-xl shadow-black/25 max-md:max-w-full">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3">
      <AgentAvatar />
      <div className="min-w-0 max-w-4xl flex-1 pt-1">
        <div className="text-base font-semibold text-(--accent)">AtlasAgent</div>
        {reasoning ? (
          <div className="mt-3">
            <ReasoningBlock reasoning={reasoning} />
          </div>
        ) : null}
        <MarkdownContent className="mt-3" content={message.content} />
      </div>
    </div>
  );
}
