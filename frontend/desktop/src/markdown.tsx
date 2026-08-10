import { Check, Copy } from "@phosphor-icons/react";
import { useState } from "react";
import type { ReactNode } from "react";

/** 代码块：右上角悬浮复制按钮。 */
function CodeFence({ code, language }: { code: string; language?: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    if (!code) return;
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      // 剪贴板不可用时静默失败。
    }
  }

  return (
    <div className="code-fence">
      <pre data-language={language || undefined}>
        <code>{code}</code>
      </pre>
      <button
        type="button"
        className={`code-copy ${copied ? "copied" : ""}`}
        aria-label={copied ? "已复制" : "复制代码"}
        title="复制代码"
        onClick={() => void copy()}
      >
        {copied ? <Check size={13} weight="bold" /> : <Copy size={13} />}
        <span>{copied ? "已复制" : "复制"}</span>
      </button>
    </div>
  );
}

/**
 * 轻量 Markdown 渲染器。
 *
 * 只覆盖模型回答里最常见的结构：标题、列表、代码块、行内代码、
 * 加粗和链接。全部通过 React 元素构造输出，不使用 innerHTML，
 * 因此模型输出里的任何 HTML 都会按纯文本展示，天然防注入。
 */

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  // 按优先级切分：行内代码 > 加粗 > 链接。
  const pattern = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\[[^\]]+\]\((https?:\/\/[^\s)]+)\))/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let index = 0;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }
    const token = match[0];
    const key = `${keyPrefix}-${index++}`;
    if (token.startsWith("`")) {
      nodes.push(<code key={key}>{token.slice(1, -1)}</code>);
    } else if (token.startsWith("**")) {
      nodes.push(<strong key={key}>{token.slice(2, -2)}</strong>);
    } else {
      const labelEnd = token.indexOf("](");
      const label = token.slice(1, labelEnd);
      const url = token.slice(labelEnd + 2, -1);
      nodes.push(
        <a key={key} href={url} target="_blank" rel="noreferrer noopener">
          {label}
        </a>,
      );
    }
    lastIndex = match.index + token.length;
  }
  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }
  return nodes;
}

interface Block {
  kind: "heading" | "paragraph" | "list" | "ordered-list" | "code";
  level?: number;
  language?: string;
  lines: string[];
}

function splitBlocks(content: string): Block[] {
  const blocks: Block[] = [];
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  let current: Block | null = null;

  function flush() {
    if (current && current.lines.length) blocks.push(current);
    current = null;
  }

  for (const line of lines) {
    if (current?.kind === "code") {
      if (line.trimEnd() === "```") flush();
      else current.lines.push(line);
      continue;
    }
    const trimmed = line.trim();
    if (trimmed.startsWith("```")) {
      flush();
      current = { kind: "code", language: trimmed.slice(3).trim(), lines: [] };
      continue;
    }
    if (!trimmed) {
      flush();
      continue;
    }
    const headingMatch = /^(#{1,4})\s+(.*)$/.exec(trimmed);
    if (headingMatch) {
      flush();
      blocks.push({
        kind: "heading",
        level: headingMatch[1].length,
        lines: [headingMatch[2]],
      });
      continue;
    }
    if (/^[-*]\s+/.test(trimmed)) {
      if (current?.kind !== "list") {
        flush();
        current = { kind: "list", lines: [] };
      }
      current.lines.push(trimmed.replace(/^[-*]\s+/, ""));
      continue;
    }
    if (/^\d+[.、]\s*/.test(trimmed)) {
      if (current?.kind !== "ordered-list") {
        flush();
        current = { kind: "ordered-list", lines: [] };
      }
      current.lines.push(trimmed.replace(/^\d+[.、]\s*/, ""));
      continue;
    }
    if (current?.kind !== "paragraph") {
      flush();
      current = { kind: "paragraph", lines: [] };
    }
    current.lines.push(trimmed);
  }
  flush();
  return blocks;
}

export function MarkdownLite({ content }: { content: string }) {
  const blocks = splitBlocks(content);
  return (
    <div className="markdown-lite">
      {blocks.map((block, blockIndex) => {
        const key = `block-${blockIndex}`;
        if (block.kind === "code") {
          return (
            <CodeFence key={key} code={block.lines.join("\n")} language={block.language} />
          );
        }
        if (block.kind === "heading") {
          const text = renderInline(block.lines[0], key);
          if (block.level === 1) return <h3 key={key}>{text}</h3>;
          if (block.level === 2) return <h4 key={key}>{text}</h4>;
          return <h5 key={key}>{text}</h5>;
        }
        if (block.kind === "list" || block.kind === "ordered-list") {
          const items = block.lines.map((line, itemIndex) => (
            <li key={`${key}-item-${itemIndex}`}>{renderInline(line, `${key}-${itemIndex}`)}</li>
          ));
          return block.kind === "list" ? (
            <ul key={key}>{items}</ul>
          ) : (
            <ol key={key}>{items}</ol>
          );
        }
        return <p key={key}>{renderInline(block.lines.join(" "), key)}</p>;
      })}
    </div>
  );
}
