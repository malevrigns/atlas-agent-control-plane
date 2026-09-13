import { and, desc, eq, isNull } from "drizzle-orm";

import { AppError } from "../core/errors.js";
import {
  type ChatMessage,
  type Session,
  type SessionEvent,
  type SessionStatus,
  newId,
  normalizeWorkspaceDir,
  nowIso,
} from "../domain/sessions.js";
import type { Database } from "../infrastructure/db/client.js";
import { sessionEvents, sessionMessages, sessions } from "../infrastructure/db/schema.js";

export class SessionService {
  constructor(private readonly db: Database) {}

  async createSession(
    title: string,
    workspaceDir = "",
    fullAccess = false,
  ): Promise<Session> {
    const id = newId();
    const stamp = nowIso();
    const row = {
      id,
      title: title.trim() || "新工作区",
      status: "idle",
      unreadCount: 0,
      workspaceDir: safeWorkspace(workspaceDir),
      fullAccess,
      createdAt: stamp,
      updatedAt: stamp,
      deletedAt: null,
    };
    await this.db.insert(sessions).values(row);
    return this.mapSession(row);
  }

  async listSessions(): Promise<Session[]> {
    const rows = await this.db
      .select()
      .from(sessions)
      .where(isNull(sessions.deletedAt))
      .orderBy(desc(sessions.updatedAt));
    return rows.map((row) => this.mapSession(row));
  }

  async getSession(sessionId: string): Promise<Session> {
    const row = await this.db.query.sessions.findFirst({
      where: and(eq(sessions.id, sessionId), isNull(sessions.deletedAt)),
    });
    if (!row) {
      throw new AppError("session not found", { code: 404, statusCode: 404 });
    }
    return this.mapSession(row);
  }

  async listMessages(sessionId: string): Promise<ChatMessage[]> {
    await this.getSession(sessionId);
    const rows = await this.db
      .select()
      .from(sessionMessages)
      .where(eq(sessionMessages.sessionId, sessionId))
      .orderBy(sessionMessages.createdAt);
    return rows.map(this.mapMessage);
  }

  async listEvents(sessionId: string): Promise<SessionEvent[]> {
    await this.getSession(sessionId);
    const rows = await this.db
      .select()
      .from(sessionEvents)
      .where(eq(sessionEvents.sessionId, sessionId))
      .orderBy(sessionEvents.createdAt);
    return rows.map(this.mapEvent);
  }

  async createUserMessage(
    sessionId: string,
    content: string,
  ): Promise<{ message: ChatMessage; event: SessionEvent }> {
    return this.createMessage(sessionId, "user", content, { incrementUnread: true });
  }

  async createAssistantMessage(
    sessionId: string,
    content: string,
  ): Promise<{ message: ChatMessage; event: SessionEvent }> {
    return this.createMessage(sessionId, "assistant", content, { incrementUnread: false });
  }

  async addEvent(
    sessionId: string,
    type: string,
    payload: Record<string, unknown>,
  ): Promise<SessionEvent> {
    await this.getSession(sessionId);
    const row = {
      id: newId(),
      sessionId,
      type,
      payload,
      createdAt: nowIso(),
    };
    await this.db.insert(sessionEvents).values(row);
    return this.mapEvent(row);
  }

  async updateStatus(sessionId: string, status: SessionStatus): Promise<Session> {
    await this.getSession(sessionId);
    const stamp = nowIso();
    await this.db
      .update(sessions)
      .set({ status, updatedAt: stamp })
      .where(eq(sessions.id, sessionId));
    return this.getSession(sessionId);
  }

  async clearUnread(sessionId: string): Promise<Session> {
    await this.getSession(sessionId);
    await this.db
      .update(sessions)
      .set({ unreadCount: 0, updatedAt: nowIso() })
      .where(eq(sessions.id, sessionId));
    return this.getSession(sessionId);
  }

  async deleteSession(sessionId: string): Promise<void> {
    await this.getSession(sessionId);
    await this.db
      .update(sessions)
      .set({ deletedAt: nowIso(), updatedAt: nowIso() })
      .where(eq(sessions.id, sessionId));
  }

