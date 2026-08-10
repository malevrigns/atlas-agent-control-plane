"use client";

import {
  Activity,
  BrainCircuit,
  ChevronDown,
  FileText,
  MessagesSquare,
  RefreshCw,
  Sparkles,
  X,
} from "lucide-react";
import type { ReactNode } from "react";
import { useState } from "react";

import { formatBytes, formatDateTime } from "../lib/format";
import type { LoadState, SessionContextData } from "../types";
import { MemoryContextSection } from "./memory-context-section";

/** 超过该长度的消息默认折叠，避免一条长回答占满整个面板。 */
const MESSAGE_COLLAPSE_CHARS = 220;

type ContextPanelProps = {
  context: LoadState<SessionContextData | null>;
  onRefresh: () => void;
  onClose: () => void;
  disabled: boolean;
};

export function ContextPanel({
  context,
  disabled,
  onClose,
  onRefresh,
}: ContextPanelProps) {
  return (
    <section className="flex h-full flex-col overflow-hidden border border-(--line) bg-(--surface) shadow-2xl shadow-black/25">
      <div className="flex items-start justify-between gap-3 border-b border-(--line) bg-(--surface-2)/95 p-5">
        <div>
          <h2 className="flex items-center gap-2 text-base font-semibold text-(--text-1)">
            <span className="brand-gradient flex h-7 w-7 items-center justify-center rounded-lg text-white">
              <BrainCircuit size={15} aria-hidden="true" />
            </span>
            上下文工程
          </h2>
          <p className="mt-1.5 text-sm leading-6 text-(--text-4)">
            模型没有记性——每次回答前，系统都会现场组装一份它能看到的内容。
            这里展示的就是本次组装的真实结果。
          </p>
        </div>
        <div className="flex gap-2">
          <button
            className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-(--line) bg-(--fill-1) text-(--text-3) hover:bg-(--fill-2) hover:text-(--text-1) disabled:text-(--text-5)"
            disabled={disabled}
            onClick={onRefresh}
            title="刷新上下文"
            type="button"
          >
            <RefreshCw size={16} aria-hidden="true" />
          </button>
          <button
            className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-(--line) bg-(--fill-1) text-(--text-3) hover:bg-(--fill-2) hover:text-(--text-1)"
            onClick={onClose}
            title="关闭上下文"
            type="button"
          >
            <X size={17} aria-hidden="true" />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-5">
        {context.type === "loading" ? (
          <p className="rounded-xl bg-(--fill-1) px-3 py-2 text-sm text-(--text-4)">
            上下文加载中
          </p>
        ) : context.type === "error" ? (
          <p className="rounded-xl border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-sm text-rose-300">
            {context.message}
          </p>
        ) : context.data ? (
          <ContextSnapshot snapshot={context.data} />
        ) : (
          <p className="rounded-xl bg-(--fill-1) px-3 py-2 text-sm text-(--text-4)">
            选择会话后可以查看上下文快照
          </p>
        )}
      </div>
    </section>
  );
}

