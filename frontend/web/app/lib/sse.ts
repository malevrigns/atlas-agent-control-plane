import type { StreamEvent } from "../types";

function parseSseBlock(block: string): StreamEvent | null {
  const lines = block.split(/\r?\n/);
  let event = "message";
  const dataLines: string[] = [];

  for (const line of lines) {
    if (!line || line.startsWith(":")) {
      continue;
    }
    if (line.startsWith("event:")) {
      event = line.slice("event:".length).trim();
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trimStart());
    }
  }

  if (dataLines.length === 0) {
    return null;
  }

  try {
    return {
      event,
      data: JSON.parse(dataLines.join("\n")) as Record<string, unknown>,
    };
  } catch {
    return null;
  }
}

export async function readSseStream(
  response: Response,
  onEvent: (event: StreamEvent) => void | Promise<void>,
  signal?: AbortSignal,
) {
  if (!response.body) {
    throw new Error("empty stream response");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const abort = () => {
    void reader.cancel().catch(() => undefined);
  };
  if (signal?.aborted) {
    abort();
    throw new DOMException("Aborted", "AbortError");
  }
  signal?.addEventListener("abort", abort, { once: true });

  try {
    while (true) {
      if (signal?.aborted) {
        throw new DOMException("Aborted", "AbortError");
      }
      const { done, value } = await reader.read();
      if (done) {
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split(/\r?\n\r?\n/);
      buffer = blocks.pop() ?? "";

      for (const block of blocks) {
        const parsed = parseSseBlock(block.trim());
        if (parsed) {
          await onEvent(parsed);
        }
      }
    }

    buffer += decoder.decode();
    const parsed = parseSseBlock(buffer.trim());
    if (parsed) {
      await onEvent(parsed);
    }
  } finally {
    signal?.removeEventListener("abort", abort);
    try {
      reader.releaseLock();
    } catch {
      // already cancelled / released
    }
  }
}
