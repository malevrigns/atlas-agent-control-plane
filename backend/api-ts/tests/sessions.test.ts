import { describe, expect, it } from "vitest";

import { json, makeTestApp } from "./helpers.js";

describe("sessions", () => {
  it("creates, lists, and soft-deletes a session", async () => {
    const { app } = await makeTestApp();
    const created = await app.request("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "工作区 A", workspace_dir: "D:\\\\projects\\\\demo" }),
    });
    expect(created.status).toBe(200);
    const session = (await json<{ data: { id: string; title: string; workspace_dir: string } }>(
      created,
    )).data;
    expect(session.title).toBe("工作区 A");
    expect(session.workspace_dir).toBe("projects/demo");

    const listed = await json<{ data: { items: Array<{ id: string }> } }>(
      await app.request("/api/sessions"),
    );
    expect(listed.data.items.map((item) => item.id)).toContain(session.id);

    const deleted = await app.request(`/api/sessions/${session.id}`, { method: "DELETE" });
    expect(deleted.status).toBe(204);
    const after = await json<{ data: { items: Array<{ id: string }> } }>(
      await app.request("/api/sessions"),
    );
    expect(after.data.items.map((item) => item.id)).not.toContain(session.id);
  });

  it("rejects workspace paths that escape", async () => {
    const { app } = await makeTestApp();
    const response = await app.request("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "bad", workspace_dir: "../etc" }),
    });
    expect(response.status).toBe(400);
  });

  it("stores a user message and event", async () => {
    const { app } = await makeTestApp();
    const created = await json<{ data: { id: string } }>(
      await app.request("/api/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: "chat" }),
      }),
    );
    const id = created.data.id;
    const posted = await app.request(`/api/sessions/${id}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: "hello" }),
    });
    expect(posted.status).toBe(200);
    const messages = await json<{ data: { items: Array<{ role: string; content: string }> } }>(
      await app.request(`/api/sessions/${id}/messages`),
    );
    expect(messages.data.items).toEqual([
      expect.objectContaining({ role: "user", content: "hello" }),
    ]);
    const events = await json<{ data: { items: Array<{ type: string }> } }>(
      await app.request(`/api/sessions/${id}/events`),
    );
    expect(events.data.items[0]?.type).toBe("message_created");
  });

  it("returns 404 for unknown sessions", async () => {
    const { app } = await makeTestApp();
    const response = await app.request("/api/sessions/00000000-0000-0000-0000-000000000000");
    expect(response.status).toBe(404);
  });
});
