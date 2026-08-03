import { requestApi } from "./api";
import type {
  AgentMemoryItem,
  AgentMemoryListData,
  MemoryCandidateListData,
  MemoryKind,
} from "../types";

export function fetchMemories(): Promise<AgentMemoryItem[]> {
  return requestApi<AgentMemoryListData>("/api/memories").then(
    (data) => data.items,
  );
}

export function createMemory(payload: {
  kind: MemoryKind;
  content: string;
  importance: number;
  source_session_id?: string | null;
  source_event_id?: string | null;
  expires_at?: string | null;
  metadata?: Record<string, unknown>;
}): Promise<AgentMemoryItem> {
  return requestApi<AgentMemoryItem>("/api/memories", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateMemory(
  memoryId: string,
  payload: {
    content?: string;
    importance?: number;
    enabled?: boolean;
  },
): Promise<AgentMemoryItem> {
  return requestApi<AgentMemoryItem>(`/api/memories/${memoryId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteMemory(memoryId: string): Promise<AgentMemoryItem> {
  return requestApi<AgentMemoryItem>(`/api/memories/${memoryId}`, {
    method: "DELETE",
  });
}

export function extractMemoryCandidates(
  sessionId: string,
): Promise<MemoryCandidateListData> {
  return requestApi<MemoryCandidateListData>("/api/memories/extract", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
  });
}
