import type {
  ApiEnvelope,
  AtlasRequestOptions,
  KnowledgeBase,
  KnowledgeBaseList,
  KnowledgeDocument,
  KnowledgeDocumentList,
  RagQueryResult,
  Skill,
  SkillContextPreview,
  SkillDraftInput,
  SkillList,
  SkillRiskLevel,
} from "./types";

const API_BASE = import.meta.env.VITE_ATLAS_API_BASE || "http://localhost:8088";

/**
 * 统一的 Atlas API 请求入口。
 *
 * Electron 环境下走主进程的 IPC 通道（携带 API Key，渲染进程零凭据）；
 * 浏览器开发环境退回 fetch。
 */
export async function atlasRequest<T>(
  path: string,
  options: AtlasRequestOptions = {},
): Promise<T> {
  if (window.atlasDesktop?.request) {
    return window.atlasDesktop.request<T>(path, options);
  }
  const response = await fetch(`${API_BASE}${path}`, {
    method: options.method || "GET",
    headers: options.body ? { "Content-Type": "application/json" } : undefined,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const payload = (await response.json()) as ApiEnvelope<T>;
  if (!response.ok || Number(payload.code ?? response.status) >= 400) {
    throw new Error(payload.message || `Atlas API returned ${response.status}`);
  }
  if (payload.data === undefined) {
    throw new Error("Atlas API returned an empty response");
  }
  return payload.data;
}

// ===================== Skill 注册中心 API =====================

export const skillsApi = {
  list: (params: { search?: string; status?: string } = {}) => {
    const query = new URLSearchParams();
    if (params.search) query.set("search", params.search);
    if (params.status) query.set("status", params.status);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return atlasRequest<SkillList>(`/api/skills${suffix}`);
  },
  versions: (skillKey: string) =>
    atlasRequest<SkillList>(`/api/skills/${encodeURIComponent(skillKey)}/versions`),
  create: (input: SkillDraftInput) =>
    atlasRequest<Skill>("/api/skills", { method: "POST", body: input }),
  update: (
    skillId: string,
    input: Partial<{
      name: string;
      description: string;
      instructions: string;
      risk_level: SkillRiskLevel;
      tags: string[];
    }>,
  ) => atlasRequest<Skill>(`/api/skills/${skillId}`, { method: "PATCH", body: input }),
  publish: (skillId: string) =>
    atlasRequest<Skill>(`/api/skills/${skillId}/publish`, { method: "POST", body: {} }),
  setEnabled: (skillId: string, enabled: boolean) =>
    atlasRequest<Skill>(`/api/skills/${skillId}/enabled`, {
      method: "POST",
      body: { enabled },
    }),
  newVersion: (skillId: string) =>
    atlasRequest<Skill>(`/api/skills/${skillId}/versions`, { method: "POST", body: {} }),
  deprecate: (skillId: string) =>
    atlasRequest<Skill>(`/api/skills/${skillId}/deprecate`, { method: "POST", body: {} }),
  remove: (skillId: string) =>
    atlasRequest<Skill>(`/api/skills/${skillId}`, { method: "DELETE" }),
  previewContext: (query: string) =>
    atlasRequest<SkillContextPreview>(
      `/api/skills/context?query=${encodeURIComponent(query)}`,
    ),
};

// ===================== RAG 知识库 API =====================

export const ragApi = {
  listKnowledgeBases: () =>
    atlasRequest<KnowledgeBaseList>("/api/rag/knowledge-bases"),
  createKnowledgeBase: (input: { name: string; description: string }) =>
    atlasRequest<KnowledgeBase>("/api/rag/knowledge-bases", {
      method: "POST",
      body: input,
    }),
  deleteKnowledgeBase: (knowledgeBaseId: string) =>
    atlasRequest<KnowledgeBase>(`/api/rag/knowledge-bases/${knowledgeBaseId}`, {
      method: "DELETE",
    }),
  listDocuments: (knowledgeBaseId: string) =>
    atlasRequest<KnowledgeDocumentList>(
      `/api/rag/knowledge-bases/${knowledgeBaseId}/documents`,
    ),
  ingestDocument: (
    knowledgeBaseId: string,
    input: { title: string; content: string },
  ) =>
    atlasRequest<KnowledgeDocument>(
      `/api/rag/knowledge-bases/${knowledgeBaseId}/documents`,
      { method: "POST", body: input },
    ),
  reingestDocument: (documentId: string) =>
    atlasRequest<KnowledgeDocument>(`/api/rag/documents/${documentId}/reingest`, {
      method: "POST",
      body: {},
    }),
  deleteDocument: (documentId: string) =>
    atlasRequest<KnowledgeDocument>(`/api/rag/documents/${documentId}`, {
      method: "DELETE",
    }),
  query: (knowledgeBaseId: string, query: string) =>
    atlasRequest<RagQueryResult>(
      `/api/rag/knowledge-bases/${knowledgeBaseId}/query`,
      { method: "POST", body: { query } },
    ),
};
