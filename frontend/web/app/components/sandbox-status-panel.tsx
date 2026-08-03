import { Box, CheckCircle2, Loader2, RefreshCcw, XCircle } from "lucide-react";

import type { LoadState, SandboxInstanceData } from "../types";

type SandboxStatusPanelProps = {
  onRefresh: () => void; // 点击刷新时调用 /api/sandboxes/current/wait。
  refreshing: boolean; // true 时禁用按钮，避免重复发起健康等待。
  state: LoadState<SandboxInstanceData>; // 来自主 API，不直接请求 /sandbox-api。
};


// ===================== 第1步：展示当前任务沙箱状态 =====================
export function SandboxStatusPanel({
  onRefresh,
  refreshing,
  state,
}: SandboxStatusPanelProps) {
  // buildSandboxView 把接口状态转换成 UI 需要的图标、颜色和文案。
  const view = buildSandboxView(state);
  const Icon = view.icon;

  return (
    <div className="rounded-md border border-slate-200 bg-white p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-slate-950">任务沙箱</h2>
          <p className="mt-1 text-sm leading-5 text-slate-500">
            当前会话使用的 Sandbox 运行状态
          </p>
        </div>
        <button
          className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:text-slate-300"
          disabled={refreshing}
          onClick={onRefresh}
          title="刷新沙箱状态"
          type="button"
        >
          {refreshing ? (
            <Loader2 className="animate-spin" size={16} />
          ) : (
            <RefreshCcw size={16} />
          )}
        </button>
      </div>

      <div className="mt-4 flex items-center gap-3 rounded-md border border-slate-200 bg-slate-50 p-3">
        <Icon className={view.iconClassName} size={18} aria-hidden="true" />
        <div className="min-w-0">
          <p className="text-sm font-medium text-slate-900">{view.title}</p>
          <p className="mt-1 truncate text-xs text-slate-500">{view.message}</p>
        </div>
      </div>

      {state.type === "ready" ? (
        <dl className="mt-4 grid gap-2 text-xs text-slate-600">
          <div className="flex justify-between gap-3">
            <dt>实例</dt>
            <dd className="truncate font-medium text-slate-900">{state.data.id}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt>容器</dt>
            <dd className="truncate font-medium text-slate-900">{state.data.name}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt>状态</dt>
            <dd className="truncate font-medium text-slate-900">{state.data.status}</dd>
          </div>
        </dl>
      ) : null}
    </div>
  );
}


function buildSandboxView(state: LoadState<SandboxInstanceData>) {
  // loading 表示页面还在读取主 API 的当前沙箱状态。
  if (state.type === "loading") {
    return {
      icon: Loader2,
      iconClassName: "animate-spin text-slate-500",
      message: "正在检查 Sandbox 健康状态",
      title: "检测中",
    };
  }
  // error 通常来自主 API 或 Sandbox 不可访问，需要明确显示给用户。
  if (state.type === "error") {
    return {
      icon: XCircle,
      iconClassName: "text-rose-600",
      message: state.message,
      title: "沙箱异常",
    };
  }
  // ready 是任务执行前最重要的状态，说明 FileTool/ShellTool 可以访问沙箱。
  if (state.data.status === "ready") {
    return {
      icon: CheckCircle2,
      iconClassName: "text-emerald-600",
      message: state.data.message,
      title: "沙箱可用",
    };
  }
  return {
    icon: Box,
    iconClassName: "text-amber-600",
    message: state.data.message,
    title: "沙箱未就绪",
  };
}
