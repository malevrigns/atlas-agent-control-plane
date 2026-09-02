"use client";

import { Loader2 } from "lucide-react";

import { formatDate } from "../../lib/format";
import type { ToolInvocation } from "../../lib/control-plane-api";

const RISK_TONES: Record<string, string> = {
  low: "border-(--line) text-(--text-4)",
  medium: "border-amber-400/40 text-amber-300",
  high: "border-orange-400/50 text-orange-300",
  critical: "border-red-400/50 text-red-300",
};

const RISK_LABELS: Record<string, string> = {
  low: "低",
  medium: "中",
  high: "高",
  critical: "关键",
};

const DECISION_LABELS: Record<string, string> = {
  allow: "放行",
  allowed: "放行",
  auto_approved: "自动批准",
  approved: "已批准",
  denied: "拒绝",
  deny: "拒绝",
  blocked: "拦截",
  pending: "待审批",
};

function decisionTone(decision: string): string {
  if (/den|block/.test(decision)) {
    return "text-red-300";
  }
  if (/pending/.test(decision)) {
    return "text-amber-300";
  }
  return "text-(--text-3)";
}

type InvocationTableProps = {
  invocations: ToolInvocation[];
  loading: boolean;
};

/**
 * 工具调用留痕。
 *
 * 这张表是"工具运行时有门禁"这句话的证据：每一行都带风险等级、审批决策、
 * 幂等键和耗时。没有它，门禁只是 README 里的一句承诺。
 */
export function InvocationTable({ invocations, loading }: InvocationTableProps) {
  if (loading) {
    return (
      <div className="flex items-center gap-2 px-1 py-6 text-sm text-(--text-4)">
        <Loader2 className="animate-spin" size={15} aria-hidden="true" />
        读取调用记录…
      </div>
    );
  }

  if (invocations.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-(--line) px-4 py-6 text-sm text-(--text-4)">
        暂无工具调用记录。每次调用的风险判定、审批决策与幂等键都会留在这里。
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] border-collapse text-left text-sm">
        <thead>
          <tr className="border-b border-(--line) text-[11px] uppercase tracking-wider text-(--text-5)">
            <th className="py-2 pr-3 font-medium">工具</th>
            <th className="py-2 pr-3 font-medium">风险</th>
            <th className="py-2 pr-3 font-medium">决策</th>
            <th className="py-2 pr-3 font-medium">状态</th>
            <th className="py-2 pr-3 font-medium">耗时</th>
            <th className="py-2 pr-3 font-medium">幂等键</th>
            <th className="py-2 font-medium">时间</th>
          </tr>
        </thead>
        <tbody>
          {invocations.map((invocation) => (
            <tr className="border-b border-(--line)/50 last:border-b-0" key={invocation.id}>
              <td className="py-2 pr-3">
                <span className="font-mono text-xs text-(--text-2)">
                  {invocation.tool_name}
                </span>
                {invocation.error ? (
                  <p className="mt-0.5 line-clamp-1 text-[11px] text-red-300">
                    {invocation.error}
                  </p>
                ) : null}
              </td>
              <td className="py-2 pr-3">
                <span
                  className={`rounded border bg-(--fill-1) px-1.5 py-0.5 text-[11px] ${
                    RISK_TONES[invocation.risk_level] ?? RISK_TONES.low
                  }`}
                >
                  {RISK_LABELS[invocation.risk_level] ?? invocation.risk_level}
                </span>
              </td>
              <td className={`py-2 pr-3 text-xs ${decisionTone(invocation.decision)}`}>
                <span title={invocation.decision_reason || undefined}>
                  {DECISION_LABELS[invocation.decision] ?? invocation.decision}
                </span>
              </td>
              <td className="py-2 pr-3 text-xs text-(--text-4)">{invocation.status}</td>
              <td className="py-2 pr-3 font-mono text-xs text-(--text-4)">
                {invocation.duration_ms === null ? "—" : `${invocation.duration_ms} ms`}
              </td>
              <td className="py-2 pr-3 font-mono text-[11px] text-(--text-5)">
                {invocation.idempotency_key ? (
                  <span title={invocation.idempotency_key}>
                    {invocation.idempotency_key.slice(0, 12)}
                  </span>
                ) : (
                  "—"
                )}
              </td>
              <td className="py-2 font-mono text-[11px] text-(--text-5)">
                {formatDate(invocation.started_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