  async emptyContext(sessionId: string) {
    const session = await this.getSession(sessionId);
    const messages = await this.listMessages(sessionId);
    const events = await this.listEvents(sessionId);
    return {
      session_id: session.id,
      summary: session.title,
      messages: messages.slice(-8).map((message) => ({
        id: message.id,
        role: message.role,
        content: message.content.slice(0, 1200),
        created_at: message.created_at,
      })),
      event_summaries: events.slice(-20).map((event) => ({
        id: event.id,
        type: event.type,
        created_at: event.created_at,
      })),
      files: [],
      memory_context: {
        query: session.title,
        items: [],
        candidate_count: 0,
        omitted_count: 0,
        total_chars: 0,
        max_chars: 2400,
      },
      budget: {
        message_limit: 8,
        event_limit: 20,
        max_message_chars: 1200,
        included_messages: Math.min(messages.length, 8),
        omitted_messages: Math.max(0, messages.length - 8),
        included_events: Math.min(events.length, 20),
        omitted_events: Math.max(0, events.length - 20),
        total_message_chars: messages.slice(-8).reduce((sum, item) => sum + item.content.length, 0),
        memory_limit: 6,
        max_memory_chars: 2400,
        included_memories: 0,
        omitted_memories: 0,
        total_memory_chars: 0,
      },
    };
  }

  private async createMessage(
    sessionId: string,
    role: "user" | "assistant",
    content: string,
    options: { incrementUnread: boolean },
  ): Promise<{ message: ChatMessage; event: SessionEvent }> {
    await this.getSession(sessionId);
    const clean = content.trim();
    if (!clean) {
      throw new AppError(
        role === "user" ? "message content is required" : "assistant message content is required",
        { code: 400, statusCode: 400 },
      );
    }
    const stamp = nowIso();
    const messageRow = {
      id: newId(),
      sessionId,
      role,
      content: clean,
      createdAt: stamp,
    };
    const eventRow = {
      id: newId(),
      sessionId,
      type: "message_created",
      payload: {
        message_id: messageRow.id,
        role,
        content: clean,
      },
      createdAt: stamp,
    };
    await this.db.insert(sessionMessages).values(messageRow);
    await this.db.insert(sessionEvents).values(eventRow);
    const current = await this.getSession(sessionId);
    await this.db
      .update(sessions)
      .set({
        unreadCount: options.incrementUnread ? current.unread_count + 1 : current.unread_count,
        updatedAt: stamp,
      })
      .where(eq(sessions.id, sessionId));
    return { message: this.mapMessage(messageRow), event: this.mapEvent(eventRow) };
  }

  private mapSession(row: {
    id: string;
    title: string;
    status: string;
    unreadCount: number;
    workspaceDir: string;
    fullAccess: boolean;
    createdAt: string;
    updatedAt: string;
  }): Session {
    return {
      id: row.id,
      title: row.title,
      status: row.status as SessionStatus,
      unread_count: row.unreadCount,
      workspace_dir: row.workspaceDir,
      full_access: row.fullAccess,
      created_at: row.createdAt,
      updated_at: row.updatedAt,
    };
  }

  private mapMessage(row: {
    id: string;
    sessionId: string;
    role: string;
    content: string;
    createdAt: string;
  }): ChatMessage {
    return {
      id: row.id,
      session_id: row.sessionId,
      role: row.role as ChatMessage["role"],
      content: row.content,
      created_at: row.createdAt,
    };
  }

  private mapEvent(row: {
    id: string;
    sessionId: string;
    type: string;
    payload: Record<string, unknown>;
    createdAt: string;
  }): SessionEvent {
    return {
      id: row.id,
      session_id: row.sessionId,
      type: row.type,
      payload: row.payload,
      created_at: row.createdAt,
    };
  }
}

function safeWorkspace(raw: string): string {
  try {
    return normalizeWorkspaceDir(raw);
  } catch {
    throw new AppError("工作区路径不能包含 ..", { code: 400, statusCode: 400 });
  }
}
