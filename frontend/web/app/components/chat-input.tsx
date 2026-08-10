import { Loader2, SendHorizontal } from "lucide-react";
import { useEffect, useRef } from "react";

import { workspaceSurface } from "../lib/design-tokens";

type ChatInputProps = {
  disabled: boolean;
  draft: string;
  onDraftChange: (value: string) => void;
  onSend: () => void;
  sending: boolean;
};

const MAX_INPUT_HEIGHT = 176;

export function ChatInput({
  disabled,
  draft,
  onDraftChange,
  onSend,
  sending,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  // 随内容自动伸缩：先归零再按内容高度设置，超过上限后内部滚动。
  useEffect(() => {
    const element = textareaRef.current;
    if (!element) {
      return;
    }
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, MAX_INPUT_HEIGHT)}px`;
    element.style.overflowY =
      element.scrollHeight > MAX_INPUT_HEIGHT ? "auto" : "hidden";
  }, [draft]);

  return (
    <form
      className="mx-auto max-w-5xl"
      onSubmit={(event) => {
        event.preventDefault();
        onSend();
      }}
    >
      <div
        className={`aurora-shell ${sending ? "aurora-active" : ""} flex items-end gap-2 rounded-3xl p-2 pl-5 ring-1 ring-(--accent)/15 max-sm:pl-4 ${workspaceSurface.panelStrong}`}
      >
        {/* 聚焦或发送中时，底部浮起的极光光带。 */}
        <span aria-hidden="true" className="aurora-veil" />
        <textarea
          aria-label="任务输入框"
          className="w-full flex-1 resize-none border-0 bg-transparent py-2.5 text-base font-medium leading-6 text-(--text-1) outline-none placeholder:text-(--text-5) disabled:bg-transparent max-sm:py-2 max-sm:text-sm"
          disabled={disabled || sending}
          onChange={(event) => onDraftChange(event.target.value)}
          onKeyDown={(event) => {
            // Enter 直接发送，Shift+Enter 换行；输入法候选确认的 Enter 不触发。
            if (
              event.key === "Enter" &&
              !event.shiftKey &&
              !event.nativeEvent.isComposing
            ) {
              event.preventDefault();
              if (!disabled && !sending && draft.trim()) {
                onSend();
              }
            }
          }}
          placeholder={disabled ? "先创建或选择一个会话" : "分配一个任务或提问任何问题..."}
          ref={textareaRef}
          rows={1}
          value={draft}
        />
        <button
          aria-label={sending ? "任务执行中" : "发送任务"}
          className="sheen-btn mb-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-(--line) bg-(--fill-2) text-(--text-1) shadow-lg shadow-black/30 transition hover:border-(--accent)/40 hover:bg-blue-500 disabled:cursor-not-allowed disabled:bg-(--fill-1) disabled:text-(--text-5) disabled:shadow-none max-sm:h-9 max-sm:w-9"
          disabled={disabled || sending || !draft.trim()}
          title={sending ? "任务执行中" : "发送并开始执行（Enter）"}
          type="submit"
        >
          {sending ? (
            <Loader2 className="animate-spin" size={19} aria-hidden="true" />
          ) : (
            <SendHorizontal size={19} aria-hidden="true" />
          )}
        </button>
      </div>
    </form>
  );
}
