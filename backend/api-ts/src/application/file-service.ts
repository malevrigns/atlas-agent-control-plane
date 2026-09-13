import { mkdir, readFile, writeFile } from "node:fs/promises";
import { extname, join } from "node:path";

import { and, desc, eq } from "drizzle-orm";

import type { Settings } from "../core/config.js";
import { AppError } from "../core/errors.js";
import { type SessionFile, type UploadedFile, newId, nowIso } from "../domain/sessions.js";
import type { Database } from "../infrastructure/db/client.js";
import { files, sessionFiles } from "../infrastructure/db/schema.js";
import { SessionService } from "./session-service.js";

export class FileService {
  constructor(
    private readonly db: Database,
    private readonly sessions: SessionService,
    private readonly settings: Settings,
  ) {}

  async saveUpload(
    file: { name: string; type: string; data: Uint8Array },
    sessionId?: string,
  ): Promise<{ file: UploadedFile; sessionFile: SessionFile | null }> {
    if (file.data.byteLength > this.settings.maxUploadSize) {
      throw new AppError("upload exceeds MAX_UPLOAD_SIZE", { code: 413, statusCode: 413 });
    }
    if (sessionId) {
      await this.sessions.getSession(sessionId);
    }
    const id = newId();
    const stamp = nowIso();
    const storedName = `${id}${extname(file.name) || ""}`;
    await mkdir(this.settings.uploadDir, { recursive: true });
    const storagePath = join(this.settings.uploadDir, storedName);
    await writeFile(storagePath, file.data);
    await this.db.insert(files).values({
      id,
      originalName: file.name || storedName,
      storedName,
      contentType: file.type || "application/octet-stream",
      size: file.data.byteLength,
      storagePath,
      createdAt: stamp,
    });
    const uploaded = this.toUploaded({
      id,
      originalName: file.name || storedName,
      contentType: file.type || "application/octet-stream",
      size: file.data.byteLength,
      createdAt: stamp,
    });
    if (!sessionId) {
      return { file: uploaded, sessionFile: null };
    }
    const linkId = newId();
    await this.db.insert(sessionFiles).values({
      id: linkId,
      sessionId,
      fileId: id,
      createdAt: stamp,
    });
    return {
      file: uploaded,
      sessionFile: {
        id: linkId,
        session_id: sessionId,
        file: uploaded,
        created_at: stamp,
      },
    };
  }

  async listSessionFiles(sessionId: string): Promise<SessionFile[]> {
    await this.sessions.getSession(sessionId);
    const rows = await this.db
      .select({
        id: sessionFiles.id,
        sessionId: sessionFiles.sessionId,
        createdAt: sessionFiles.createdAt,
        fileId: files.id,
        originalName: files.originalName,
        contentType: files.contentType,
        size: files.size,
        fileCreatedAt: files.createdAt,
      })
      .from(sessionFiles)
      .innerJoin(files, eq(sessionFiles.fileId, files.id))
      .where(eq(sessionFiles.sessionId, sessionId))
      .orderBy(desc(sessionFiles.createdAt));
    return rows.map((row) => ({
      id: row.id,
      session_id: row.sessionId,
      created_at: row.createdAt,
      file: this.toUploaded({
        id: row.fileId,
        originalName: row.originalName,
        contentType: row.contentType,
        size: row.size,
        createdAt: row.fileCreatedAt,
      }),
    }));
  }

  async deleteSessionFile(sessionId: string, sessionFileId: string): Promise<void> {
    await this.sessions.getSession(sessionId);
    const deleted = await this.db
      .delete(sessionFiles)
      .where(and(eq(sessionFiles.id, sessionFileId), eq(sessionFiles.sessionId, sessionId)))
      .returning({ id: sessionFiles.id });
    if (!deleted.length) {
      throw new AppError("session file not found", { code: 404, statusCode: 404 });
    }
  }

  async preview(fileId: string): Promise<{
    file: UploadedFile;
    content: string;
    file_type: string;
    language: string | null;
    line_count: number;
    parse_status: string;
    parse_message: string;
    references: Array<{ label: string; excerpt: string }>;
  }> {
    const row = await this.db.query.files.findFirst({ where: eq(files.id, fileId) });
    if (!row) {
      throw new AppError("file not found", { code: 404, statusCode: 404 });
    }
    const raw = await readFile(row.storagePath);
    const text = raw.subarray(0, this.settings.maxFilePreviewSize).toString("utf8");
    return {
      file: this.toUploaded(row),
      content: text,
      file_type: extname(row.originalName).replace(".", "") || "text",
      language: null,
      line_count: text.split(/\r?\n/).length,
      parse_status: "ok",
      parse_message: "",
      references: [],
    };
  }

  async readBytes(fileId: string): Promise<{ bytes: Buffer; name: string; type: string }> {
    const row = await this.db.query.files.findFirst({ where: eq(files.id, fileId) });
    if (!row) {
      throw new AppError("file not found", { code: 404, statusCode: 404 });
    }
    return {
      bytes: await readFile(row.storagePath),
      name: row.originalName,
      type: row.contentType,
    };
  }

  private toUploaded(row: {
    id: string;
    originalName: string;
    contentType: string;
    size: number;
    createdAt: string;
  }): UploadedFile {
    return {
      id: row.id,
      original_name: row.originalName,
      content_type: row.contentType,
      size: row.size,
      download_url: `/api/files/${row.id}/download`,
      created_at: row.createdAt,
    };
  }
}
