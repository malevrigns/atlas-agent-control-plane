import { Plug, RefreshCcw } from "lucide-react";

import type { LoadState, McpServerListData, McpToolListData } from "../types";

type McpPanelProps = {
  onRefresh: () => void; // 重新读取 MCP Server 和工具列表。
  servers: LoadState<McpServerListData>; // /api/mcp/servers 返回的配置状态。
  tools: LoadState<McpToolListData>; // /api/mcp/tools 发现到的 MCP 工具。
};


// ===================== 第1步：展示 MCP Server 和工具发现结果 =====================
export function McpPanel({ onRefresh, servers, tools }: McpPanelProps) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-base font-semibold text-slate-950">
            <Plug size={17} aria-hidden="true" />
            MCP 工具
          </h2>
          <p className="mt-1 text-sm leading-5 text-slate-500">
            查看已配置 Server 和发现到的外部工具
          </p>
        </div>
        <button
          className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
          onClick={onRefresh}
          title="刷新 MCP"
          type="button"
        >
          <RefreshCcw size={16} aria-hidden="true" />
        </button>
      </div>

      <div className="mt-4 grid gap-4">
        <ServerList state={servers} />
        <ToolList state={tools} />
      </div>
    </div>
  );
}


function ServerList({ state }: { state: LoadState<McpServerListData> }) {
  if (state.type === "loading") {
    return <p className="text-sm text-slate-500">正在读取 MCP Server...</p>;
  }
  if (state.type === "error") {
    return <p className="text-sm text-rose-600">{state.message}</p>;
  }
  return (
    <div>
      <h3 className="text-sm font-semibold text-slate-900">Server</h3>
      <div className="mt-2 grid gap-2">
        {state.data.items.map((server) => (
          <div
            className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2"
            key={server.name}
          >
            <div className="flex items-center justify-between gap-3 text-sm">
              <span className="font-medium text-slate-900">{server.name}</span>
              <span className="text-xs text-slate-500">{server.transport}</span>
            </div>
            <p className="mt-1 text-xs leading-5 text-slate-500">
              {server.description || (server.enabled ? "已启用" : "未启用")}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}


function ToolList({ state }: { state: LoadState<McpToolListData> }) {
  if (state.type === "loading") {
    return <p className="text-sm text-slate-500">正在发现 MCP 工具...</p>;
  }
  if (state.type === "error") {
    return <p className="text-sm text-rose-600">{state.message}</p>;
  }
  return (
    <div>
      <h3 className="text-sm font-semibold text-slate-900">已发现工具</h3>
      <div className="mt-2 grid gap-2">
        {state.data.items.map((tool) => (
          <div
            className="rounded-md border border-slate-200 bg-white px-3 py-2"
            key={`${tool.server_name}-${tool.name}`}
          >
            <div className="text-sm font-medium text-slate-900">
              {tool.server_name}.{tool.name}
            </div>
            <p className="mt-1 text-xs leading-5 text-slate-500">
              {tool.description || "暂无说明"}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

