import { useCallback, useEffect, useRef, useState } from "react";

type UseAutoScrollOptions = {
  threshold?: number;
  /** 会话标识：变化时视为切换会话，跳到底部展示最新内容。 */
  sessionKey: string;
  /** 最新一条用户消息的 id：变化时把该消息锚定到视口顶部。 */
  lastUserMessageId: string | null;
};

/**
 * ChatGPT 式滚动策略：
 * - 切换会话：直接跳到底部（看最新）。
 * - 发出新消息：把这条消息滚动到视口顶部并锁定，回答在下方生长。
 * - 流式期间：绝不自动跟滚——用户停在哪就是哪；想去底部用"回到底部"按钮。
 */
export function useAutoScroll({
  threshold = 96,
  sessionKey,
  lastUserMessageId,
}: UseAutoScrollOptions) {
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [pinnedToBottom, setPinnedToBottom] = useState(true);
  // 锚定后在时间线尾部垫一段空白，保证"锚到视口顶部"物理上可达
  //（否则新消息下方内容不足一屏时滚不上去）。ChatGPT 同款行为。
  const [anchorSpacer, setAnchorSpacer] = useState(false);
  const anchoredMessageRef = useRef<string | null>(null);
  const sessionRef = useRef<string | null>(null);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "smooth") => {
    bottomRef.current?.scrollIntoView({ behavior, block: "end" });
  }, []);

  const handleScroll = useCallback(() => {
    const element = scrollRef.current;
    if (!element) {
      return;
    }
    // 以"内容末尾"（bottomRef，位于锚定空白之前）为贴底基准：
    // 锚定空白只是滚动缓冲，视口越过内容末尾就算到底，不再提示回到底部。
    const bottomElement = bottomRef.current;
    const distanceToBottom = bottomElement
      ? bottomElement.getBoundingClientRect().top -
        element.getBoundingClientRect().top -
        element.clientHeight
      : element.scrollHeight - element.scrollTop - element.clientHeight;
    setPinnedToBottom(distanceToBottom <= threshold);
  }, [threshold]);

  // 会话切换：跳到底部；同时重置锚定记录（避免把历史消息当新消息锚定）。
  useEffect(() => {
    if (sessionRef.current === sessionKey) {
      return;
    }
    sessionRef.current = sessionKey;
    anchoredMessageRef.current = lastUserMessageId;
    setAnchorSpacer(false);
    // 用 setTimeout 而非 requestAnimationFrame：后台/隐藏标签页的 rAF
    // 会被浏览器冻结，导致滚动永远不执行。
    window.setTimeout(() => scrollToBottom("auto"), 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionKey]);

  // 新的用户消息出现：把它锚定到视口顶部（问题固定，回答向下生长）。
  useEffect(() => {
    if (!lastUserMessageId || anchoredMessageRef.current === lastUserMessageId) {
      return;
    }
    anchoredMessageRef.current = lastUserMessageId;
    setAnchorSpacer(true);
    // 等 spacer 渲染进 DOM 再滚动，否则底部空间不足仍会滚不到位。
    window.setTimeout(() => {
      const element = scrollRef.current?.querySelector(
        `[data-message-anchor="${lastUserMessageId}"]`,
      );
      element?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 50);
  }, [lastUserMessageId]);

  return {
    anchorSpacer,
    bottomRef,
    handleScroll,
    pinnedToBottom,
    scrollRef,
    scrollToBottom,
  };
}
