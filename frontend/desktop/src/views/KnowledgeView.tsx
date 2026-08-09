import {
  ArrowClockwise,
  Books,
  MagnifyingGlass,
  Plus,
  Trash,
} from "@phosphor-icons/react";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { ragApi } from "../api";
import { InlineNotice, ThemeSelect, formatTimestamp } from "../components";
import type {
  KnowledgeBase,
  KnowledgeDocument,
  RagQueryResult,
  Theme,
} from "../types";

const DOCUMENT_STATUS_LABELS: Record<string, string> = {
  pending: "待处理",
  processing: "摄取中",
  ready: "已就绪",
  failed: "失败",
};

interface KnowledgeViewProps {
  theme: Theme;
  setTheme: Dispatch<SetStateAction<Theme>>;
}

export function KnowledgeView({ theme, setTheme }: KnowledgeViewProps) {
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);
  const [notice, setNotice] = useState("");
  const [noticeTone, setNoticeTone] = useState<"info" | "danger">("info");
  const [creatingKb, setCreatingKb] = useState(false);
  const [kbForm, setKbForm] = useState({ name: "", description: "" });
  const [ingesting, setIngesting] = useState(false);
  const [documentForm, setDocumentForm] = useState({ title: "", content: "" });
  const [query, setQuery] = useState("");
  const [querying, setQuerying] = useState(false);
  const [queryResult, setQueryResult] = useState<RagQueryResult | null>(null);

  const selected = useMemo(
    () => knowledgeBases.find((kb) => kb.id === selectedId) || null,
    [knowledgeBases, selectedId],
  );

  const report = useCallback((message: string, tone: "info" | "danger" = "info") => {
    setNotice(message);
    setNoticeTone(tone);
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await ragApi.listKnowledgeBases();
      setKnowledgeBases(data.items);
      setOffline(false);
      setSelectedId((current) => {
        if (current && data.items.some((kb) => kb.id === current)) return current;
        return data.items[0]?.id ?? null;
      });
    } catch (error) {
      setOffline(true);
      report(error instanceof Error ? error.message : "无法连接知识库服务", "danger");
    } finally {
      setLoading(false);
    }
  }, [report]);

  const refreshDocuments = useCallback(async (knowledgeBaseId: string) => {
    try {
      const data = await ragApi.listDocuments(knowledgeBaseId);
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

  async function createKnowledgeBase() {
    if (!kbForm.name.trim()) {
      report("知识库名称是必填项。", "danger");
      return;
    }
    try {
      const created = await ragApi.createKnowledgeBase({
        name: kbForm.name.trim(),
        description: kbForm.description.trim(),
      });
      report(`知识库「${created.name}」已创建（${created.embedding_provider} · ${created.embedding_dim} 维）。`);
      setCreatingKb(false);
      setKbForm({ name: "", description: "" });
      await refresh();
      setSelectedId(created.id);
    } catch (error) {
      report(error instanceof Error ? error.message : "创建失败", "danger");
    }
  }

  async function ingestDocument() {
    if (!selected) return;
    if (!documentForm.title.trim() || !documentForm.content.trim()) {
      report("文档标题与内容都是必填项。", "danger");
      return;
    }
    setIngesting(true);
    try {
      const document = await ragApi.ingestDocument(selected.id, {
        title: documentForm.title.trim(),
        content: documentForm.content,
      });
      if (document.status === "ready") {
        report(`文档已摄取：切分为 ${document.chunk_count} 个 chunk 并写入向量索引。`);
      } else {
        report(`摄取失败：${document.error || "未知原因"}`, "danger");
      }
      setDocumentForm({ title: "", content: "" });
      await Promise.all([refresh(), refreshDocuments(selected.id)]);
    } catch (error) {
      report(error instanceof Error ? error.message : "摄取失败", "danger");
    } finally {
      setIngesting(false);
    }
  }

  async function runQuery() {
    if (!selected) return;
    const clean = query.trim();
    if (!clean) return;
    setQuerying(true);
    try {
      setQueryResult(await ragApi.query(selected.id, clean));
      report("检索完成。");
    } catch (error) {
      report(error instanceof Error ? error.message : "检索失败", "danger");
    } finally {
      setQuerying(false);
    }
  }

  async function removeDocument(document: KnowledgeDocument) {
    try {
      await ragApi.deleteDocument(document.id);
      report(`文档「${document.title}」及其向量已删除。`);
      if (selected) await Promise.all([refresh(), refreshDocuments(selected.id)]);
    } catch (error) {
      report(error instanceof Error ? error.message : "删除失败", "danger");
    }
  }

  async function reingestDocument(document: KnowledgeDocument) {
    try {
      const updated = await ragApi.reingestDocument(document.id);
      report(
        updated.status === "ready"
          ? `文档「${document.title}」已重建索引。`
          : `重建失败：${updated.error || "未知原因"}`,
      );
      if (selected) await refreshDocuments(selected.id);
    } catch (error) {
      report(error instanceof Error ? error.message : "重建失败", "danger");
    }
  }

  async function removeKnowledgeBase(kb: KnowledgeBase) {
    try {
      await ragApi.deleteKnowledgeBase(kb.id);
      report(`知识库「${kb.name}」已删除。`);
      await refresh();
    } catch (error) {
      report(error instanceof Error ? error.message : "删除失败", "danger");
    }
  }

  return (
    <section className="panel-workspace" aria-label="RAG 知识库">
      <header className="panel-header">
        <div>
          <h1><Books size={22} weight="duotone" /> 知识库（RAG）</h1>
          <p className="panel-subtitle">
            摄取文档 → 切分向量化 → 带引用检索。Agent 通过 knowledge_search 工具消费同一条链路。
          </p>
        </div>
        <div className="header-actions">
          <ThemeSelect theme={theme} onChange={setTheme} />
          <button
            className="outline-button"
            type="button"
            onClick={() => setCreatingKb((value) => !value)}
          >
            <Plus size={17} weight="bold" /> 新建知识库
          </button>
          <button className="icon-button" type="button" onClick={() => void refresh()} aria-label="刷新">
            <ArrowClockwise size={18} className={loading ? "spin" : undefined} />
          </button>
        </div>
      </header>

      <InlineNotice notice={notice} tone={noticeTone} />
      {offline ? (
        <InlineNotice notice="未连接控制平面：请启动后端后重试。" tone="danger" />
      ) : null}

      {creatingKb ? (
        <div className="editor-card" aria-label="新建知识库">
          <h2>新建知识库</h2>
          <div className="form-grid">
            <label>名称
              <input
                value={kbForm.name}
                onChange={(event) => setKbForm({ ...kbForm, name: event.target.value })}
                placeholder="工程运维知识库"
              />
            </label>
            <label>描述
              <input
                value={kbForm.description}
                onChange={(event) => setKbForm({ ...kbForm, description: event.target.value })}
                placeholder="部署、迁移与故障处理文档"
              />
            </label>
          </div>
          <div className="editor-actions">
            <button className="outline-button" type="button" onClick={() => setCreatingKb(false)}>取消</button>
            <button className="primary-button" type="button" onClick={() => void createKnowledgeBase()}>创建</button>
          </div>
        </div>
      ) : null}

      <div className="panel-body">
        <div className="entity-list" role="list" aria-label="知识库列表">
          {knowledgeBases.length === 0 && !loading ? (
            <p className="empty-hint">还没有知识库。创建一个，把团队文档变成 Agent 可检索的证据。</p>
          ) : null}
          {knowledgeBases.map((kb) => (
            <button
              key={kb.id}
              type="button"
              role="listitem"
              className={`entity-item ${kb.id === selectedId ? "selected" : ""}`}
              onClick={() => setSelectedId(kb.id)}
            >
              <span className="entity-title">
                <strong>{kb.name}</strong>
                <small>{kb.description || "（无描述）"}</small>
              </span>
              <span className="entity-meta">
                <span className="status-chip">{kb.document_count} 文档</span>
                <span className="status-chip">{kb.chunk_count} chunk</span>
                <span className="risk-chip">{kb.embedding_provider}</span>
              </span>
            </button>
          ))}
        </div>

        <div className="entity-detail" aria-label="知识库详情">
          {selected ? (
            <>
              <div className="detail-header">
                <div>
                  <h2>{selected.name}</h2>
                  <p className="detail-meta">
                    <span>{selected.embedding_model} · {selected.embedding_dim} 维</span>
                    <span>chunk {selected.chunk_size}/{selected.chunk_overlap}</span>
                    <span>更新于 {formatTimestamp(selected.updated_at)}</span>
                  </p>
                </div>
                <div className="detail-actions">
                  <button
                    className="outline-button danger"
                    type="button"
                    onClick={() => void removeKnowledgeBase(selected)}
                  >
                    <Trash size={16} /> 删除知识库
                  </button>
                </div>
              </div>

              <div className="query-block">
                <h3><MagnifyingGlass size={16} /> 检索验证台</h3>
                <div className="query-row">
                  <input
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") void runQuery();
                    }}
                    placeholder="例如：数据库迁移怎么回滚？"
                    aria-label="检索查询"
                  />
                  <button className="primary-button" type="button" disabled={querying} onClick={() => void runQuery()}>
                    {querying ? <ArrowClockwise size={16} className="spin" /> : "检索"}
                  </button>
                </div>
                {queryResult ? (
                  <div className="query-result">
                    <p className="detail-meta">
                      <span>后端 {queryResult.backend}</span>
                      <span>候选 {queryResult.candidate_count}</span>
                      <span>命中 {queryResult.chunks.length}</span>
                      <span>{queryResult.total_chars} 字符</span>
                    </p>
                    {queryResult.chunks.length ? (
                      queryResult.chunks.map((chunk) => (
                        <div key={chunk.chunk_id} className="hit-card">
                          <div className="hit-card-head">
                            <strong>{chunk.citation}</strong>
                            <span>
                              综合 {chunk.final_score.toFixed(2)} · 向量 {chunk.vector_score.toFixed(2)} · 词法 {chunk.lexical_score.toFixed(2)}
                            </span>
                          </div>
                          <p>{chunk.content}</p>
                        </div>
                      ))
                    ) : (
                      <p className="empty-hint">没有超过相关度阈值的内容。</p>
                    )}
                  </div>
                ) : null}
              </div>

              <div className="ingest-block">
                <h3>摄取新文档</h3>
                <div className="form-grid">
                  <label className="span-2">标题
                    <input
                      value={documentForm.title}
                      onChange={(event) => setDocumentForm({ ...documentForm, title: event.target.value })}
                      placeholder="部署手册 v2"
                    />
                  </label>
                  <label className="span-2">正文（纯文本 / Markdown）
                    <textarea
                      rows={6}
                      value={documentForm.content}
                      onChange={(event) => setDocumentForm({ ...documentForm, content: event.target.value })}
                      placeholder="粘贴要入库的文档内容…"
                    />
                  </label>
                </div>
                <div className="editor-actions">
                  <button className="primary-button" type="button" disabled={ingesting} onClick={() => void ingestDocument()}>
                    {ingesting ? "摄取中…" : "切分并写入索引"}
                  </button>
                </div>
              </div>

              <div className="documents-block">
                <h3>文档（{documents.length}）</h3>
                {documents.length === 0 ? (
                  <p className="empty-hint">知识库为空。摄取第一份文档后即可检索。</p>
                ) : (
                  <ul className="document-list">
                    {documents.map((document) => (
                      <li key={document.id} className="document-item">
                        <div>
                          <strong>{document.title}</strong>
                          <p className="detail-meta">
                            <span className={`status-chip ${document.status}`}>
                              {DOCUMENT_STATUS_LABELS[document.status] || document.status}
                            </span>
                            <span>{document.chunk_count} chunk</span>
                            <span>{document.content_chars} 字符</span>
                            <span>{formatTimestamp(document.created_at)}</span>
                          </p>
                          {document.status === "failed" && document.error ? (
                            <p className="error-text">{document.error}</p>
                          ) : null}
                        </div>
                        <div className="detail-actions">
                          <button
                            className="outline-button"
                            type="button"
                            onClick={() => void reingestDocument(document)}
                          >
                            重建索引
                          </button>
                          <button
                            className="outline-button danger"
                            type="button"
                            onClick={() => void removeDocument(document)}
                          >
                            删除
                          </button>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </>
          ) : (
            <p className="empty-hint">选择左侧知识库，或创建一个新知识库。</p>
          )}
        </div>
      </div>
    </section>
  );
}
