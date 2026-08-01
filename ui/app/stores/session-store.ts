import { create } from "zustand";

import { fetchFilePreview } from "../lib/file-api";
import { ApiRequestError } from "../lib/api";
import {
  clearUnread,
  createSession,
  deleteSession,
  fetchEvents,
  fetchMessages,
  fetchSessionContext,
  fetchSessionFiles,
  fetchSessions,
  streamMessage,
  stopSession,
  uploadSessionFile,
} from "../lib/session-api";
import type {
  AgentTaskItem,
  ChatMessage,
  FilePreviewData,
  LoadState,
  AgentPlan,
  SessionContextData,
  SessionEventItem,
  SessionFileItem,
  SessionItem,
  StreamEvent,
} from "../types";

type SessionState = {
  actionError: string | null;
  attachments: SessionFileItem[];
  draft: string;
  events: LoadState<SessionEventItem[]>;
  files: LoadState<SessionFileItem[]>;
  filePreview: LoadState<FilePreviewData | null>;
  latestPlan: AgentPlan | null;
  messages: LoadState<ChatMessage[]>;
  selectedSessionId: string | null;
  selectedFile: SessionFileItem | null;
  clearingUnread: boolean;
  currentTask: AgentTaskItem | null;
  context: LoadState<SessionContextData | null>;
  sendingMessage: boolean;
  planning: boolean;
  executingPlan: boolean;
  sessions: LoadState<SessionItem[]>;
  stoppingSession: boolean;
  submitting: boolean;
  title: string;
  uploadingFile: boolean;
};

type SessionActions = {
  createSession: () => Promise<void>;
  deleteSession: (sessionId: string) => Promise<void>;
  loadSessionDetail: (sessionId: string) => Promise<void>;
  loadSessionContext: (sessionId: string) => Promise<void>;
  loadFilePreview: (fileId: string) => Promise<void>;
  refreshSessions: () => Promise<void>;
  clearUnread: () => Promise<void>;
  selectSession: (sessionId: string | null) => void;
  selectFile: (file: SessionFileItem | null) => void;
  sendMessage: () => Promise<void>;
  stopSession: () => Promise<void>;
  uploadAttachment: (file: File) => Promise<void>;
  setActionError: (message: string | null) => void;
  setDraft: (draft: string) => void;
  setTitle: (title: string) => void;
};

const initialDetailState = {
  messages: { type: "ready", data: [] } as LoadState<ChatMessage[]>,
  events: { type: "ready", data: [] } as LoadState<SessionEventItem[]>,
  files: { type: "ready", data: [] } as LoadState<SessionFileItem[]>,
  context: { type: "ready", data: null } as LoadState<SessionContextData | null>,
  filePreview: { type: "ready", data: null } as LoadState<FilePreviewData | null>,
};

function getErrorMessage(error: unknown) {
  if (error instanceof ApiRequestError) {
    const suggestion = error.apiError?.suggestion;
    const requestId = error.apiError?.request_id;
    return [
      error.message,
      suggestion ? `建议：${suggestion}` : "",
      requestId ? `request_id：${requestId}` : "",
    ]
      .filter(Boolean)
      .join("\n");
  }
  return error instanceof Error ? error.message : "unknown error";
}

function sleep(ms: number) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function getPresentationDelay(eventName: string) {
  // ===================== 第1步：给不同事件留出可感知的展示节奏 =====================
  // 这里不是伪造后端耗时，而是避免浏览器把 SSE 瞬间批量刷出，导致用户看不清执行顺序。
  if (eventName === "message_created") {
    return 120;
  }
  if (eventName === "plan_created") {
    return 460;
  }
  if (eventName === "step_started") {
    return 560;
  }
  if (eventName === "tool_called") {
    return 720;
  }
  if (eventName === "step_completed") {
    return 460;
  }
  if (eventName === "task_done" || eventName === "task_error") {
    return 280;
  }
  return 120;
}

function updateSession(items: SessionItem[], nextSession: SessionItem) {
  return items.map((item) => (item.id === nextSession.id ? nextSession : item));
}

