"use client";

import { Brain, ChevronDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { MarkdownContent } from "../markdown-content";

type ReasoningBlockProps = {
  /** 完整或流式中的思考文本。 */
  reasoning: string;
  /** 流式中：默认展开并显示动画提示。 */
  streaming?: boolean;
};

/**
 * 模型推理过程的可折叠展示块。
 * 流式时默认展开实时滚动；完成后默认折叠，点击可回看。
 */
export function ReasoningBlock({ reasoning, streaming = false }: ReasoningBlockProps) {
  const [expanded, setExpanded] = useState<boolean | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const open = expanded ?? streaming;

  // 流式时始终滚到底部，让最新思考持续可见，而不是框铺满后就停住。
  useEffect(() => {
    if (streaming && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [reasoning, streaming]);

  if (!reasoning) {
    return null;
  }

  return (
    <div className="mb-2 overflow-hidden rounded-2xl border border-(--line) bg-(--fill-1)">
      <button
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-xs font-medium text-(--text-4) transition hover:text-(--text-2)"
        onClick={() => setExpanded(!open)}
        type="button"
      >
        <Brain
          aria-hidden="true"
          className={streaming ? "animate-pulse text-(--accent)" : "text-(--text-4)"}
          size={14}
        />
        {streaming ? (
          <span className="shimmer-text text-(--accent)">正在思考…</span>
        ) : (
          <span>推理过程</span>
        )}
        <span className="text-(--text-5)">{reasoning.length} 字</span>
        <ChevronDown
          aria-hidden="true"
          className={`ml-auto transition-transform ${open ? "rotate-180" : ""}`}
          size={14}
        />
      </button>
      {open ? (
        <div
          ref={scrollRef}
          className="max-h-64 overflow-y-auto border-t border-(--line-soft) px-4 py-3"
        >
          <MarkdownContent compact content={reasoning} />
        </div>
      ) : null}
    </div>
  );
}
