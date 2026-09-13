import { describe, expect, it } from "vitest";

import { json, makeTestApp } from "./helpers.js";

describe("message stream", () => {
  it("emits the chat SSE sequence and persists both sides", async () => {
    const { app } = await makeTestApp();
    const created = await json<{ data: { id: string } }>(
      await app.request("/api/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: "stream" }),
      }),
    );
    const id = created.data.id;
    const response = await app.request(`/api/sessions/${id}/messages/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ content: "ping" }),
    });
    expect(response.status).toBe(200);
    expect(response.headers.get("content-type") ?? "").toContain("text/event-stream");
    const body = await response.text();
    expect(body).toContain("event: session_status");
    expect(body).toContain("event: message_created");
    expect(body).toContain("event: answer_started");
    expect(body).toContain("event: answer_delta");
    expect(body).toContain("event: task_done");
    expect(body).toContain("event: stream_done");

    const messages = await json<{ data: { items: Array<{ role: string }> } }>(
      await app.request(`/api/sessions/${id}/messages`),
    );
    expect(messages.data.items.map((item) => item.role)).toEqual(["user", "assistant"]);
  });
});
