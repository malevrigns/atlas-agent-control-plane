import { ApiRequestError, requestApi } from "./api";
import type { ApiResponse } from "../types";

// ===================== RAG 知识库类型 =====================

export type KnowledgeBase = {
  id: string;
  name: string;
  description: string;
  project_id: string;
  embedding_provider: string;
  embedding_model: string;
  embedding_dim: number;
  chunk_size: number;
  chunk_overlap: number;
  document_count: number;
  chunk_count: number;
  created_at: string | null;
  updated_at: string | null;
};

export type KnowledgeDocument = {
  id: string;
  knowledge_base_id: string;
  title: string;
  source_type: string;
  source_ref: string;
  status: "pending" | "processing" | "ready" | "failed";
  chunk_count: number;
  content_chars: number;
  error: string;
  created_at: string | null;
  updated_at: string | null;
};

export type RetrievedChunk = {
  chunk_id: string;
  document_id: string;
  document_title: string;
  seq: number;
  content: string;
  vector_score: number;
  lexical_score: number;
  final_score: number;
  matched_terms: string[];
  citation: string;
};

export type RagQueryResult = {
  query: string;
  knowledge_base_id: string;
  backend: string;
  embedding_provider: string;
  top_k: number;
  candidate_count: number;
  total_chars: number;
  context_text: string;
  chunks: RetrievedChunk[];
};

// ===================== RAG 知识库 API =====================

export function fetchKnowledgeBases() {
  return requestApi<{ items: KnowledgeBase[] }>("/api/rag/knowledge-bases");
}

export function createKnowledgeBase(input: { name: string; description: string }) {
  return requestApi<KnowledgeBase>("/api/rag/knowledge-bases", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function deleteKnowledgeBase(knowledgeBaseId: string) {
  return requestApi<KnowledgeBase>(`/api/rag/knowledge-bases/${knowledgeBaseId}`, {
    method: "DELETE",
  });
}

export function fetchKnowledgeDocuments(knowledgeBaseId: string) {
  return requestApi<{ items: KnowledgeDocument[] }>(
    `/api/rag/knowledge-bases/${knowledgeBaseId}/documents`,
  );
}

export function ingestKnowledgeDocument(
  knowledgeBaseId: string,
  input: { title: string; content: string },
) {
  return requestApi<KnowledgeDocument>(
    `/api/rag/knowledge-bases/${knowledgeBaseId}/documents`,
    { method: "POST", body: JSON.stringify(input) },
  );
}

/**
 * 多模态摄取：上传图片，由服务端视觉模型（qwen-vl）解析成文本后入库。
 * multipart 请求不能带 JSON Content-Type，因此不走 requestApi。
 */
export async function ingestImageDocument(
  knowledgeBaseId: string,
  file: File,
  title = "",
): Promise<KnowledgeDocument> {
  const form = new FormData();
  form.append("upload", file);
  if (title) form.append("title", title);
  const response = await fetch(
    `/api/rag/knowledge-bases/${knowledgeBaseId}/documents/image`,
    { method: "POST", body: form, credentials: "same-origin" },
  );
  const payload = (await response.json()) as ApiResponse<KnowledgeDocument>;
  if (!response.ok || payload.code >= 400) {
    const message =
      payload.error?.user_message || payload.message || `HTTP ${response.status}`;
    throw new ApiRequestError(message, payload.code, response.status, payload.error ?? null);
  }
  if (payload.data === null) throw new Error("empty response");
  return payload.data;
}

export function reingestKnowledgeDocument(documentId: string) {
  return requestApi<KnowledgeDocument>(`/api/rag/documents/${documentId}/reingest`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function deleteKnowledgeDocument(documentId: string) {
  return requestApi<KnowledgeDocument>(`/api/rag/documents/${documentId}`, {
    method: "DELETE",
  });
}

export function queryKnowledgeBase(knowledgeBaseId: string, query: string, topK = 5) {
  return requestApi<RagQueryResult>(
    `/api/rag/knowledge-bases/${knowledgeBaseId}/query`,
    { method: "POST", body: JSON.stringify({ query, top_k: topK }) },
  );
}
