"use client";

import {
  Brain,
  CheckCircle2,
  Plus,
  RefreshCw,
  Sparkles,
  Trash2,
} from "lucide-react";
import { useEffect, useState } from "react";

import {
  createMemory,
  deleteMemory,
  extractMemoryCandidates,
  fetchMemories,
  updateMemory,
} from "../lib/memory-api";
import type {
  AgentMemoryItem,
  LoadState,
  MemoryCandidateItem,
  MemoryKind,
} from "../types";

type MemoryDraft = {
  kind: MemoryKind;
  content: string;
  importance: number;
};

const memoryKindOptions: Array<{ label: string; value: MemoryKind }> = [
  { label: "用户偏好", value: "user_preference" },
  { label: "项目事实", value: "project_fact" },
  { label: "任务经验", value: "task_experience" },
  { label: "长期约束", value: "constraint" },
];


// ===================== 第1步：长期记忆设置面板入口 =====================
export function MemorySettingsPanel() {
  const [memories, setMemories] = useState<LoadState<AgentMemoryItem[]>>({
    type: "loading",
  });
  const [candidates, setCandidates] = useState<
    LoadState<MemoryCandidateItem[]>
  >({ type: "ready", data: [] });
  const [draft, setDraft] = useState<MemoryDraft>({
    kind: "user_preference",
    content: "",
    importance: 3,
  });
  const [extractSessionId, setExtractSessionId] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  async function loadMemories() {
    // 1. 读取数据库中的长期记忆列表。
    //    第41章做上下文注入时，也会复用同一批 enabled=true 的记忆。
    setMemories({ type: "loading" });
    try {
      const items = await fetchMemories();
      setMemories({ type: "ready", data: items });
    } catch (error) {
      setMemories({
        type: "error",
        message: error instanceof Error ? error.message : "unknown error",
      });
    }
  }

  async function handleCreateMemory(payload: MemoryDraft) {
    // 2. 手动新增适合保存的长期记忆。
    //    这里不要求来自某个会话，因为项目背景、个人偏好也可能由用户直接录入。
    const cleanContent = payload.content.trim();
    if (!cleanContent) {
      setActionError("请输入记忆内容");
      return;
    }
    setActionError(null);
    try {
      await createMemory({
        kind: payload.kind,
        content: cleanContent,
        importance: payload.importance,
      });
      setDraft({ kind: "user_preference", content: "", importance: 3 });
      await loadMemories();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "unknown error");
    }
  }

  async function handleExtractCandidates() {
    // 3. 从指定会话里抽取候选，但不自动写入长期记忆。
    //    长期记忆会影响后续任务，因此先让用户确认候选内容。
    const cleanSessionId = extractSessionId.trim();
    if (!cleanSessionId) {
      setActionError("请输入会话 ID");
      return;
    }
    setActionError(null);
    setCandidates({ type: "loading" });
    try {
      const data = await extractMemoryCandidates(cleanSessionId);
      setCandidates({ type: "ready", data: data.items });
    } catch (error) {
      setCandidates({
        type: "error",
        message: error instanceof Error ? error.message : "unknown error",
      });
    }
  }

  async function confirmCandidate(candidate: MemoryCandidateItem) {
    // 4. 用户确认候选后，才真正写入 agent_memories。
    setActionError(null);
    try {
      await createMemory({
        kind: candidate.kind,
        content: candidate.content,
        importance: candidate.importance,
        source_session_id: candidate.source_session_id,
        source_event_id: candidate.source_event_id,
        metadata: candidate.metadata,
      });
      setCandidates((current) =>
        current.type === "ready"
          ? {
              type: "ready",
              data: current.data.filter((item) => item !== candidate),
            }
          : current,
      );
      await loadMemories();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "unknown error");
    }
  }

  async function toggleMemory(memory: AgentMemoryItem) {
    setActionError(null);
    try {
      await updateMemory(memory.id, { enabled: !memory.enabled });
      await loadMemories();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "unknown error");
    }
  }

  async function removeMemory(memoryId: string) {
    setActionError(null);
    try {
      await deleteMemory(memoryId);
      await loadMemories();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "unknown error");
    }
  }

  useEffect(() => {
    loadMemories();
  }, []);

  return (
    <section className="grid gap-5 rounded-md border border-slate-200 bg-white p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="flex items-center gap-2 text-base font-semibold text-slate-950">
            <Brain size={18} aria-hidden="true" />
            长期记忆
          </h3>
          <p className="mt-1 text-sm leading-6 text-slate-500">
            管理跨会话保存的用户偏好、项目事实、任务经验和长期约束
          </p>
        </div>
        <button
          className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-slate-200 text-slate-600 hover:bg-slate-50"
          onClick={loadMemories}
          title="刷新记忆"
          type="button"
        >
          <RefreshCw size={16} aria-hidden="true" />
        </button>
      </div>

      {actionError ? (
        <div className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
          {actionError}
        </div>
      ) : null}

      <MemoryCreateForm
        draft={draft}
        onChange={setDraft}
        onSubmit={handleCreateMemory}
      />
      <MemoryCandidateExtractor
        candidates={candidates}
        onConfirm={confirmCandidate}
        onExtract={handleExtractCandidates}
        onSessionIdChange={setExtractSessionId}
        sessionId={extractSessionId}
      />
      <MemoryList
        memories={memories}
        onDelete={removeMemory}
        onToggle={toggleMemory}
      />
    </section>
  );
}


