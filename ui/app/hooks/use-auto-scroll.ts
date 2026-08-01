import { useCallback, useEffect, useRef, useState } from "react";

type UseAutoScrollOptions = {
  threshold?: number;
  watchKey: string;
};

// ===================== 第1步：管理对话时间线的自动滚动状态 =====================
export function useAutoScroll({
  threshold = 96,
  watchKey,
}: UseAutoScrollOptions) {
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [pinnedToBottom, setPinnedToBottom] = useState(true);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "smooth") => {
    bottomRef.current?.scrollIntoView({ behavior, block: "end" });
  }, []);

  const handleScroll = useCallback(() => {
    const element = scrollRef.current;
    if (!element) {
      return;
    }

    // ===================== 第2步：判断用户是否还停留在底部附近 =====================
    // 如果用户主动向上看旧步骤，就暂停自动滚动；否则新事件进入时继续贴底展示。
    const distanceToBottom =
      element.scrollHeight - element.scrollTop - element.clientHeight;
    setPinnedToBottom(distanceToBottom <= threshold);
  }, [threshold]);

  useEffect(() => {
    if (pinnedToBottom) {
      scrollToBottom("smooth");
    }
  }, [pinnedToBottom, scrollToBottom, watchKey]);

  return {
    bottomRef,
    handleScroll,
    pinnedToBottom,
    scrollRef,
    scrollToBottom,
  };
}
