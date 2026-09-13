import { mkdir, readdir, readFile, rm, stat, writeFile } from "node:fs/promises";
import { dirname, join, relative, resolve, sep } from "node:path";

import { SandboxError, type SandboxSettings } from "./core.js";

export class FileService {
  constructor(private readonly settings: SandboxSettings) {}

  root(workspace: string, fullAccess: boolean): string {
    if (fullAccess) {
      return this.settings.workspaceDir;
    }
    const clean = workspace.trim().replace(/^\/+|\/+$/g, "");
    if (!clean) {
      return this.settings.workspaceDir;
    }
    const target = resolve(this.settings.workspaceDir, clean);
    if (!this.isInside(this.settings.workspaceDir, target)) {
      throw new SandboxError("workspace escapes mount root");
    }
    return target;
  }

  resolvePath(path: string, workspace: string, fullAccess: boolean): string {
    const clean = path.trim() || ".";
    if (isAbsolutePath(clean)) {
      throw new SandboxError("absolute path is not allowed");
    }
    if (clean.split(/[\\/]/).includes("..")) {
      throw new SandboxError("path escapes workspace");
    }
    const root = this.root(workspace, fullAccess);
    const target = resolve(root, clean);
    if (!this.isInside(root, target)) {
      throw new SandboxError("path escapes workspace");
    }
    return target;
  }

  toRelative(target: string, workspace: string, fullAccess: boolean): string {
    const root = this.root(workspace, fullAccess);
    const rel = relative(root, target).split(sep).join("/");
    return rel || ".";
  }

  async list(path: string, workspace: string, fullAccess: boolean) {
    const target = this.resolvePath(path, workspace, fullAccess);
    let info;
    try {
      info = await stat(target);
    } catch {
      throw new SandboxError("path not found", 404);
    }
    if (!info.isDirectory()) {
      throw new SandboxError("path is not a directory");
    }
    const entries = await readdir(target, { withFileTypes: true });
    const items = await Promise.all(
      entries
        .sort((a, b) => a.name.localeCompare(b.name))
        .map(async (entry) => {
          const child = join(target, entry.name);
          const meta = await stat(child);
          return {
            name: entry.name,
            path: this.toRelative(child, workspace, fullAccess),
            is_dir: entry.isDirectory(),
            size: entry.isDirectory() ? 0 : meta.size,
          };
        }),
    );
    return { current_path: this.toRelative(target, workspace, fullAccess), items };
  }

  async read(path: string, workspace: string, fullAccess: boolean) {
    const target = await this.existingFile(path, workspace, fullAccess);
    const raw = await readFile(target);
    const truncated = raw.byteLength > this.settings.maxFileReadBytes;
    const preview = raw.subarray(0, this.settings.maxFileReadBytes);
    return {
      path: this.toRelative(target, workspace, fullAccess),
      content: preview.toString("utf8"),
      size: raw.byteLength,
      truncated,
    };
  }

  async write(
    path: string,
    content: string,
    createParent: boolean,
    workspace: string,
    fullAccess: boolean,
  ) {
    const encoded = Buffer.from(content, "utf8");
    if (encoded.byteLength > this.settings.maxFileWriteBytes) {
      throw new SandboxError("file content is too large", 413);
    }
    const target = this.resolvePath(path, workspace, fullAccess);
    try {
      const info = await stat(target);
      if (info.isDirectory()) {
        throw new SandboxError("path is a directory");
      }
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT" && error instanceof SandboxError) {
        throw error;
      }
    }
    if (createParent) {
      await mkdir(dirname(target), { recursive: true });
    } else {
      try {
        await stat(dirname(target));
      } catch {
        throw new SandboxError("parent directory not found", 404);
      }
    }
    await writeFile(target, encoded);
    return { path: this.toRelative(target, workspace, fullAccess), size: encoded.byteLength };
  }

  async replace(path: string, oldText: string, newText: string, workspace: string, fullAccess: boolean) {
    const current = await this.read(path, workspace, fullAccess);
    const replacements = current.content.split(oldText).length - 1;
    const next = current.content.replaceAll(oldText, newText);
    await this.write(path, next, false, workspace, fullAccess);
    return { path: current.path, replacements, content: next };
  }

  async delete(path: string, workspace: string, fullAccess: boolean) {
    const root = this.root(workspace, fullAccess);
    const target = this.resolvePath(path, workspace, fullAccess);
    if (target === root) {
      throw new SandboxError("workspace root cannot be deleted");
    }
    try {
      await rm(target, { recursive: true, force: false });
    } catch {
      throw new SandboxError("path not found", 404);
    }
    return { path, deleted: true };
  }

  async existingFile(path: string, workspace: string, fullAccess: boolean): Promise<string> {
    const target = this.resolvePath(path, workspace, fullAccess);
    let info;
    try {
      info = await stat(target);
    } catch {
      throw new SandboxError("path not found", 404);
    }
    if (!info.isFile()) {
      throw new SandboxError("path is not a file");
    }
    return target;
  }

  private isInside(root: string, target: string): boolean {
    const rel = relative(root, target);
    return rel === "" || (!rel.startsWith("..") && !isAbsolutePath(rel));
  }
}

function isAbsolutePath(path: string): boolean {
  return path.startsWith("/") || path.startsWith("\\") || /^[A-Za-z]:[\\/]/.test(path);
}