function MemoryCreateForm({
  draft,
  onChange,
  onSubmit,
}: {
  draft: MemoryDraft;
  onChange: (draft: MemoryDraft) => void;
  onSubmit: (draft: MemoryDraft) => void;
}) {
  return (
    <form
      className="grid gap-3 rounded-md border border-slate-200 bg-slate-50 p-4"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit(draft);
      }}
    >
      <div className="grid grid-cols-[180px_1fr_120px] gap-3 max-lg:grid-cols-1">
        <select
          className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none focus:border-slate-400"
          onChange={(event) =>
            onChange({ ...draft, kind: event.target.value as MemoryKind })
          }
          value={draft.kind}
        >
          {memoryKindOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <input
          className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none focus:border-slate-400"
          maxLength={2000}
          onChange={(event) =>
            onChange({ ...draft, content: event.target.value })
          }
          placeholder="例如：用户希望教程里的后端代码保留详细分步注释"
          value={draft.content}
        />
        <input
          className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none focus:border-slate-400"
          max={5}
          min={1}
          onChange={(event) =>
            onChange({ ...draft, importance: Number(event.target.value) })
          }
          type="number"
          value={draft.importance}
        />
      </div>
      <button
        className="inline-flex h-10 w-fit items-center gap-2 rounded-md bg-slate-950 px-4 text-sm font-medium text-white hover:bg-slate-800"
        type="submit"
      >
        <Plus size={16} aria-hidden="true" />
        新增记忆
      </button>
    </form>
  );
}


