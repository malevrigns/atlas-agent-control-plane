import type { ChatMessage } from "../../types";
import { MarkdownContent } from "../markdown-content";
import { AgentAvatar } from "./agent-avatar";

type MessageBubbleProps = {
  message: ChatMessage;
};

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end pt-2">
        <div className="max-w-[82%] rounded-2xl border border-white/10 bg-[#151722]/90 px-5 py-3 text-base font-semibold leading-7 text-zinc-50 shadow-xl shadow-black/25 max-md:max-w-full">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3">
      <AgentAvatar />
      <div className="max-w-4xl pt-1">
        <div className="text-base font-semibold text-blue-400">AtlasAgent</div>
        <MarkdownContent className="mt-3" content={message.content} />
      </div>
    </div>
  );
}
