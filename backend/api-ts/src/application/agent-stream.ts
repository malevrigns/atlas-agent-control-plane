import type { Settings } from "../core/config.js";
import type { Session } from "../domain/sessions.js";
import { SessionService } from "./session-service.js";

export type SseFrame = { event: string; data: Record<string, unknown> };

export async function* streamUserMessage(
  sessions: SessionService,
  settings: Settings,
  sessionId: string,
  content: string,
  options: { resume?: boolean; skillIds?: string[] } = {},
): AsyncGenerator<SseFrame> {
  const running = await sessions.updateStatus(sessionId, "running");
  yield { event: "session_status", data: running };

  let userMessageId: string | null = null;
  if (!options.resume) {
    const created = await sessions.createUserMessage(sessionId, content);
    userMessageId = created.message.id;
    yield { event: "message_created", data: created.event };
  }

  yield {
    event: "answer_started",
    data: { session_id: sessionId, mode: "chat" },
  };

  const answer = await generateAnswer(settings, content);
  const chunkSize = 24;
  for (let index = 0; index < answer.length; index += chunkSize) {
    yield {
      event: "answer_delta",
      data: { session_id: sessionId, delta: answer.slice(index, index + chunkSize) },
    };
  }

  const assistant = await sessions.createAssistantMessage(sessionId, answer);
  yield { event: "message_created", data: assistant.event };
  const done = await sessions.addEvent(sessionId, "task_done", {
    mode: "chat",
    final_answer: answer,
    message_id: assistant.message.id,
    user_message: content,
    skill_ids: options.skillIds ?? [],
    resume: Boolean(options.resume),
    source_message_id: userMessageId,
  });
  yield { event: "task_done", data: done };

  const idle = await sessions.updateStatus(sessionId, "idle");
  yield { event: "session_status", data: idle };
  yield { event: "stream_done", data: { session_id: sessionId } };
}

async function generateAnswer(settings: Settings, prompt: string): Promise<string> {
  if (!settings.llmApiKey) {
    return [
      "AtlasAgent 控制平面（TypeScript）已收到任务。",
      "",
      `> ${prompt.slice(0, 240)}`,
      "",
      "当前未配置 LLM_API_KEY，因此走离线直答。配置任意 OpenAI 兼容密钥后，同一条 SSE 路径会改为模型流式作答。",
    ].join("\n");
  }
  const response = await fetch(`${settings.llmBaseUrl.replace(/\/$/, "")}/chat/completions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${settings.llmApiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: settings.llmModel,
      messages: [
        {
          role: "system",
          content: "You are AtlasAgent. Answer concisely with evidence when you have it.",
        },
        { role: "user", content: prompt },
      ],
      temperature: 0.2,
    }),
  });
  if (!response.ok) {
    return `模型调用失败（HTTP ${response.status}）。请检查 LLM_API_KEY 与 LLM_BASE_URL。`;
  }
  const payload = (await response.json()) as {
    choices?: Array<{ message?: { content?: string } }>;
  };
  const content = payload.choices?.[0]?.message?.content?.trim();
  return content || "模型返回了空内容。";
}

export function encodeSse(event: string, data: Record<string, unknown>): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

export function sessionPayload(session: Session): Record<string, unknown> {
  return { ...session };
}
