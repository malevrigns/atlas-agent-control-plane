export type SessionStatus = "idle" | "running" | "stopped";

export type Session = {
  id: string;
  title: string;
  status: SessionStatus;
  unread_count: number;
  created_at: string;
  updated_at: string;
  workspace_dir: string;
  full_access: boolean;
};

export type ChatMessage = {
  id: string;
  session_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
};

export type SessionEvent = {
  id: string;
  session_id: string;
  type: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type UploadedFile = {
  id: string;
  original_name: string;
  content_type: string;
  size: number;
  download_url: string;
  created_at: string;
};

export type SessionFile = {
  id: string;
  session_id: string;
  file: UploadedFile;
  created_at: string;
};

export function nowIso(): string {
  return new Date().toISOString();
}

export function newId(): string {
  return crypto.randomUUID();
}

export function normalizeWorkspaceDir(raw: string): string {
  let value = raw.trim();
  if (!value) {
    return "";
  }
  value = value.replaceAll("\\", "/");
  if (value.length >= 2 && value[1] === ":") {
    value = value.slice(2);
  }
  value = value.replace(/^\/+|\/+$/g, "");
  const parts = value.split("/").filter((part) => part && part !== ".");
  if (parts.some((part) => part === "..")) {
    throw Object.assign(new Error("工作区路径不能包含 .."), { code: 400 });
  }
  return parts.join("/");
}
