import { ApiRequestError, requestApi } from "./api";
import { readSseStream } from "./sse";
import type {
  ChatMessage,
  ApiErrorData,
  MessageListData,
  SessionEventItem,
  SessionEventListData,
  SessionContextData,
  SessionFileItem,
  SessionFileListData,
  SessionItem,
  SessionListData,
  StreamEvent,
  ApiResponse,
} from "../types";

export function fetchSessions(): Promise<SessionItem[]> {
  return requestApi<SessionListData>("/api/sessions").then((data) => data.items);
}

export function createSession(title: string): Promise<SessionItem> {
  return requestApi<SessionItem>("/api/sessions", {
    method: "POST",
    body: JSON.stringify({ title }),
  });
}

export function deleteSession(sessionId: string): Promise<void> {
  return requestApi<void>(`/api/sessions/${sessionId}`, { method: "DELETE" });
}

export function stopSession(sessionId: string): Promise<SessionItem> {
  return requestApi<SessionItem>(`/api/sessions/${sessionId}/stop`, {
    method: "POST",
  });
}

export function clearUnread(sessionId: string): Promise<SessionItem> {
  return requestApi<SessionItem>(`/api/sessions/${sessionId}/read`, {
    method: "POST",
  });
}

export function fetchMessages(sessionId: string): Promise<ChatMessage[]> {
  return requestApi<MessageListData>(`/api/sessions/${sessionId}/messages`).then(
    (data) => data.items,
  );
}

export function fetchEvents(sessionId: string): Promise<SessionEventItem[]> {
  return requestApi<SessionEventListData>(
    `/api/sessions/${sessionId}/events`,
  ).then((data) => data.items);
}

export function fetchSessionContext(
  sessionId: string,
): Promise<SessionContextData> {
  return requestApi<SessionContextData>(`/api/sessions/${sessionId}/context`);
}

export function fetchSessionFiles(sessionId: string): Promise<SessionFileItem[]> {
  return requestApi<SessionFileListData>(`/api/sessions/${sessionId}/files`).then(
    (data) => data.items,
  );
}

export async function uploadSessionFile(
  sessionId: string,
  file: File,
): Promise<SessionFileItem> {
  const formData = new FormData();
  formData.append("upload", file);

  const response = await fetch(`/api/sessions/${sessionId}/files`, {
    method: "POST",
    body: formData,
  });
  const payload = (await response.json()) as {
    code: number;
    message: string;
    data: SessionFileItem | null;
    error?: ApiErrorData | null;
  };
  if (!response.ok || payload.code >= 400) {
    const message = payload.error?.user_message || payload.message || `HTTP ${response.status}`;
    throw new ApiRequestError(message, payload.code, response.status, payload.error ?? null);
  }
  if (!payload.data) {
    throw new Error("empty response");
  }
  return payload.data;
}

// 本地开发时 Next 的 rewrite 代理会把 SSE 整体缓冲，逐字流会退化成
// “憋很久然后一次性弹出”。设置 NEXT_PUBLIC_STREAM_BASE（如
// http://127.0.0.1:8000）让流式端点直连后端绕过代理；后端 CORS 已放行
// localhost:3000。生产环境不设置该变量，走 Nginx（已配 proxy_buffering off）。
const STREAM_BASE = process.env.NEXT_PUBLIC_STREAM_BASE ?? "";

export async function streamMessage(
  sessionId: string,
  content: string,
  onEvent: (event: StreamEvent) => void | Promise<void>,
  skillIds: string[] = [],
) {
  const response = await fetch(
    `${STREAM_BASE}/api/sessions/${sessionId}/messages/stream`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify({ content, skill_ids: skillIds }),
    },
  );

  if (!response.ok) {
    try {
      const payload = (await response.json()) as ApiResponse<unknown>;
      const message = payload.error?.user_message || payload.message || `HTTP ${response.status}`;
      throw new ApiRequestError(message, payload.code, response.status, payload.error ?? null);
    } catch (error) {
      if (error instanceof ApiRequestError) {
        throw error;
      }
      throw new Error(`HTTP ${response.status}`);
    }
  }

  await readSseStream(response, onEvent);
}
