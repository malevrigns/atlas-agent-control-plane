import type {
  ApiEnvelope,
  AtlasRequestOptions,
  ChatMessageList,
  ChatSession,
  ChatSessionEventList,
  ChatSessionList,
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
  SseRecord,
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

// ===================== 会话与对话 API =====================

export const sessionsApi = {
  list: () => atlasRequest<ChatSessionList>("/api/sessions"),
  create: (title: string) =>
    atlasRequest<ChatSession>("/api/sessions", { method: "POST", body: { title } }),
  remove: (sessionId: string) =>
    atlasRequest<void>(`/api/sessions/${sessionId}`, { method: "DELETE" }),
  messages: (sessionId: string) =>
    atlasRequest<ChatMessageList>(`/api/sessions/${sessionId}/messages`),
  events: (sessionId: string) =>
    atlasRequest<ChatSessionEventList>(`/api/sessions/${sessionId}/events`),
  markRead: (sessionId: string) =>
    atlasRequest<ChatSession>(`/api/sessions/${sessionId}/read`, {
      method: "POST",
      body: {},
    }),
  stop: (sessionId: string) =>
    atlasRequest<ChatSession>(`/api/sessions/${sessionId}/stop`, {
      method: "POST",
      body: {},
    }),
};

/** 增量解析 SSE 文本流：喂入任意大小的文本块，产出完整记录。 */
export function createSseParser(onRecord: (record: SseRecord) => void) {
  let buffer = "";

  function parseBlock(block: string) {
    let event = "message";
    const dataLines: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice("event:".length).trim();
      if (line.startsWith("data:")) dataLines.push(line.slice("data:".length).trim());
    }
    if (!dataLines.length) return;
    try {
      onRecord({ event, data: JSON.parse(dataLines.join("\n")) as Record<string, unknown> });
    } catch {
      // 单条记录损坏时跳过，不中断整个流。
    }
  }

  return {
    push(text: string) {
      buffer += text;
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() ?? "";
      for (const block of blocks) {
        const clean = block.trim();
        if (clean) parseBlock(clean);
      }
    },
    end() {
      const clean = buffer.trim();
      buffer = "";
      if (clean) parseBlock(clean);
    },
  };
}

/**
 * 发送消息并以 SSE 流式接收 Agent 执行过程。
 *
 * Electron 环境走主进程流式 IPC；浏览器开发环境退回 fetch reader。
 * 返回 cancel 函数。
 */
export function streamSessionMessage(
  sessionId: string,
  content: string,
  handlers: {
    onRecord: (record: SseRecord) => void;
    onEnd: () => void;
    onError: (message: string) => void;
  },
): () => void {
  const path = `/api/sessions/${sessionId}/messages/stream`;
  const parser = createSseParser(handlers.onRecord);

  if (window.atlasDesktop?.stream) {
    const cancel = window.atlasDesktop.stream(path, { content }, {
      onChunk: (text) => parser.push(text),
      onEnd: () => {
        parser.end();
        handlers.onEnd();
      },
      onError: (message) => handlers.onError(message),
    });
    return cancel;
  }

  const controller = new AbortController();
  void (async () => {
    try {
      const response = await fetch(`${API_BASE}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
        signal: controller.signal,
      });
      if (!response.ok || !response.body) {
        throw new Error(`Atlas API returned ${response.status}`);
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        parser.push(decoder.decode(value, { stream: true }));
      }
      parser.end();
      handlers.onEnd();
    } catch (error) {
      if (controller.signal.aborted) handlers.onEnd();
      else handlers.onError(error instanceof Error ? error.message : "stream failed");
    }
  })();
  return () => controller.abort();
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
