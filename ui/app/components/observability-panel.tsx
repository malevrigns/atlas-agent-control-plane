"use client";

import { Activity, Copy, RefreshCcw, TerminalSquare } from "lucide-react";
import { useEffect, useState } from "react";

import { fetchObservabilityChecks } from "../lib/observability-api";
import type {
  LoadState,
  ObservabilityCheckItem,
  ObservabilityCheckListData,
} from "../types";


// ===================== 第1步：展示系统诊断和可观测性入口 =====================
export function ObservabilityPanel() {
  const [checks, setChecks] = useState<
    LoadState<ObservabilityCheckListData>
  >({ type: "loading" });

  async function loadChecks() {
    setChecks({ type: "loading" });
    try {
      const data = await fetchObservabilityChecks();
      setChecks({ type: "ready", data });
    } catch (error) {
      const message = error instanceof Error ? error.message : "unknown error";
      setChecks({ type: "error", message });
    }
  }

  useEffect(() => {
    loadChecks();
  }, []);

  return (
    <section className="rounded-md border border-slate-200 bg-white p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="flex items-center gap-2 text-base font-semibold text-slate-950">
            <Activity size={18} aria-hidden="true" />
            系统诊断
          </h3>
          <p className="mt-1 text-sm leading-6 text-slate-500">
            汇总 API、数据库、沙箱、工具、记忆和 Harness 的常用排查命令
          </p>
        </div>
        <button
          className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
          onClick={loadChecks}
          title="刷新诊断清单"
          type="button"
        >
          <RefreshCcw size={16} aria-hidden="true" />
        </button>
      </div>

      {checks.type === "loading" ? (
        <div className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-500">
          正在读取诊断清单...
        </div>
      ) : null}

      {checks.type === "error" ? (
        <div className="mt-4 rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
          {checks.message}
        </div>
      ) : null}

      {checks.type === "ready" ? (
        <div className="mt-4 grid gap-3">
          {checks.data.items.map((item) => (
            <ObservabilityCheckCard item={item} key={item.key} />
          ))}
        </div>
      ) : null}
    </section>
  );
}


// ===================== 第2步：展示单条诊断命令和预期结果 =====================
function ObservabilityCheckCard({ item }: { item: ObservabilityCheckItem }) {
  async function copyCommand() {
    await navigator.clipboard.writeText(item.command);
  }

  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <TerminalSquare className="text-slate-500" size={16} />
            <span className="text-sm font-semibold text-slate-950">
              {item.name}
            </span>
            <span className="rounded bg-white px-2 py-1 text-xs text-slate-500">
              {item.category}
            </span>
          </div>
          <p className="mt-2 text-xs leading-5 text-slate-500">
            {item.description}
          </p>
        </div>
        <button
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
          onClick={copyCommand}
          title="复制命令"
          type="button"
        >
          <Copy size={14} aria-hidden="true" />
        </button>
      </div>

      <pre className="mt-3 overflow-auto rounded-md bg-slate-950 p-3 text-xs leading-5 text-slate-100">
        {item.command}
      </pre>
      <p className="mt-2 text-xs leading-5 text-slate-500">
        预期：{item.expected}
      </p>
    </div>
  );
}