function toSessionEventItem(event: StreamEvent): SessionEventItem | null {
  if (event.event === "session_status") {
    const data = event.data as Partial<SessionItem>;
    if (!data.id || !data.status || !data.updated_at) {
      return null;
    }
    return {
      id: `${data.id}-${data.status}-${Date.now()}`,
      session_id: String(data.id),
      type: `session_status:${data.status}`,
      payload: {
        status: data.status,
      },
      created_at: String(data.updated_at),
    };
  }

  if (
    [
      "message_created",
      "plan_created",
      "step_started",
      "tool_called",
      "step_completed",
      "task_done",
      "task_error",
    ].includes(event.event)
  ) {
    const data = event.data as Partial<SessionEventItem>;
    if (!data.id || !data.session_id || !data.type || !data.created_at) {
      return null;
    }
    return {
      id: String(data.id),
      session_id: String(data.session_id),
      type: String(data.type),
      payload:
        typeof data.payload === "object" && data.payload !== null
          ? (data.payload as Record<string, unknown>)
          : {},
      created_at: String(data.created_at),
    };
  }

  return null;
}

function toChatMessageItem(event: SessionEventItem): ChatMessage | null {
  if (event.type !== "message_created") {
    return null;
  }
  const messageId = event.payload.message_id;
  const role = event.payload.role;
  const content = event.payload.content;
  if (
    typeof messageId !== "string" ||
    typeof content !== "string" ||
    !["user", "assistant", "system"].includes(String(role))
  ) {
    return null;
  }
  return {
    content,
    created_at: event.created_at,
    id: messageId,
    role: role as ChatMessage["role"],
    session_id: event.session_id,
  };
}

function toSessionItem(event: StreamEvent): SessionItem | null {
  if (event.event !== "session_status") {
    return null;
  }
  const data = event.data as Partial<SessionItem>;
  if (
    !data.id ||
    !data.title ||
    !data.status ||
    !data.created_at ||
    !data.updated_at ||
    data.unread_count === undefined
  ) {
    return null;
  }
  return {
    id: String(data.id),
    title: String(data.title),
    status: String(data.status),
    unread_count: Number(data.unread_count),
    created_at: String(data.created_at),
    updated_at: String(data.updated_at),
  };
}

function toPlan(event: SessionEventItem): AgentPlan | null {
  if (event.type !== "plan_created") {
    return null;
  }
  const payload = event.payload as Partial<AgentPlan>;
  if (
    !payload.id ||
    !payload.title ||
    !payload.goal ||
    !payload.source ||
    !Array.isArray(payload.steps)
  ) {
    return null;
  }
  return {
    id: String(payload.id),
    title: String(payload.title),
    goal: String(payload.goal),
    source: String(payload.source),
    steps: payload.steps,
  };
}

function getLatestPlan(events: SessionEventItem[]) {
  return [...events]
    .reverse()
    .map(toPlan)
    .find((plan): plan is AgentPlan => plan !== null) ?? null;
}

function applyExecutionEvents(plan: AgentPlan | null, events: SessionEventItem[]) {
  if (!plan) {
    return null;
  }
  const nextSteps = plan.steps.map((step) => ({ ...step }));

  for (const event of events) {
    const payload = event.payload as Record<string, unknown>;
    const stepId = typeof payload.step_id === "string" ? payload.step_id : null;
    if (!stepId) {
      if (event.type === "task_error") {
        const runningStep = nextSteps.find((item) => item.status === "running");
        if (runningStep) {
          runningStep.status = "failed";
        }
      }
      continue;
    }
    const step = nextSteps.find((item) => item.id === stepId);
    if (!step) {
      continue;
    }
    if (event.type === "step_started") {
      step.status = "running";
    }
    if (event.type === "step_completed") {
      step.status = "completed";
    }
    if (event.type === "task_error") {
      step.status = "failed";
    }
  }

  return {
    ...plan,
    steps: nextSteps,
  };
}

