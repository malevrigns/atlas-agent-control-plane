import { index, integer, sqliteTable, text, uniqueIndex } from "drizzle-orm/sqlite-core";

export const sessions = sqliteTable(
  "sessions",
  {
    id: text("id").primaryKey(),
    title: text("title").notNull(),
    status: text("status").notNull().default("idle"),
    unreadCount: integer("unread_count").notNull().default(0),
    workspaceDir: text("workspace_dir").notNull().default(""),
    fullAccess: integer("full_access", { mode: "boolean" }).notNull().default(false),
    createdAt: text("created_at").notNull(),
    updatedAt: text("updated_at").notNull(),
    deletedAt: text("deleted_at"),
  },
  (table) => ({
    deletedAtIdx: index("ix_sessions_deleted_at").on(table.deletedAt),
    updatedAtIdx: index("ix_sessions_updated_at").on(table.updatedAt),
  }),
);

export const sessionMessages = sqliteTable(
  "session_messages",
  {
    id: text("id").primaryKey(),
    sessionId: text("session_id")
      .notNull()
      .references(() => sessions.id, { onDelete: "cascade" }),
    role: text("role").notNull(),
    content: text("content").notNull(),
    createdAt: text("created_at").notNull(),
  },
  (table) => ({
    sessionCreatedIdx: index("ix_session_messages_session_created").on(
      table.sessionId,
      table.createdAt,
    ),
  }),
);

export const sessionEvents = sqliteTable(
  "session_events",
  {
    id: text("id").primaryKey(),
    sessionId: text("session_id")
      .notNull()
      .references(() => sessions.id, { onDelete: "cascade" }),
    type: text("type").notNull(),
    payload: text("payload", { mode: "json" }).notNull().$type<Record<string, unknown>>(),
    createdAt: text("created_at").notNull(),
  },
  (table) => ({
    sessionCreatedIdx: index("ix_session_events_session_created").on(
      table.sessionId,
      table.createdAt,
    ),
  }),
);

export const files = sqliteTable("files", {
  id: text("id").primaryKey(),
  originalName: text("original_name").notNull(),
  storedName: text("stored_name").notNull(),
  contentType: text("content_type").notNull(),
  size: integer("size").notNull(),
  storagePath: text("storage_path").notNull(),
  createdAt: text("created_at").notNull(),
});

export const sessionFiles = sqliteTable(
  "session_files",
  {
    id: text("id").primaryKey(),
    sessionId: text("session_id")
      .notNull()
      .references(() => sessions.id, { onDelete: "cascade" }),
    fileId: text("file_id")
      .notNull()
      .references(() => files.id, { onDelete: "cascade" }),
    createdAt: text("created_at").notNull(),
  },
  (table) => ({
    uniquePair: uniqueIndex("uq_session_files_session_file").on(table.sessionId, table.fileId),
    sessionCreatedIdx: index("ix_session_files_session_created").on(
      table.sessionId,
      table.createdAt,
    ),
  }),
);

export const agentTasks = sqliteTable("agent_tasks", {
  id: text("id").primaryKey(),
  sessionId: text("session_id"),
  projectId: text("project_id").notNull().default("default"),
  title: text("title").notNull(),
  goal: text("goal").notNull().default(""),
  status: text("status").notNull().default("pending"),
  version: integer("version").notNull().default(1),
  stateHash: text("state_hash").notNull().default(""),
  progress: text("progress", { mode: "json" })
    .notNull()
    .$type<{ done: string[]; doing: string[]; blocked: string[] }>(),
  createdAt: text("created_at").notNull(),
  updatedAt: text("updated_at").notNull(),
});

export const schema = {
  sessions,
  sessionMessages,
  sessionEvents,
  files,
  sessionFiles,
  agentTasks,
};

export const SQLITE_DDL = `
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'idle',
  unread_count INTEGER NOT NULL DEFAULT 0,
  workspace_dir TEXT NOT NULL DEFAULT '',
  full_access INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  deleted_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_sessions_deleted_at ON sessions (deleted_at);
CREATE INDEX IF NOT EXISTS ix_sessions_updated_at ON sessions (updated_at);

CREATE TABLE IF NOT EXISTS session_messages (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_session_messages_session_created
  ON session_messages (session_id, created_at);

CREATE TABLE IF NOT EXISTS session_events (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  type TEXT NOT NULL,
  payload TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_session_events_session_created
  ON session_events (session_id, created_at);

CREATE TABLE IF NOT EXISTS files (
  id TEXT PRIMARY KEY,
  original_name TEXT NOT NULL,
  stored_name TEXT NOT NULL,
  content_type TEXT NOT NULL,
  size INTEGER NOT NULL,
  storage_path TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_files (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  file_id TEXT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_session_files_session_file
  ON session_files (session_id, file_id);
CREATE INDEX IF NOT EXISTS ix_session_files_session_created
  ON session_files (session_id, created_at);

CREATE TABLE IF NOT EXISTS agent_tasks (
  id TEXT PRIMARY KEY,
  session_id TEXT,
  project_id TEXT NOT NULL DEFAULT 'default',
  title TEXT NOT NULL,
  goal TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'pending',
  version INTEGER NOT NULL DEFAULT 1,
  state_hash TEXT NOT NULL DEFAULT '',
  progress TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
`
