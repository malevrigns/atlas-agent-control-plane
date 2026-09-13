import { mkdirSync } from "node:fs";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

import { createClient, type Client } from "@libsql/client";
import { drizzle, type LibSQLDatabase } from "drizzle-orm/libsql";

import { normalizeDatabaseUrl } from "../../core/config.js";
import { schema, SQLITE_DDL } from "./schema.js";

export type Database = LibSQLDatabase<typeof schema>;

export type DatabaseBundle = {
  db: Database;
  raw: Client;
  kind: "sqlite" | "postgres";
};

export async function openDatabase(databaseUrl: string): Promise<DatabaseBundle> {
  const normalized = normalizeDatabaseUrl(databaseUrl);
  if (normalized.kind === "postgres") {
    throw new Error(
      "Postgres driver is not wired in this slice. Use sqlite+aiosqlite / file: URLs, or wait for the postgres adapter.",
    );
  }
  const url = toLibsqlUrl(normalized.url);
  ensureSqliteDir(url);
  const raw = createClient({ url });
  const db = drizzle(raw, { schema });
  for (const statement of SQLITE_DDL.split(";").map((part) => part.trim()).filter(Boolean)) {
    await raw.execute(statement);
  }
  return { db, raw, kind: "sqlite" };
}

function toLibsqlUrl(url: string): string {
  if (url === ":memory:" || url === "file::memory:") {
    return ":memory:";
  }
  if (url.startsWith("file:")) {
    return url;
  }
  return `file:${url}`;
}

function ensureSqliteDir(url: string): void {
  if (!url.startsWith("file:") || url.includes(":memory:")) {
    return;
  }
  const path = url.slice("file:".length).replace(/^\/*/, "");
  if (!path) {
    return;
  }
  mkdirSync(dirname(path), { recursive: true });
}

export function sqliteFileFromAlchemy(url: string): string {
  return normalizeDatabaseUrl(url).url;
}

export function here(metaUrl: string, ...segments: string[]): string {
  return fileURLToPath(new URL(segments.join("/"), metaUrl));
}