export const useSessionStore = create<SessionState & SessionActions>(
  (set, get) => ({
    actionError: null,
    attachments: [],
    clearingUnread: false,
    currentTask: null,
    context: initialDetailState.context,
    draft: "",
    events: initialDetailState.events,
    files: initialDetailState.files,
    filePreview: initialDetailState.filePreview,
    latestPlan: null,
    messages: initialDetailState.messages,
    selectedSessionId: null,
    selectedFile: null,
    sendingMessage: false,
    planning: false,
    executingPlan: false,
    sessions: { type: "loading" },
    stoppingSession: false,
    submitting: false,
    title: "",
    uploadingFile: false,

    setActionError: (message) => set({ actionError: message }),
    setDraft: (draft) => set({ draft }),
    setTitle: (title) => set({ title }),

    selectFile: (file) => {
      set({
        filePreview: { type: "ready", data: null },
        selectedFile: file,
      });
    },

    selectSession: (sessionId) => {
      set({
        attachments: [],
        latestPlan: null,
        currentTask: null,
        selectedFile: null,
        selectedSessionId: sessionId,
        ...initialDetailState,
      });
    },

    refreshSessions: async () => {
      set({ actionError: null });
      try {
        const items = await fetchSessions();
        set((state) => {
          const selectedSessionId =
            state.selectedSessionId &&
            items.some((item) => item.id === state.selectedSessionId)
              ? state.selectedSessionId
              : items[0]?.id ?? null;

          return {
            sessions: { type: "ready", data: items },
            selectedSessionId,
          };
        });
      } catch (error) {
        set({
          actionError: getErrorMessage(error),
          sessions: { type: "error", message: getErrorMessage(error) },
        });
      }
    },

    loadSessionDetail: async (sessionId) => {
      set({
        context: { type: "loading" },
        events: { type: "loading" },
        files: { type: "loading" },
        filePreview: { type: "ready", data: null },
        messages: { type: "loading" },
        selectedFile: null,
      });
      try {
        const [messages, events, files, context] = await Promise.all([
          fetchMessages(sessionId),
          fetchEvents(sessionId),
          fetchSessionFiles(sessionId),
          fetchSessionContext(sessionId),
        ]);
        set({
          context: { type: "ready", data: context },
          events: { type: "ready", data: events },
          files: { type: "ready", data: files },
          latestPlan: applyExecutionEvents(getLatestPlan(events), events),
          messages: { type: "ready", data: messages },
        });
      } catch (error) {
        const message = getErrorMessage(error);
        set({
          actionError: message,
          context: { type: "error", message },
          events: { type: "error", message },
          files: { type: "error", message },
          messages: { type: "error", message },
        });
      }
    },

    loadSessionContext: async (sessionId) => {
      set({ actionError: null, context: { type: "loading" } });
      try {
        const context = await fetchSessionContext(sessionId);
        set({ context: { type: "ready", data: context } });
      } catch (error) {
        const message = getErrorMessage(error);
        set({
          actionError: message,
          context: { type: "error", message },
        });
      }
    },

    loadFilePreview: async (fileId) => {
      set({ actionError: null, filePreview: { type: "loading" } });
      try {
        const preview = await fetchFilePreview(fileId);
        set({ filePreview: { type: "ready", data: preview } });
      } catch (error) {
        const message = getErrorMessage(error);
        set({
          actionError: message,
          filePreview: { type: "error", message },
        });
      }
    },

    createSession: async () => {
      const cleanTitle = get().title.trim();
      if (!cleanTitle) {
        set({ actionError: "请输入会话标题" });
        return;
      }

      set({ actionError: null, submitting: true });
      try {
        const created = await createSession(cleanTitle);
        set({
          title: "",
          selectedSessionId: created.id,
        });
        await get().refreshSessions();
      } catch (error) {
        set({ actionError: getErrorMessage(error) });
      } finally {
        set({ submitting: false });
      }
    },

    deleteSession: async (sessionId) => {
      set({ actionError: null });
      try {
        await deleteSession(sessionId);
        await get().refreshSessions();
      } catch (error) {
        set({ actionError: getErrorMessage(error) });
      }
    },

    stopSession: async () => {
      const sessionId = get().selectedSessionId;
      if (!sessionId) {
        set({ actionError: "请先选择一个会话" });
        return;
      }

      set({ actionError: null, stoppingSession: true });
      try {
        const session = await stopSession(sessionId);
        set((state) => ({
          sessions:
            state.sessions.type === "ready"
              ? {
                  type: "ready",
                  data: updateSession(state.sessions.data, session),
                }
              : state.sessions,
        }));
      } catch (error) {
        set({ actionError: getErrorMessage(error) });
      } finally {
        set({ stoppingSession: false });
      }
    },

    clearUnread: async () => {
      const sessionId = get().selectedSessionId;
      if (!sessionId) {
        set({ actionError: "请先选择一个会话" });
        return;
      }

      set({ actionError: null, clearingUnread: true });
      try {
        const session = await clearUnread(sessionId);
        set((state) => ({
          sessions:
            state.sessions.type === "ready"
              ? {
                  type: "ready",
                  data: updateSession(state.sessions.data, session),
                }
              : state.sessions,
        }));
      } catch (error) {
        set({ actionError: getErrorMessage(error) });
      } finally {
        set({ clearingUnread: false });
      }
    },

    sendMessage: async () => {
      const sessionId = get().selectedSessionId;
      const content = get().draft.trim();
      if (!sessionId) {
        set({ actionError: "请先选择一个会话" });
        return;
      }
      if (!content) {
        set({ actionError: "请输入消息内容" });
        return;
      }

      set({
        actionError: null,
        currentTask: null,
        executingPlan: false,
        latestPlan: null,
        planning: true,
        sendingMessage: true,
      });
      try {
        set({ draft: "" });
        // ===================== 第1步：通过统一 SSE 发送任务并接收执行过程 =====================
        // 后端会依次推送 message_created、plan_created、step/tool/task 事件。
        await streamMessage(sessionId, content, async (event) => {
          await sleep(getPresentationDelay(event.event));
          const session = toSessionItem(event);
          if (session) {
            set((state) => ({
              sessions:
                state.sessions.type === "ready"
                  ? {
                      type: "ready",
                      data: updateSession(state.sessions.data, session),
                    }
                  : state.sessions,
            }));
          }

          const sessionEvent = toSessionEventItem(event);
          if (!sessionEvent) {
            return;
          }
          set((state) => {
            const currentEvents =
              state.events.type === "ready" ? state.events.data : [];
            const events = [...currentEvents, sessionEvent];
            const currentMessages =
              state.messages.type === "ready" ? state.messages.data : [];
            const streamMessageItem = toChatMessageItem(sessionEvent);
            const messages =
              streamMessageItem &&
              !currentMessages.some((message) => message.id === streamMessageItem.id)
                ? [...currentMessages, streamMessageItem]
                : currentMessages;
            const latestPlan = applyExecutionEvents(getLatestPlan(events), events);
            return {
              events: {
                type: "ready",
                data: events,
              },
              executingPlan:
                sessionEvent.type === "task_done" ||
                sessionEvent.type === "task_error"
                  ? false
                  : state.executingPlan || sessionEvent.type === "plan_created",
              latestPlan,
              messages: {
                type: "ready",
                data: messages,
              },
              planning:
                sessionEvent.type === "plan_created" ? false : state.planning,
            };
          });
        });
        await Promise.all([
          get().loadSessionDetail(sessionId),
          get().refreshSessions(),
          get().loadSessionContext(sessionId),
        ]);
      } catch (error) {
        set({ actionError: getErrorMessage(error) });
      } finally {
        set({
          executingPlan: false,
          planning: false,
          sendingMessage: false,
        });
      }
    },

    uploadAttachment: async (file) => {
      if (!get().selectedSessionId) {
        set({ actionError: "请先选择一个会话" });
        return;
      }

      set({ actionError: null, uploadingFile: true });
      try {
        const uploaded = await uploadSessionFile(get().selectedSessionId!, file);
        set((state) => ({
          attachments: [uploaded, ...state.attachments],
          files:
            state.files.type === "ready"
              ? {
                  type: "ready",
                  data: [uploaded, ...state.files.data],
                }
              : state.files,
        }));
        await get().loadSessionContext(get().selectedSessionId!);
      } catch (error) {
        set({ actionError: getErrorMessage(error) });
      } finally {
        set({ uploadingFile: false });
      }
    },
  }),
);
