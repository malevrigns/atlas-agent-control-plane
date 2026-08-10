"use client";

import { Check, Copy } from "lucide-react";
import { useRef, useState } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

/** 代码块容器：右上角悬浮复制按钮，点击复制整段代码。 */
function PreBlock({ children }: { children?: React.ReactNode }) {
  const preRef = useRef<HTMLPreElement>(null);
  const [copied, setCopied] = useState(false);

  async function copy() {
    const text = preRef.current?.innerText ?? "";
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      // 剪贴板不可用（如非安全上下文）时静默失败。
    }
  }

  return (
    <div className="group relative my-4">
      <pre className="overflow-x-auto" ref={preRef}>
        {children}
      </pre>
      <button
        aria-label={copied ? "已复制" : "复制代码"}
        className={`absolute right-2.5 top-2.5 flex h-8 items-center gap-1.5 rounded-lg border border-(--line) bg-(--surface-2)/90 px-2.5 text-xs font-medium backdrop-blur transition ${
          copied
            ? "text-emerald-400 opacity-100"
            : "text-(--text-4) opacity-0 hover:text-(--text-1) focus-visible:opacity-100 group-hover:opacity-100"
        }`}
        onClick={copy}
        title="复制代码"
        type="button"
      >
        {copied ? <Check size={13} aria-hidden="true" /> : <Copy size={13} aria-hidden="true" />}
        {copied ? "已复制" : "复制"}
      </button>
    </div>
  );
}

type MarkdownContentProps = {
  className?: string;
  content: string;
  /** 紧凑模式：更小字号与更弱的文字色，用于推理过程等辅助内容。 */
  compact?: boolean;
};

const cjkRanges = "\\u3000-\\u303F\\u4E00-\\u9FFF\\uFF01-\\uFF60";
const urlFollowedByCjk = new RegExp(
  `(https?:\\/\\/[^\\s${cjkRanges}]+)([${cjkRanges}])`,
  "g",
);

function normalizeAutolinks(value: string) {
  return value.replace(urlFollowedByCjk, "$1 $2");
}

function buildComponents(compact: boolean): Components {
  // \u6B63\u6587\u4E0E\u7D27\u51D1\u4E24\u6863\u5B57\u53F7\uFF1B\u7D27\u51D1\u6863\u7528\u4E8E\u63A8\u7406\u8FC7\u7A0B\u7B49\u8F85\u52A9\u5185\u5BB9\u3002
  const bodyText = compact
    ? "text-[13px] leading-6 text-(--text-4)"
    : "text-[15px] leading-7 text-(--text-3)";
  const codeText = compact ? "text-xs leading-5" : "text-sm leading-6";

  return {
    h1: ({ children }) => (
      <h1
        className={`mb-3 mt-5 font-semibold text-(--text-1) first:mt-0 ${
          compact ? "text-sm leading-6" : "text-lg leading-8"
        }`}
      >
        {children}
      </h1>
    ),
    h2: ({ children }) => (
      <h2
        className={`mb-2.5 mt-5 font-semibold text-(--text-1) first:mt-0 ${
          compact ? "text-sm leading-6" : "text-base leading-7"
        }`}
      >
        {children}
      </h2>
    ),
    h3: ({ children }) => (
      <h3
        className={`mb-2 mt-4 font-semibold text-(--text-1) first:mt-0 ${
          compact ? "text-[13px] leading-6" : "text-base leading-7"
        }`}
      >
        {children}
      </h3>
    ),
    p: ({ children }) => (
      <p className={`mb-3 last:mb-0 ${bodyText}`}>{children}</p>
    ),
    ul: ({ children }) => (
      <ul className={`mb-3 list-disc space-y-1 pl-5 last:mb-0 ${bodyText}`}>
        {children}
      </ul>
    ),
    ol: ({ children }) => (
      <ol className={`mb-3 list-decimal space-y-1 pl-5 last:mb-0 ${bodyText}`}>
        {children}
      </ol>
    ),
    li: ({ children }) => <li className="pl-1">{children}</li>,
    strong: ({ children }) => (
      <strong className="font-semibold text-(--text-1)">{children}</strong>
    ),
    blockquote: ({ children }) => (
      <blockquote className="my-4 border-l-2 border-(--accent)/45 pl-4 text-(--text-3)">
        {children}
      </blockquote>
    ),
    a: ({ children, href }) => {
      if (href && /[\u4E00-\u9FFF\u3000-\u303F\uFF00-\uFFEF]/.test(href)) {
        return <span>{children}</span>;
      }
      return (
        <a
          className="text-(--accent) underline-offset-4 hover:underline"
          href={href}
          rel="noreferrer"
          target="_blank"
        >
          {children}
        </a>
      );
    },
    code: ({ children, className }) => {
      const value = String(children);
      const block = value.includes("\n") || className?.startsWith("language-");
      if (!block) {
        return (
          <code className="rounded-md border border-(--line) bg-(--fill-2) px-1.5 py-0.5 font-mono text-[0.9em] text-(--text-1)">
            {children}
          </code>
        );
      }
      return (
        <code
          className={`block overflow-x-auto whitespace-pre rounded-2xl border border-(--line) bg-(--field) p-4 font-mono text-(--text-1) ${codeText}`}
        >
          {children}
        </code>
      );
    },
    pre: ({ children }) => <PreBlock>{children}</PreBlock>,
    table: ({ children }) => (
      <div className="my-4 overflow-x-auto rounded-2xl border border-(--line)">
        <table className="min-w-full border-collapse text-sm text-(--text-2)">
          {children}
        </table>
      </div>
    ),
    th: ({ children }) => (
      <th className="border-b border-(--line) bg-(--fill-1) px-3 py-2 text-left font-semibold text-(--text-1)">
        {children}
      </th>
    ),
    td: ({ children }) => (
      <td className="border-b border-(--line-soft) px-3 py-2 text-(--text-3)">
        {children}
      </td>
    ),
  };
}

const defaultComponents = buildComponents(false);
const compactComponents = buildComponents(true);

export function MarkdownContent({
  className = "",
  content,
  compact = false,
}: MarkdownContentProps) {
  return (
    <div className={`break-words ${className}`}>
      <ReactMarkdown
        components={compact ? compactComponents : defaultComponents}
        remarkPlugins={[remarkGfm]}
      >
        {normalizeAutolinks(content)}
      </ReactMarkdown>
    </div>
  );
}
