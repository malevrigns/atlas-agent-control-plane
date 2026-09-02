import type { SessionEventItem } from "../types";

/**
 * 把会话事件流翻译成"一次长程运行"的可读轨迹。
 *
 * 后端有 18 种事件类型，完整记录了 agent 干活的每一步：计划、步骤起止、
 * 工具调用、反思、阻塞，以及 summarize 之前的三级门禁。对话时间线关心
 * 的是"说了什么"，这里关心的是"做了什么、卡在哪、凭什么算完成"——
 * 长时间跑的任务只有这个视角看得懂。
 *
 * 纯函数，不碰 React，便于单测。
 */

/** 轨迹分段：一次运行按"回合"切开，每回合是一个步骤或一次门禁链。 */
export type TracePhase =
  | "plan"
  | "step"
  | "tool"
  | "reflect"
  | "gate"
  | "todo"
  | "done"
  | "error";

export type TraceEntry = {
  id: string;
  phase: TracePhase;
  /** 一行摘要，列表里直接可读。 */
  title: string;
  /** 补充说明；没有则为空串。 */
  detail: string;
  /** 门禁类事件的结论：通过 / 未通过 / 跳过；其余为 null。 */
  verdict: "passed" | "failed" | "skipped" | null;
  createdAt: string;
  raw: SessionEventItem;
};

export type RunTrace = {
  entries: TraceEntry[];
  /** 三级门禁的最终结论，按 stage 归并。 */
  gates: Array<{ stage: string; verdict: "passed" | "failed" | "skipped"; detail: string }>;
  stepCount: number;
  toolCount: number;
  failureCount: number;
  /** 首末事件时间差，毫秒；不足两条事件时为 null。 */
  elapsedMs: number | null;
  /** 最近一次阻塞或失败的原因，用于顶部告警。 */
  blockedReason: string | null;
};

function text(payload: Record<string, unknown>, ...keys: string[]): string {
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return "";
}

function verdictOf(payload: Record<string, unknown>): "passed" | "failed" | "skipped" {
  if (payload.skipped === true) {
    return "skipped";
  }
  const passed = payload.passed ?? payload.ok ?? payload.success;
  if (passed === true) {
    return "passed";
  }
  if (passed === false) {
    return "failed";
  }
  // 没有显式布尔时按退出码判断：0 通过，其余不通过。
  const exitCode = payload.exit_code;
  if (typeof exitCode === "number") {
    return exitCode === 0 ? "passed" : "failed";
  }
  return "skipped";
}

const GATE_LABELS: Record<string, string> = {
  acceptance_gate_finished: "验收门禁",
  scope_audit_finished: "范围审计",
  coverage_review_finished: "覆盖度评审",
};