function ContextSnapshot({ snapshot }: { snapshot: SessionContextData }) {
  const budget = snapshot.budget;
  return (
    <div className="space-y-5">
      <p className="rounded-2xl border border-(--accent)/20 bg-(--accent)/8 px-4 py-3 text-sm leading-6 text-(--text-3)">
        {snapshot.summary}
      </p>

      {/* 组装来源：四类内容各自是什么、纳入了多少。 */}
      <div>
        <SectionTitle>本次组装的四类来源</SectionTitle>
        <div className="mt-2.5 grid gap-2">
          <SourceRow
            description="模型直接读到的多轮对话原文，超出预算的旧消息会被省略"
            icon={<MessagesSquare size={15} aria-hidden="true" />}
            included={budget.included_messages}
            name="最近消息"
            omitted={budget.omitted_messages}
          />
          <SourceRow
            description="计划与工具执行记录压缩成的摘要，让模型知道之前做过什么"
            icon={<Activity size={15} aria-hidden="true" />}
            included={budget.included_events}
            name="事件压缩"
            omitted={budget.omitted_events}
          />
          <SourceRow
            description="跨会话保存的事实，按与当前任务的相关度检索后注入"
            icon={<Sparkles size={15} aria-hidden="true" />}
            included={budget.included_memories}
            name="长期记忆"
            omitted={budget.omitted_memories}
          />
          <SourceRow
            description="附件的元信息与用法提示；文本 / PDF 的内容在回答时另行抽取注入"
            icon={<FileText size={15} aria-hidden="true" />}
            included={snapshot.files.length}
            name="文件引用"
            omitted={0}
          />
        </div>
        <p className="mt-2 text-xs leading-5 text-(--text-5)">
          知识库检索与 / 调用的技能同样会注入上下文，它们按每轮提问实时组装，
          可在回答的（来源：《文档》）标注与技能徽章中查看。
        </p>
      </div>

      <MemoryContextSection memoryContext={snapshot.memory_context} />

      <div>
        <SectionTitle>最近消息（模型视角）</SectionTitle>
        <div className="mt-2.5 space-y-2">
          {snapshot.messages.length === 0 ? (
            <p className="rounded-xl bg-(--fill-1) px-3 py-2 text-sm text-(--text-4)">
              暂无消息
            </p>
          ) : (
            snapshot.messages.map((message, index) => (
              <ContextMessage
                key={`${message.created_at}-${index}`}
                message={message}
              />
            ))
          )}
        </div>
      </div>

      <div>
        <SectionTitle>事件压缩结果</SectionTitle>
        <div className="mt-2.5 grid gap-1.5">
          {snapshot.event_summaries.length === 0 ? (
            <p className="rounded-xl bg-(--fill-1) px-3 py-2 text-sm text-(--text-4)">
              暂无事件
            </p>
          ) : (
            snapshot.event_summaries.map((event) => (
              <div
                className="flex items-center justify-between rounded-xl border border-(--line) bg-(--fill-1) px-3 py-2 text-sm"
                key={event.type}
              >
                <span className="font-mono text-xs text-(--text-2)">{event.type}</span>
                <span className="rounded-full bg-(--fill-2) px-2 py-0.5 text-xs text-(--text-4)">
                  ×{event.count}
                </span>
              </div>
            ))
          )}
        </div>
      </div>

      <div>
        <SectionTitle>文件引用</SectionTitle>
        <div className="mt-2.5 space-y-2">
          {snapshot.files.length === 0 ? (
            <p className="rounded-xl bg-(--fill-1) px-3 py-2 text-sm text-(--text-4)">
              暂无文件引用
            </p>
          ) : (
            snapshot.files.map((file) => (
              <div
                className="rounded-xl border border-(--line) bg-(--fill-1) p-3"
                key={file.id}
              >
                <div className="flex items-start gap-2">
                  <FileText
                    className="mt-0.5 text-(--text-4)"
                    size={16}
                    aria-hidden="true"
                  />
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-(--text-2)">
                      {file.name}
                    </p>
                    <p className="mt-1 text-xs text-(--text-4)">
                      {file.content_type} · {formatBytes(file.size)}
                    </p>
                    <p className="mt-2 text-xs leading-5 text-(--text-3)">
                      {file.usage_hint}
                    </p>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function ContextMessage({
  message,
}: {
  message: SessionContextData["messages"][number];
}) {
  const collapsible = message.content.length > MESSAGE_COLLAPSE_CHARS;
  const [expanded, setExpanded] = useState(false);
  const clamped = collapsible && !expanded;

  return (
    <div className="rounded-xl border border-(--line) bg-(--fill-1) p-3">
      <div className="flex items-center justify-between gap-2 text-xs">
        <span
          className={`rounded-full px-2 py-0.5 font-semibold ${
            message.role === "user"
              ? "bg-(--accent)/12 text-(--accent)"
              : "bg-violet-500/12 text-violet-400"
          }`}
        >
          {message.role === "user" ? "用户" : "助手"}
        </span>
        <span className="text-(--text-5)">{formatDateTime(message.created_at)}</span>
      </div>
      <div className="relative">
        <p
          className={`mt-2 whitespace-pre-wrap text-sm leading-6 text-(--text-2) ${
            clamped ? "line-clamp-4" : ""
          }`}
        >
          {message.content}
        </p>
        {clamped ? (
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-x-0 bottom-0 h-8 bg-gradient-to-t from-(--surface) to-transparent"
          />
        ) : null}
      </div>
      {collapsible ? (
        <button
          className="mt-1.5 inline-flex items-center gap-1 text-xs font-medium text-(--accent) transition hover:opacity-80"
          onClick={() => setExpanded((value) => !value)}
          type="button"
        >
          <ChevronDown
            aria-hidden="true"
            className={`transition-transform ${expanded ? "rotate-180" : ""}`}
            size={13}
          />
          {expanded ? "收起" : `展开全文（${message.content.length} 字）`}
        </button>
      ) : null}
      {message.truncated ? (
        <p className="mt-2 text-xs text-amber-400">
          原始长度 {message.original_chars} 字符，已按预算裁剪
        </p>
      ) : null}
    </div>
  );
}

function SectionTitle({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span className="brand-gradient h-3.5 w-[3px] rounded-full" aria-hidden="true" />
      <h3 className="text-xs font-semibold uppercase tracking-[0.16em] text-(--text-3)">
        {children}
      </h3>
    </div>
  );
}

function SourceRow({
  description,
  icon,
  included,
  name,
  omitted,
}: {
  description: string;
  icon: ReactNode;
  included: number;
  name: string;
  omitted: number;
}) {
  const active = included > 0;
  return (
    <div className="flex items-start gap-3 rounded-xl border border-(--line) bg-(--fill-1) p-3">
      <span
        className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${
          active
            ? "bg-(--accent)/12 text-(--accent)"
            : "bg-(--fill-2) text-(--text-5)"
        }`}
      >
        {icon}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold text-(--text-1)">{name}</span>
          <span
            className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${
              active
                ? "bg-emerald-500/12 text-emerald-500"
                : "bg-(--fill-2) text-(--text-5)"
            }`}
          >
            纳入 {included}
          </span>
          {omitted > 0 ? (
            <span className="rounded-full bg-amber-500/12 px-2 py-0.5 text-[11px] font-semibold text-amber-500">
              省略 {omitted}
            </span>
          ) : null}
        </div>
        <p className="mt-1 text-xs leading-5 text-(--text-4)">{description}</p>
      </div>
    </div>
  );
}
