"use client";

import {
  BookOpenText,
  ImagePlus,
  Loader2,
  Plus,
  RefreshCcw,
  Search,
  Trash2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  createKnowledgeBase,
  deleteKnowledgeBase,
  deleteKnowledgeDocument,
  fetchKnowledgeBases,
  fetchKnowledgeDocuments,
  ingestImageDocument,
  ingestKnowledgeDocument,
  queryKnowledgeBase,
  reingestKnowledgeDocument,
} from "../lib/rag-api";
import type {
  KnowledgeBase,
  KnowledgeDocument,
  RagQueryResult,
} from "../lib/rag-api";

const DOCUMENT_STATUS_LABELS: Record<string, string> = {
  pending: "待处理",
  processing: "摄取中",
  ready: "已就绪",
  failed: "失败",
};

/**
 * Web 版 RAG 知识库管理台：建库、摄取文档、重建索引、检索验证。
 * 与桌面端共用同一套 /api/rag 接口。
 */
export function KnowledgeWorkspace() {
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState("");
  const [noticeTone, setNoticeTone] = useState<"info" | "danger">("info");
  const [creating, setCreating] = useState(false);
  const [kbForm, setKbForm] = useState({ name: "", description: "" });
  const [documentForm, setDocumentForm] = useState({ title: "", content: "" });
  const [ingesting, setIngesting] = useState(false);
  const [query, setQuery] = useState("");
  const [querying, setQuerying] = useState(false);
  const [queryResult, setQueryResult] = useState<RagQueryResult | null>(null);
  const [imageIngesting, setImageIngesting] = useState(false);
  const imageInputRef = useRef<HTMLInputElement>(null);

  const selected = useMemo(
    () => knowledgeBases.find((kb) => kb.id === selectedId) ?? null,
    [knowledgeBases, selectedId],
  );

  const report = useCallback((message: string, tone: "info" | "danger" = "info") => {
    setNotice(message);
    setNoticeTone(tone);
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchKnowledgeBases();
      setKnowledgeBases(data.items);
      setSelectedId((current) =>
        current && data.items.some((kb) => kb.id === current)
          ? current
          : data.items[0]?.id ?? null,
      );
    } catch (error) {
      report(error instanceof Error ? error.message : "读取知识库失败", "danger");
    } finally {
      setLoading(false);
    }
  }, [report]);

  const refreshDocuments = useCallback(async (knowledgeBaseId: string) => {
    try {
      const data = await fetchKnowledgeDocuments(knowledgeBaseId);
      setDocuments(data.items);
    } catch {
      setDocuments([]);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    setQueryResult(null);
    setDocuments([]);
    if (selectedId) void refreshDocuments(selectedId);
  }, [selectedId, refreshDocuments]);

  async function submitCreate() {
    if (!kbForm.name.trim()) {
      report("知识库名称是必填项。", "danger");
      return;
    }
    try {
      const created = await createKnowledgeBase({
        name: kbForm.name.trim(),
        description: kbForm.description.trim(),
      });
      report(`知识库「${created.name}」已创建。`);
      setCreating(false);
      setKbForm({ name: "", description: "" });
      await refresh();
      setSelectedId(created.id);
    } catch (error) {
      report(error instanceof Error ? error.message : "创建失败", "danger");
    }
  }

  async function submitIngest() {
    if (!selected) return;
    if (!documentForm.title.trim() || !documentForm.content.trim()) {
      report("文档标题与内容都是必填项。", "danger");
      return;
    }
    setIngesting(true);
    try {
      const document = await ingestKnowledgeDocument(selected.id, {
        title: documentForm.title.trim(),
        content: documentForm.content,
      });
      report(
        document.status === "ready"
          ? `文档已摄取：切分为 ${document.chunk_count} 个 chunk。`
          : `摄取失败：${document.error || "未知原因"}`,
        document.status === "ready" ? "info" : "danger",
      );
      setDocumentForm({ title: "", content: "" });
      await Promise.all([refresh(), refreshDocuments(selected.id)]);
    } catch (error) {
      report(error instanceof Error ? error.message : "摄取失败", "danger");
    } finally {
      setIngesting(false);
    }
  }

  async function submitImage(file: File) {
    if (!selected) return;
    setImageIngesting(true);
    report(`正在用视觉模型解析「${file.name}」…（图表越复杂耗时越长）`);
    try {
      const document = await ingestImageDocument(selected.id, file);
      report(
        document.status === "ready"
          ? `图片已解析入库：「${document.title}」切分为 ${document.chunk_count} 个 chunk，现在可以检索图中内容了。`
          : `解析失败：${document.error || "未知原因"}`,
        document.status === "ready" ? "info" : "danger",
      );
      await Promise.all([refresh(), refreshDocuments(selected.id)]);
    } catch (error) {
      report(error instanceof Error ? error.message : "图片解析失败", "danger");
    } finally {
      setImageIngesting(false);
      if (imageInputRef.current) imageInputRef.current.value = "";
    }
  }

  async function runQuery() {
    if (!selected || !query.trim()) return;
    setQuerying(true);
    try {
      setQueryResult(await queryKnowledgeBase(selected.id, query.trim()));
    } catch (error) {
      report(error instanceof Error ? error.message : "检索失败", "danger");
    } finally {
      setQuerying(false);
    }
  }

  const inputClass =
    "h-10 w-full rounded-xl border border-(--line) bg-(--field) px-3 text-sm text-(--text-1) outline-none transition placeholder:text-(--text-5) focus:border-(--accent)/60";

  return (
    <section className="mx-auto flex h-full min-h-[640px] w-full max-w-[1080px] flex-col overflow-hidden rounded-[28px] border border-(--line) bg-(--surface)/95 shadow-2xl shadow-black/25">
      <header className="flex shrink-0 items-start justify-between gap-4 border-b border-(--line) px-6 py-5">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-semibold text-(--text-1)">
            <BookOpenText size={19} aria-hidden="true" />
            知识库（RAG）
          </h2>
          <p className="mt-1 text-sm leading-6 text-(--text-4)">
            摄取文档 → 切分向量化 → 带引用检索；Agent 通过 knowledge_search 消费同一条链路
          </p>
        </div>
        <div className="flex gap-2">
          <button
            className="inline-flex h-10 items-center gap-2 rounded-2xl bg-blue-500 px-4 text-sm font-medium text-white transition hover:bg-blue-400"
            onClick={() => setCreating((value) => !value)}
            type="button"
          >
            <Plus size={15} aria-hidden="true" /> 新建知识库
          </button>
          <button
            className="inline-flex h-10 w-10 items-center justify-center rounded-2xl border border-(--line) bg-(--fill-1) text-(--text-3) hover:bg-(--fill-2) hover:text-(--text-1)"
            onClick={() => void refresh()}
            title="刷新"
            type="button"
          >
            <RefreshCcw className={loading ? "animate-spin" : ""} size={16} aria-hidden="true" />
          </button>
        </div>
      </header>

      {notice ? (
        <div
          className={`mx-6 mt-4 rounded-2xl border px-4 py-2.5 text-sm ${
            noticeTone === "danger"
              ? "border-rose-500/30 bg-rose-500/10 text-rose-300"
              : "border-(--line) bg-(--fill-1) text-(--text-3)"
          }`}
        >
          {notice}
        </div>
      ) : null}

      {creating ? (
        <div className="mx-6 mt-4 rounded-2xl border border-(--line) bg-(--fill-1) p-4">
          <div className="grid grid-cols-2 gap-3 max-md:grid-cols-1">
            <label className="text-xs font-medium text-(--text-4)">
              名称
              <input
                className={`mt-1.5 ${inputClass}`}
                onChange={(event) => setKbForm({ ...kbForm, name: event.target.value })}
                placeholder="工程运维知识库"
                value={kbForm.name}
              />
            </label>
            <label className="text-xs font-medium text-(--text-4)">
              描述
              <input
                className={`mt-1.5 ${inputClass}`}
                onChange={(event) =>
                  setKbForm({ ...kbForm, description: event.target.value })
                }
                placeholder="部署、迁移与故障处理文档"
                value={kbForm.description}
              />
            </label>
          </div>
          <div className="mt-3 flex justify-end gap-2">
            <button
              className="rounded-xl border border-(--line) bg-(--fill-1) px-4 py-2 text-sm text-(--text-3) hover:text-(--text-1)"
              onClick={() => setCreating(false)}
              type="button"
            >
              取消
            </button>
            <button
              className="rounded-xl bg-blue-500 px-4 py-2 text-sm font-medium text-white hover:bg-blue-400"
              onClick={() => void submitCreate()}
              type="button"
            >
              创建
            </button>
          </div>
        </div>
      ) : null}

      <div className="grid min-h-0 flex-1 grid-cols-[280px_minmax(0,1fr)] max-lg:grid-cols-1">
        <aside className="min-h-0 min-w-0 overflow-y-auto border-r border-(--line) p-4 max-lg:border-b max-lg:border-r-0">
          {knowledgeBases.length === 0 && !loading ? (
            <p className="px-2 text-sm leading-6 text-(--text-4)">
              还没有知识库。创建一个，把团队文档变成 Agent 可检索的证据。
            </p>
          ) : null}
          <div className="grid gap-2">
            {knowledgeBases.map((kb) => (
              <button
                className={`rounded-2xl border p-3 text-left transition ${
                  kb.id === selectedId
                    ? "border-(--accent)/50 bg-(--accent)/10"
                    : "border-(--line) bg-(--fill-1) hover:bg-(--fill-2)"
                }`}
                key={kb.id}
                onClick={() => setSelectedId(kb.id)}
                type="button"
              >
                <div className="break-words text-sm font-semibold text-(--text-1)">
                  {kb.name}
                </div>
                <div className="mt-1 line-clamp-2 break-words text-xs leading-5 text-(--text-4)">
                  {kb.description || "（无描述）"}
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5 text-[11px] text-(--text-4)">
                  <span className="rounded-full border border-(--line) px-2 py-0.5">
                    {kb.document_count} 文档
                  </span>
                  <span className="rounded-full border border-(--line) px-2 py-0.5">
                    {kb.chunk_count} chunk
                  </span>
                  <span className="rounded-full bg-(--accent)/10 px-2 py-0.5 text-(--accent)">
                    {kb.embedding_provider}
                  </span>
                </div>
              </button>
            ))}
          </div>
        </aside>

        <section className="min-h-0 min-w-0 overflow-y-auto p-5">
          {selected ? (
            <div className="grid gap-5 [&>*]:min-w-0">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <h3 className="break-words text-base font-semibold text-(--text-1)">
                    {selected.name}
                  </h3>
                  <p className="mt-1 flex flex-wrap gap-x-2 gap-y-1 text-xs text-(--text-4)">
                    <span className="break-all">{selected.embedding_model}</span>
                    <span>· {selected.embedding_dim} 维</span>
                    <span>
                      · chunk {selected.chunk_size}/{selected.chunk_overlap}
                    </span>
                  </p>
                </div>
                <button
                  className="inline-flex items-center gap-1.5 rounded-xl border border-rose-500/40 px-3 py-1.5 text-xs text-rose-400 hover:bg-rose-500/10"
                  onClick={() =>
                    void deleteKnowledgeBase(selected.id)
                      .then(() => {
                        report(`知识库「${selected.name}」已删除。`);
                        return refresh();
                      })
                      .catch((error) =>
                        report(error instanceof Error ? error.message : "删除失败", "danger"),
                      )
                  }
                  type="button"
                >
                  <Trash2 size={13} aria-hidden="true" /> 删除知识库
                </button>
              </div>

              <div className="rounded-2xl border border-(--line) bg-(--fill-1) p-4">
                <h4 className="flex items-center gap-2 text-sm font-semibold text-(--text-1)">
                  <Search size={14} aria-hidden="true" /> 检索验证台
                </h4>
                <div className="mt-3 flex gap-2">
                  <input
                    className={inputClass}
                    onChange={(event) => setQuery(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") void runQuery();
                    }}
                    placeholder="例如：数据库迁移怎么回滚？"
                    value={query}
                  />
                  <button
                    className="inline-flex h-10 shrink-0 items-center gap-2 rounded-xl bg-blue-500 px-4 text-sm font-medium text-white hover:bg-blue-400 disabled:opacity-50"
                    disabled={querying}
                    onClick={() => void runQuery()}
                    type="button"
                  >
                    {querying ? (
                      <Loader2 className="animate-spin" size={14} aria-hidden="true" />
                    ) : (
                      "检索"
                    )}
                  </button>
                </div>
                {queryResult ? (
                  <div className="mt-3 grid gap-2">
                    <p className="text-xs text-(--text-4)">
                      后端 {queryResult.backend} · 候选 {queryResult.candidate_count} · 命中{" "}
                      {queryResult.chunks.length}
                    </p>
                    {queryResult.chunks.length ? (
                      queryResult.chunks.map((chunk) => (
                        <div
                          className="rounded-xl border border-(--line) bg-(--surface) p-3"
                          key={chunk.chunk_id}
                        >
                          <div className="flex items-baseline justify-between gap-3">
                            <span className="text-xs font-semibold text-(--accent)">
                              {chunk.citation}
                            </span>
                            <span className="shrink-0 text-[11px] text-(--text-4)">
                              综合 {chunk.final_score.toFixed(2)}
                            </span>
                          </div>
                          <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-(--text-3)">
                            {chunk.content}
                          </p>
                        </div>
                      ))
                    ) : (
                      <p className="text-sm text-(--text-4)">没有超过相关度阈值的内容。</p>
                    )}
                  </div>
                ) : null}
              </div>

              <div className="rounded-2xl border border-(--line) bg-(--fill-1) p-4">
                <h4 className="text-sm font-semibold text-(--text-1)">摄取新文档</h4>
                <div className="mt-3 grid gap-3">
                  <input
                    className={inputClass}
                    onChange={(event) =>
                      setDocumentForm({ ...documentForm, title: event.target.value })
                    }
                    placeholder="文档标题，如：部署手册 v2"
                    value={documentForm.title}
                  />
                  <textarea
                    className="min-h-32 w-full rounded-xl border border-(--line) bg-(--field) px-3 py-2.5 text-sm leading-6 text-(--text-1) outline-none transition placeholder:text-(--text-5) focus:border-(--accent)/60"
                    onChange={(event) =>
                      setDocumentForm({ ...documentForm, content: event.target.value })
                    }
                    placeholder="粘贴要入库的文档内容（纯文本 / Markdown）…"
                    value={documentForm.content}
                  />
                  <div className="flex justify-end">
                    <button
                      className="inline-flex items-center gap-2 rounded-xl bg-blue-500 px-4 py-2 text-sm font-medium text-white hover:bg-blue-400 disabled:opacity-50"
                      disabled={ingesting}
                      onClick={() => void submitIngest()}
                      type="button"
                    >
                      {ingesting ? (
                        <Loader2 className="animate-spin" size={14} aria-hidden="true" />
                      ) : null}
                      切分并写入索引
                    </button>
                  </div>
                </div>

                <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-(--line-soft) pt-4">
                  <div>
                    <p className="text-sm font-semibold text-(--text-1)">
                      图片解析入库（多模态）
                    </p>
                    <p className="mt-0.5 text-xs leading-5 text-(--text-4)">
                      截图、图表、扫描件由视觉模型（qwen-vl）提取文字与图表结构后入库，
                      图里的内容从此可以被检索和引用
                    </p>
                  </div>
                  <input
                    accept="image/png,image/jpeg,image/webp,image/gif"
                    className="hidden"
                    onChange={(event) => {
                      const file = event.target.files?.[0];
                      if (file) void submitImage(file);
                    }}
                    ref={imageInputRef}
                    type="file"
                  />
                  <button
                    className="inline-flex items-center gap-2 rounded-xl border border-(--accent)/40 bg-(--accent)/10 px-4 py-2 text-sm font-medium text-(--accent) transition hover:bg-(--accent)/20 disabled:opacity-50"
                    disabled={imageIngesting}
                    onClick={() => imageInputRef.current?.click()}
                    type="button"
                  >
                    {imageIngesting ? (
                      <>
                        <Loader2 className="animate-spin" size={14} aria-hidden="true" />
                        视觉模型解析中…
                      </>
                    ) : (
                      <>
                        <ImagePlus size={14} aria-hidden="true" />
                        选择图片解析入库
                      </>
                    )}
                  </button>
                </div>
              </div>

              <div>
                <h4 className="text-sm font-semibold text-(--text-1)">
                  文档（{documents.length}）
                </h4>
                <div className="mt-3 grid gap-2">
                  {documents.length === 0 ? (
                    <p className="text-sm text-(--text-4)">
                      知识库为空。摄取第一份文档后即可检索。
                    </p>
                  ) : (
                    documents.map((document) => (
                      <div
                        className="flex items-start justify-between gap-3 rounded-2xl border border-(--line) bg-(--fill-1) p-3.5"
                        key={document.id}
                      >
                        <div className="min-w-0">
                          <div className="text-sm font-semibold text-(--text-1)">
                            {document.title}
                          </div>
                          <div className="mt-1.5 flex flex-wrap gap-2 text-[11px] text-(--text-4)">
                            <span
                              className={`rounded-full border px-2 py-0.5 ${
                                document.status === "ready"
                                  ? "border-emerald-500/40 text-emerald-400"
                                  : document.status === "failed"
                                    ? "border-rose-500/40 text-rose-400"
                                    : "border-(--line)"
                              }`}
                            >
                              {DOCUMENT_STATUS_LABELS[document.status] || document.status}
                            </span>
                            {document.source_type === "image" ? (
                              <span className="rounded-full border border-(--accent)/40 px-2 py-0.5 text-(--accent)">
                                图片解析
                              </span>
                            ) : null}
                            <span>{document.chunk_count} chunk</span>
                            <span>{document.content_chars} 字符</span>
                          </div>
                          {document.status === "failed" && document.error ? (
                            <p className="mt-1.5 text-xs text-rose-400">{document.error}</p>
                          ) : null}
                        </div>
                        <div className="flex shrink-0 gap-2">
                          <button
                            className="rounded-lg border border-(--line) px-2.5 py-1.5 text-xs text-(--text-3) hover:text-(--text-1)"
                            onClick={() =>
                              void reingestKnowledgeDocument(document.id)
                                .then(() => refreshDocuments(selected.id))
                                .catch((error) =>
                                  report(
                                    error instanceof Error ? error.message : "重建失败",
                                    "danger",
                                  ),
                                )
                            }
                            type="button"
                          >
                            重建索引
                          </button>
                          <button
                            className="rounded-lg border border-rose-500/40 px-2.5 py-1.5 text-xs text-rose-400 hover:bg-rose-500/10"
                            onClick={() =>
                              void deleteKnowledgeDocument(document.id)
                                .then(() =>
                                  Promise.all([refresh(), refreshDocuments(selected.id)]),
                                )
                                .catch((error) =>
                                  report(
                                    error instanceof Error ? error.message : "删除失败",
                                    "danger",
                                  ),
                                )
                            }
                            type="button"
                          >
                            删除
                          </button>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          ) : (
            <p className="text-sm text-(--text-4)">选择左侧知识库，或创建一个新知识库。</p>
          )}
        </section>
      </div>
    </section>
  );
}
