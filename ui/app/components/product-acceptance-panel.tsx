"use client";

import { CheckCircle2, ClipboardCheck, Eye, RefreshCcw } from "lucide-react";
import { useEffect, useState } from "react";

import { fetchProductAcceptanceChecks } from "../lib/acceptance-api";
import type {
  LoadState,
  ProductAcceptanceChecklistData,
  ProductAcceptanceItem,
} from "../types";


// ===================== 第1步：展示最终产品体验验收入口 =====================
export function ProductAcceptancePanel() {
  const [checklist, setChecklist] = useState<
    LoadState<ProductAcceptanceChecklistData>
  >({ type: "loading" });

  async function loadChecklist() {
    // 1. 刷新时先进入 loading，让用户知道正在读取最新验收清单。
    setChecklist({ type: "loading" });
    try {
      // 2. 从主 API 读取最终产品体验验收项。
      const data = await fetchProductAcceptanceChecks();
      setChecklist({ type: "ready", data });
    } catch (error) {
      // 3. 设置页不能因为验收接口失败而整体不可用，所以错误只显示在本面板内。
      const message = error instanceof Error ? error.message : "unknown error";
      setChecklist({ type: "error", message });
    }
  }

  useEffect(() => {
    loadChecklist();
  }, []);

  return (
    <section className="rounded-md border border-slate-200 bg-white p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="flex items-center gap-2 text-base font-semibold text-slate-950">
            <ClipboardCheck size={18} aria-hidden="true" />
            产品体验验收
          </h3>
          <p className="mt-1 text-sm leading-6 text-slate-500">
            汇总自然对话、工具预览、记忆、多 Agent、Harness 和沙箱观察的最终验收项
          </p>
        </div>
        <button
          className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
          onClick={loadChecklist}
          title="刷新验收清单"
          type="button"
        >
          <RefreshCcw size={16} aria-hidden="true" />
        </button>
      </div>

      {checklist.type === "loading" ? (
        <div className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-500">
          正在读取产品体验验收清单...
        </div>
      ) : null}

      {checklist.type === "error" ? (
        <div className="mt-4 rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
          {checklist.message}
        </div>
      ) : null}

      {checklist.type === "ready" ? (
        <ProductAcceptanceReadyView data={checklist.data} />
      ) : null}
    </section>
  );
}


function ProductAcceptanceReadyView({
  data,
}: {
  data: ProductAcceptanceChecklistData;
}) {
  return (
    <div className="mt-4 grid gap-4">
      <div className="grid grid-cols-3 gap-3 max-md:grid-cols-1">
        <SummaryCard label="验收项" value={data.summary.total} />
        <SummaryCard label="已有证据" value={data.summary.ready} />
        <SummaryCard label="人工确认" value={data.summary.needs_manual_check} />
      </div>

      <div className="grid gap-3">
        {data.items.map((item) => (
          <ProductAcceptanceItemCard item={item} key={item.key} />
        ))}
      </div>
    </div>
  );
}


function SummaryCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 p-4">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-2 text-2xl font-semibold text-slate-950">{value}</div>
    </div>
  );
}


// ===================== 第2步：展示单条验收项的证据、步骤和相关接口 =====================
function ProductAcceptanceItemCard({ item }: { item: ProductAcceptanceItem }) {
  const ready = item.status === "ready";

  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`inline-flex items-center gap-1 rounded-full border px-2 py-1 text-xs font-medium ${
            ready
              ? "border-emerald-200 bg-emerald-50 text-emerald-700"
              : "border-sky-200 bg-sky-50 text-sky-700"
          }`}
        >
          {ready ? (
            <CheckCircle2 size={13} aria-hidden="true" />
          ) : (
            <Eye size={13} aria-hidden="true" />
          )}
          {ready ? "已有证据" : "人工确认"}
        </span>
        <span className="rounded bg-white px-2 py-1 text-xs text-slate-500">
          {item.category}
        </span>
        <h4 className="text-sm font-semibold text-slate-950">{item.title}</h4>
      </div>

      <p className="mt-3 text-xs leading-5 text-slate-600">
        <span className="font-medium text-slate-900">验收证据：</span>
        {item.evidence}
      </p>

      <div className="mt-3">
        <div className="text-xs font-medium text-slate-900">验证步骤</div>
        <ol className="mt-2 grid gap-1 text-xs leading-5 text-slate-600">
          {item.verify_steps.map((step, index) => (
            <li key={`${item.key}-step-${step}`}>
              {index + 1}. {step}
            </li>
          ))}
        </ol>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {item.related_routes.map((route) => (
          <span
            className="rounded-md border border-slate-200 bg-white px-2 py-1 font-mono text-[11px] text-slate-600"
            key={`${item.key}-${route}`}
          >
            {route}
          </span>
        ))}
      </div>
    </div>
  );
}