export function buildRunTrace(events: SessionEventItem[]): RunTrace {
  const ordered = [...events].sort(
    (left, right) => Date.parse(left.created_at) - Date.parse(right.created_at),
  );

  const entries: TraceEntry[] = [];
  const gates: RunTrace["gates"] = [];
  let stepCount = 0;
  let toolCount = 0;
  let failureCount = 0;
  let blockedReason: string | null = null;

  for (const event of ordered) {
    const payload = event.payload ?? {};
    const base = { id: event.id, createdAt: event.created_at, raw: event };

    switch (event.type) {
      case "plan_created": {
        const steps = Array.isArray(payload.steps) ? payload.steps.length : 0;
        entries.push({
          ...base,
          phase: "plan",
          title: steps ? `制定计划 · ${steps} 个步骤` : "制定计划",
          detail: text(payload, "goal", "task", "title"),
          verdict: null,
        });
        break;
      }
      case "step_started": {
        stepCount += 1;
        entries.push({
          ...base,
          phase: "step",
          title: text(payload, "title", "step_title", "name") || "开始步骤",
          detail: text(payload, "description", "expected_output"),
          verdict: null,
        });
        break;
      }
      case "tool_called": {
        toolCount += 1;
        const tool = text(payload, "tool_name", "tool", "name") || "工具";
        entries.push({
          ...base,
          phase: "tool",
          title: `调用 ${tool}`,
          detail: text(payload, "output_preview", "summary", "arguments_preview"),
          verdict: null,
        });
        break;
      }
      case "step_reflected": {
        entries.push({
          ...base,
          phase: "reflect",
          title: "反思",
          detail: text(payload, "reflection", "reason", "summary"),
          verdict: null,
        });
        break;
      }
      case "step_completed": {
        entries.push({
          ...base,
          phase: "step",
          title: text(payload, "title", "step_title") || "步骤完成",
          detail: text(payload, "result", "summary", "output_preview"),
          verdict: "passed",
        });
        break;
      }
      case "step_failed":
      case "step_blocked": {
        failureCount += 1;
        const reason =
          text(payload, "reason", "error", "message") ||
          (event.type === "step_blocked" ? "被阻塞" : "步骤失败");
        blockedReason = reason;
        entries.push({
          ...base,
          phase: "error",
          title: event.type === "step_blocked" ? "阻塞" : "步骤失败",
          detail: reason,
          verdict: "failed",
        });
        break;
      }
      case "todo_updated": {
        const status = text(payload, "status") || "更新";
        entries.push({
          ...base,
          phase: "todo",
          title: `清单流转 · ${status}`,
          detail: text(payload, "todo_id", "title"),
          verdict: null,
        });
        break;
      }
      case "acceptance_gate_started": {
        entries.push({
          ...base,
          phase: "gate",
          title: "验收门禁开始",
          detail: text(payload, "command"),
          verdict: null,
        });
        break;
      }
      case "acceptance_gate_finished":
      case "scope_audit_finished":
      case "coverage_review_finished": {
        const verdict = verdictOf(payload);
        const stage = GATE_LABELS[event.type] ?? "门禁";
        const detail =
          text(payload, "reason", "output_digest", "summary", "detail") ||
          (typeof payload.exit_code === "number" ? `退出码 ${payload.exit_code}` : "");
        if (verdict === "failed") {
          failureCount += 1;
          blockedReason = `${stage}未通过：${detail || "无说明"}`;
        }
        gates.push({ stage, verdict, detail });
        entries.push({ ...base, phase: "gate", title: stage, detail, verdict });
        break;
      }
      case "acceptance_chain_finished": {
        entries.push({
          ...base,
          phase: "gate",
          title: "门禁链汇总",
          detail: text(payload, "summary", "detail"),
          verdict: verdictOf(payload),
        });
        break;
      }
      case "task_done": {
        entries.push({
          ...base,
          phase: "done",
          title: "任务完成",
          detail: text(payload, "summary", "result"),
          verdict: "passed",
        });
        break;
      }
      case "task_error": {
        failureCount += 1;
        const reason = text(payload, "error", "message", "reason") || "任务出错";
        blockedReason = reason;
        entries.push({
          ...base,
          phase: "error",
          title: "任务出错",
          detail: reason,
          verdict: "failed",
        });
        break;
      }
      default:
        // message_created 等对话类事件不属于执行轨迹，跳过。
        break;
    }
  }

  const first = ordered[0];
  const last = ordered[ordered.length - 1];
  const elapsedMs =
    first && last && first !== last
      ? Math.max(0, Date.parse(last.created_at) - Date.parse(first.created_at))
      : null;

  return {
    entries,
    gates,
    stepCount,
    toolCount,
    failureCount,
    elapsedMs,
    blockedReason,
  };
}

/** 把毫秒渲染成人读的时长：长程任务动辄几小时，秒数没有意义。 */
export function formatDuration(ms: number | null): string {
  if (ms === null) {
    return "—";
  }
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) {
    return `${seconds} 秒`;
  }
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return `${minutes} 分 ${seconds % 60} 秒`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours} 小时 ${minutes % 60} 分`;
  }
  return `${Math.floor(hours / 24)} 天 ${hours % 24} 小时`;
}
