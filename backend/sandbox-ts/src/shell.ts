import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

import { SandboxError, type SandboxSettings } from "./core.js";
import { FileService } from "./files.js";

type ShellSession = {
  id: string;
  command: string;
  cwd: string;
  process: ChildProcessWithoutNullStreams;
  status: "running" | "exited" | "terminated";
  returnCode: number | null;
  output: string;
  outputTruncated: boolean;
};

export class ShellService {
  private readonly sessions = new Map<string, ShellSession>();

  constructor(
    private readonly settings: SandboxSettings,
    private readonly files: FileService,
  ) {}

  execute(command: string, cwd: string, workspace: string, fullAccess: boolean) {
    const root = this.files.root(workspace, fullAccess);
    mkdirSync(root, { recursive: true });
    const workdir = this.files.resolvePath(cwd || ".", workspace, fullAccess);
    mkdirSync(workdir, { recursive: true });
    const isWin = process.platform === "win32";
    const child = spawn(isWin ? "cmd.exe" : "sh", isWin ? ["/c", command] : ["-c", command], {
      cwd: workdir,
      env: process.env,
      windowsHide: true,
    });
    const session: ShellSession = {
      id: crypto.randomUUID(),
      command,
      cwd: this.files.toRelative(workdir, workspace, fullAccess),
      process: child,
      status: "running",
      returnCode: null,
      output: "",
      outputTruncated: false,
    };
    this.sessions.set(session.id, session);
    const append = (chunk: Buffer) => {
      const next = session.output + chunk.toString("utf8");
      if (next.length > this.settings.shellOutputLimit) {
        session.output = next.slice(0, this.settings.shellOutputLimit);
        session.outputTruncated = true;
      } else {
        session.output = next;
      }
    };
    child.stdout.on("data", append);
    child.stderr.on("data", append);
    child.on("close", (code) => {
      session.status = session.status === "terminated" ? "terminated" : "exited";
      session.returnCode = code;
    });
    return this.toResponse(session);
  }

  get(id: string) {
    return this.toResponse(this.require(id));
  }

  list() {
    return { items: [...this.sessions.values()].map((session) => this.toResponse(session)) };
  }

  async wait(id: string, timeoutSeconds?: number) {
    const session = this.require(id);
    const timeout = (timeoutSeconds ?? this.settings.shellDefaultTimeoutSeconds) * 1000;
    if (session.status !== "running") {
      return this.toResponse(session);
    }
    await Promise.race([
      new Promise<void>((resolveWait) => session.process.once("close", () => resolveWait())),
      new Promise<void>((resolveWait) => setTimeout(resolveWait, timeout)),
    ]);
    return this.toResponse(session);
  }

  write(id: string, value: string) {
    const session = this.require(id);
    if (session.status !== "running" || !session.process.stdin.writable) {
      throw new SandboxError("shell session is not writable");
    }
    const encoded = Buffer.from(value, "utf8");
    session.process.stdin.write(encoded);
    return { id: session.id, written: encoded.byteLength };
  }

  terminate(id: string) {
    const session = this.require(id);
    if (session.status === "running") {
      session.status = "terminated";
      session.process.kill();
    }
    return { id: session.id, status: session.status };
  }

  private require(id: string): ShellSession {
    const session = this.sessions.get(id);
    if (!session) {
      throw new SandboxError("shell session not found", 404);
    }
    return session;
  }

  private toResponse(session: ShellSession) {
    return {
      id: session.id,
      command: session.command,
      cwd: session.cwd,
      status: session.status,
      return_code: session.returnCode,
      output: session.output,
      output_truncated: session.outputTruncated,
    };
  }
}

export function resolveWorkdir(cwd: string, root: string): string {
  return resolve(root, cwd || ".");
}
