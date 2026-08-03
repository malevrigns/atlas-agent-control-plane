import { Loader2, Pause, SendHorizontal } from "lucide-react";

import { workspaceSurface } from "../lib/design-tokens";

type ChatInputProps = {
  disabled: boolean;
  draft: string;
  onDraftChange: (value: string) => void;
  onSend: () => void;
  sending: boolean;
};

export function ChatInput({
  disabled,
  draft,
  onDraftChange,
  onSend,
  sending,
}: ChatInputProps) {
  return (
    <form
      className="mx-auto max-w-5xl"
      onSubmit={(event) => {
        event.preventDefault();
        onSend();
      }}
    >
      <div
        className={`rounded-[28px] p-4 ring-1 ring-blue-500/15 max-sm:p-3 ${workspaceSurface.panelStrong}`}
      >
        <textarea
          aria-label="任务输入框"
          className="max-h-40 min-h-24 w-full resize-none border-0 bg-transparent px-2 py-2 text-lg font-medium leading-8 text-zinc-100 outline-none placeholder:text-zinc-600 disabled:bg-transparent max-sm:min-h-16 max-sm:text-base max-sm:leading-6"
          disabled={disabled || sending}
          onChange={(event) => onDraftChange(event.target.value)}
          placeholder={disabled ? "先创建或选择一个会话" : "分配一个任务或提问任何问题..."}
          value={draft}
        />
        <div className="mt-2 flex items-center justify-end max-sm:mt-1">
          <button
            aria-label={sending ? "任务发送中" : "发送任务"}
            className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full border border-white/10 bg-white/[0.08] text-zinc-100 shadow-lg shadow-black/30 transition hover:border-blue-500/40 hover:bg-blue-500 disabled:cursor-not-allowed disabled:bg-white/[0.04] disabled:text-zinc-700 disabled:shadow-none max-sm:h-10 max-sm:w-10"
            disabled={disabled || sending}
            title="发送并开始执行"
            type="submit"
          >
            {sending ? (
              <Loader2 className="animate-spin" size={21} aria-hidden="true" />
            ) : draft.trim() ? (
              <SendHorizontal size={21} aria-hidden="true" />
            ) : (
              <Pause size={21} aria-hidden="true" />
            )}
          </button>
        </div>
      </div>
    </form>
  );
}
