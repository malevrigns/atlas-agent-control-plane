"use client";

import { Copy, RefreshCcw, ShieldAlert, ShieldCheck, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";

import { fetchSecurityChecks } from "../lib/security-api";
import type {
  LoadState,
  SecurityCheckItem,
  SecurityCheckListData,
} from "../types";


// ===================== 第1步：展示安全边界检查入口 =====================
export function SecurityPanel() {
  const [checks, setChecks] = useState<LoadState<SecurityCheckListData>>({
    type: "loading",
  });

  async function loadChecks() {
    // 1. 每次刷新先进入 loading，避免用户看到旧数据还以为已经更新。
    setChecks({ type: "loading" });
    try {
      // 2. 从主 API 读取结构化安全检查清单。
      const data = await fetchSecurityChecks();
      setChecks({ type: "ready", data });
    } catch (error) {
      // 3. 请求失败时只展示错误文案，不让整个设置页崩溃。
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
            <ShieldAlert size={18} aria-hidden="true" />
            安全边界
          </h3>
          <p className="mt-1 text-sm leading-6 text-slate-500">
            检查配置、上传、沙箱、外部集成和长期记忆的上线风险
          </p>
        </div>
        <button
          className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
          onClick={loadChecks}
          title="刷新安全清单"
          type="button"
        >
          <RefreshCcw size={16} aria-hidden="true" />
        </button>
      </div>

      {checks.type === "loading" ? (
        <div className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-500">
          正在读取安全检查清单...
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
            <SecurityCheckCard item={item} key={item.key} />
          ))}
        </div>
      ) : null}
    </section>
  );
}


// ===================== 第2步：展示单条安全检查和修复建议 =====================
function SecurityCheckCard({ item }: { item: SecurityCheckItem }) {
  async function copyCommand() {
    // 1. 验证命令通常会被复制到终端执行，所以这里直接复制完整命令。
    await navigator.clipboard.writeText(item.verify_command);
  }

  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <SeverityBadge severity={item.severity} />
            <span className="text-sm font-semibold text-slate-950">
              {item.name}
            </span>
            <span className="rounded bg-white px-2 py-1 text-xs text-slate-500">
              {item.category}
            </span>
          </div>
          <p className="mt-3 text-xs leading-5 text-slate-600">
            <span className="font-medium text-slate-900">风险：</span>
            {item.risk}
          </p>
          <p className="mt-2 text-xs leading-5 text-slate-600">
            <span className="font-medium text-slate-900">建议：</span>
            {item.recommendation}
          </p>
        </div>
        <button
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
          onClick={copyCommand}
          title="复制验证命令"
          type="button"
        >
          <Copy size={14} aria-hidden="true" />
        </button>
      </div>

      <pre className="mt-3 overflow-auto rounded-md bg-slate-950 p-3 text-xs leading-5 text-slate-100">
        {item.verify_command}
      </pre>
    </div>
  );
}


// ===================== 第3步：把风险等级转换成稳定的视觉提示 =====================
function SeverityBadge({ severity }: { severity: SecurityCheckItem["severity"] }) {
  if (severity === "risk") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-rose-200 bg-rose-50 px-2 py-1 text-xs font-medium text-rose-700">
        <TriangleAlert size={13} aria-hidden="true" />
        高风险
      </span>
    );
  }

  if (severity === "warning") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-1 text-xs font-medium text-amber-700">
        <ShieldAlert size={13} aria-hidden="true" />
        注意
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700">
      <ShieldCheck size={13} aria-hidden="true" />
      提示
    </span>
  );
}
