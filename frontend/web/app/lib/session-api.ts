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

export function createSession(
  title: string,
  workspaceDir = "",
  fullAccess = false,
): Promise<SessionItem> {
  return requestApi<SessionItem>("/api/sessions", {
    method: "POST",
    body: JSON.stringify({
      title,
      workspace_dir: workspaceDir,
      full_access: fullAccess,
    }),
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

export async function deleteSessionFile(
  sessionId: string,
  sessionFileId: string,
): Promise<void> {
  return requestApi<void>(`/api/sessions/${sessionId}/files/${sessionFileId}`, {
    method: "DELETE",
  });
}

export async function streamMessage(
  sessionId: string,
  content: string,
  onEvent: (event: StreamEvent) => void | Promise<void>,
  skillIds: string[] = [],
  resume = false,
  signal?: AbortSignal,
) {
  // Always same-origin: the App Router route at
  // app/api/sessions/[sessionId]/messages/stream pipes the backend SSE
  // so Next rewrites cannot buffer it and the session cookie is sent.
  const response = await fetch(
    `/api/sessions/${sessionId}/messages/stream`,
    {
      method: "POST",
      credentials: "include",
      signal,
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify({ content, skill_ids: skillIds, resume }),
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

  await readSseStream(response, onEvent, signal);
}
