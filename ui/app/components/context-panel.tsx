import { BrainCircuit, FileText, RefreshCw, X } from "lucide-react";

import { formatBytes, formatDateTime } from "../lib/format";
import type { LoadState, SessionContextData } from "../types";
import { MemoryContextSection } from "./memory-context-section";

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
    <section className="flex h-full flex-col overflow-hidden border border-white/10 bg-[#08090d] shadow-2xl shadow-black/60">
      <div className="flex items-start justify-between gap-3 border-b border-white/10 bg-black/60 p-5">
        <div>
          <h2 className="flex items-center gap-2 text-base font-semibold text-zinc-50">
            <BrainCircuit size={17} aria-hidden="true" />
            上下文工程
          </h2>
          <p className="mt-1 text-sm text-zinc-500">
            查看本次任务实际使用的短期上下文和长期记忆
          </p>
        </div>
        <div className="flex gap-2">
          <button
            className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-white/10 bg-white/[0.04] text-zinc-400 hover:bg-white/10 hover:text-zinc-50 disabled:text-zinc-700"
            disabled={disabled}
            onClick={onRefresh}
            title="刷新上下文"
            type="button"
          >
            <RefreshCw size={16} aria-hidden="true" />
          </button>
          <button
            className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-white/10 bg-white/[0.04] text-zinc-400 hover:bg-white/10 hover:text-zinc-50"
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
          <p className="rounded-md bg-white/[0.04] px-3 py-2 text-sm text-zinc-500">
            上下文加载中
          </p>
        ) : context.type === "error" ? (
          <p className="rounded-md border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-sm text-rose-300">
            {context.message}
          </p>
        ) : context.data ? (
          <ContextSnapshot snapshot={context.data} />
        ) : (
          <p className="rounded-md bg-white/[0.04] px-3 py-2 text-sm text-zinc-500">
            选择会话后可以查看上下文快照
          </p>
        )}
      </div>
    </section>
  );
}

function ContextSnapshot({ snapshot }: { snapshot: SessionContextData }) {
  return (
    <div className="space-y-4">
      <p className="rounded-md border border-white/10 bg-white/[0.04] px-3 py-2 text-sm leading-6 text-zinc-400">
        {snapshot.summary}
      </p>

      <div className="grid grid-cols-3 gap-2 text-xs text-zinc-400">
        <Metric label="纳入消息" value={snapshot.budget.included_messages} />
        <Metric label="省略消息" value={snapshot.budget.omitted_messages} />
        <Metric label="纳入事件" value={snapshot.budget.included_events} />
        <Metric label="省略事件" value={snapshot.budget.omitted_events} />
        <Metric label="注入记忆" value={snapshot.budget.included_memories} />
        <Metric label="省略记忆" value={snapshot.budget.omitted_memories} />
      </div>

      <MemoryContextSection memoryContext={snapshot.memory_context} />

      <div>
        <h3 className="text-sm font-semibold text-zinc-100">最近消息</h3>
        <div className="mt-2 space-y-2">
          {snapshot.messages.length === 0 ? (
            <p className="rounded-md bg-white/[0.04] px-3 py-2 text-sm text-zinc-500">
              暂无消息
            </p>
          ) : (
            snapshot.messages.map((message, index) => (
              <div
                className="rounded-md border border-white/10 bg-white/[0.04] p-3"
                key={`${message.created_at}-${index}`}
              >
                <div className="flex items-center justify-between gap-2 text-xs text-zinc-500">
                  <span>{message.role}</span>
                  <span>{formatDateTime(message.created_at)}</span>
                </div>
                <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-zinc-300">
                  {message.content}
                </p>
                {message.truncated ? (
                  <p className="mt-2 text-xs text-amber-400">
                    原始长度 {message.original_chars} 字符，已按预算裁剪
                  </p>
                ) : null}
              </div>
            ))
          )}
        </div>
      </div>

      <div>
        <h3 className="text-sm font-semibold text-zinc-100">事件摘要</h3>
        <div className="mt-2 grid gap-2">
          {snapshot.event_summaries.length === 0 ? (
            <p className="rounded-md bg-white/[0.04] px-3 py-2 text-sm text-zinc-500">
              暂无事件
            </p>
          ) : (
            snapshot.event_summaries.map((event) => (
              <div
                className="flex items-center justify-between rounded-md border border-white/10 bg-white/[0.04] px-3 py-2 text-sm"
                key={event.type}
              >
                <span className="font-medium text-zinc-300">{event.type}</span>
                <span className="text-xs text-zinc-500">{event.count} 次</span>
              </div>
            ))
          )}
        </div>
      </div>

      <div>
        <h3 className="text-sm font-semibold text-zinc-100">文件引用</h3>
        <div className="mt-2 space-y-2">
          {snapshot.files.length === 0 ? (
            <p className="rounded-md bg-white/[0.04] px-3 py-2 text-sm text-zinc-500">
              暂无文件引用
            </p>
          ) : (
            snapshot.files.map((file) => (
              <div
                className="rounded-md border border-white/10 bg-white/[0.04] p-3"
                key={file.id}
              >
                <div className="flex items-start gap-2">
                  <FileText className="mt-0.5 text-zinc-500" size={16} aria-hidden="true" />
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-zinc-200">
                      {file.name}
                    </p>
                    <p className="mt-1 text-xs text-zinc-500">
                      {file.content_type} · {formatBytes(file.size)}
                    </p>
                    <p className="mt-2 text-xs leading-5 text-zinc-400">
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

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-white/10 bg-white/[0.04] px-3 py-2">
      <div className="text-zinc-500">{label}</div>
      <div className="mt-1 text-base font-semibold text-zinc-100">{value}</div>
    </div>
  );
}