function MemoryCandidateExtractor({
  candidates,
  onConfirm,
  onExtract,
  onSessionIdChange,
  sessionId,
}: {
  candidates: LoadState<MemoryCandidateItem[]>;
  onConfirm: (candidate: MemoryCandidateItem) => void;
  onExtract: () => void;
  onSessionIdChange: (value: string) => void;
  sessionId: string;
}) {
  return (
    <div className="rounded-md border border-slate-200 p-4">
      <div className="flex items-start justify-between gap-3 max-lg:flex-col">
        <div>
          <h4 className="flex items-center gap-2 text-sm font-semibold text-slate-950">
            <Sparkles size={16} aria-hidden="true" />
            从会话抽取候选
          </h4>
          <p className="mt-1 text-sm leading-6 text-slate-500">
            先生成候选，确认后再写入长期记忆，避免错误记忆污染后续上下文
          </p>
        </div>
        <div className="flex w-full max-w-xl gap-2">
          <input
            className="h-10 min-w-0 flex-1 rounded-md border border-slate-200 px-3 text-sm text-slate-900 outline-none focus:border-slate-400"
            onChange={(event) => onSessionIdChange(event.target.value)}
            placeholder="输入会话 ID"
            value={sessionId}
          />
          <button
            className="h-10 shrink-0 rounded-md border border-slate-200 px-3 text-sm font-medium text-slate-700 hover:bg-slate-50"
            onClick={onExtract}
            type="button"
          >
            抽取
          </button>
        </div>
      </div>

      {candidates.type === "loading" ? (
        <div className="mt-3 text-sm text-slate-500">正在抽取候选...</div>
      ) : null}
      {candidates.type === "error" ? (
        <div className="mt-3 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
          {candidates.message}
        </div>
      ) : null}
      {candidates.type === "ready" && candidates.data.length > 0 ? (
        <div className="mt-3 grid gap-2">
          {candidates.data.map((candidate, index) => (
            <div
              className="flex items-start justify-between gap-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-2"
              key={`${candidate.kind}-${candidate.content}-${index}`}
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <KindPill kind={candidate.kind} />
                  <span className="text-xs text-slate-500">
                    重要度 {candidate.importance}
                  </span>
                </div>
                <p className="mt-2 text-sm leading-6 text-slate-800">
                  {candidate.content}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  {candidate.reason}
                </p>
              </div>
              <button
                className="inline-flex h-8 shrink-0 items-center gap-1 rounded-md border border-emerald-200 bg-emerald-50 px-2 text-xs font-medium text-emerald-700"
                onClick={() => onConfirm(candidate)}
                type="button"
              >
                <CheckCircle2 size={14} aria-hidden="true" />
                确认
              </button>
            </div>
          ))}
        </div>
      ) : null}
      {candidates.type === "ready" &&
      candidates.data.length === 0 &&
      sessionId.trim() ? (
        <div className="mt-3 text-sm text-slate-500">
          当前没有待确认的记忆候选
        </div>
      ) : null}
    </div>
  );
}


function MemoryList({
  memories,
  onDelete,
  onToggle,
}: {
  memories: LoadState<AgentMemoryItem[]>;
  onDelete: (memoryId: string) => void;
  onToggle: (memory: AgentMemoryItem) => void;
}) {
  if (memories.type === "loading") {
    return <div className="text-sm text-slate-500">正在读取长期记忆...</div>;
  }

  if (memories.type === "error") {
    return (
      <div className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
        {memories.message}
      </div>
    );
  }

  if (memories.data.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-slate-300 px-3 py-8 text-center text-sm text-slate-500">
        暂无长期记忆
      </div>
    );
  }

  return (
    <div className="grid gap-2">
      {memories.data.map((memory) => (
        <div
          className="flex items-start justify-between gap-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-3"
          key={memory.id}
        >
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <KindPill kind={memory.kind} />
              <span className="text-xs text-slate-500">
                重要度 {memory.importance}
              </span>
              <span className="text-xs text-slate-500">
                {memory.enabled ? "已启用" : "已禁用"}
              </span>
            </div>
            <p className="mt-2 text-sm leading-6 text-slate-800">
              {memory.content}
            </p>
          </div>
          <div className="flex shrink-0 gap-2">
            <button
              className="h-8 rounded-md border border-slate-200 bg-white px-2 text-xs text-slate-700 hover:bg-slate-50"
              onClick={() => onToggle(memory)}
              type="button"
            >
              {memory.enabled ? "禁用" : "启用"}
            </button>
            <button
              className="inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-white hover:text-rose-600"
              onClick={() => onDelete(memory.id)}
              title="删除记忆"
              type="button"
            >
              <Trash2 size={15} aria-hidden="true" />
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}


function KindPill({ kind }: { kind: MemoryKind }) {
  const label =
    memoryKindOptions.find((option) => option.value === kind)?.label ?? kind;
  return (
    <span className="rounded bg-white px-2 py-1 text-xs font-medium text-slate-600">
      {label}
    </span>
  );
}
