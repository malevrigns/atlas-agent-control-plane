import assert from "node:assert/strict";
import { test } from "node:test";

import type { SessionEventItem } from "../types.ts";
import { buildRunTrace, formatDuration } from "./run-trace.ts";

function event(
  type: string,
  payload: Record<string, unknown>,
  createdAt: string,
): SessionEventItem {
  return {
    id: `${type}-${createdAt}`,
    session_id: "session-1",
    type,
    payload,
    created_at: createdAt,
  };
}

test("buildRunTrace keeps the long-run evidence chain and skips chat noise", () => {
  const trace = buildRunTrace([
    event("message_created", { content: "开始吧" }, "2026-08-31T08:00:00Z"),
    event(
      "plan_created",
      { goal: "把队列抽成端口", steps: [{ id: "a" }, { id: "b" }, { id: "c" }] },
      "2026-08-31T08:00:01Z",
    ),
    event("step_started", { title: "抽出端口" }, "2026-08-31T08:01:00Z"),
    event("tool_called", { tool_name: "read_file", output_preview: "ok" }, "2026-08-31T08:02:00Z"),
    event("step_completed", { title: "抽出端口", result: "端口已落地" }, "2026-08-31T08:03:00Z"),
    event("step_blocked", { reason: "FakeRedis 重复投递" }, "2026-08-31T08:04:00Z"),
    event("acceptance_gate_finished", { passed: true, exit_code: 0 }, "2026-08-31T08:05:00Z"),
    event("scope_audit_finished", { passed: false, reason: "改了无关文件" }, "2026-08-31T08:06:00Z"),
    event("coverage_review_finished", { skipped: true }, "2026-08-31T08:07:00Z"),
  ]);

  assert.equal(trace.entries.some((entry) => entry.raw.type === "message_created"), false);
  assert.equal(trace.stepCount, 1);
  assert.equal(trace.toolCount, 1);
  assert.equal(trace.failureCount, 2);
  assert.equal(trace.elapsedMs, 7 * 60 * 1000);
  assert.match(trace.blockedReason ?? "", /范围审计未通过/);
  assert.deepEqual(
    trace.gates.map((gate) => [gate.stage, gate.verdict]),
    [
      ["验收门禁", "passed"],
      ["范围审计", "failed"],
      ["覆盖度评审", "skipped"],
    ],
  );
});

test("formatDuration uses hours for long-running tasks", () => {
  assert.equal(formatDuration(null), "—");
  assert.equal(formatDuration(45_000), "45 秒");
  assert.equal(formatDuration(3 * 60 * 60 * 1000 + 12 * 60 * 1000), "3 小时 12 分");
});
