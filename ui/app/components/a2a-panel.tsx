import { Network, RefreshCcw } from "lucide-react";

import type {
  A2aAgentCardData,
  A2aConceptsData,
  A2aRemoteAgentListData,
  LoadState,
} from "../types";

type A2aPanelProps = {
  agentCard: LoadState<A2aAgentCardData>;
  agents: LoadState<A2aRemoteAgentListData>;
  concepts: LoadState<A2aConceptsData>;
  onRefresh: () => void;
};


// ===================== 第1步：展示 A2A 远程 Agent 概念和示例 Agent Card =====================
export function A2aPanel({
  agentCard,
  agents,
  concepts,
  onRefresh,
}: A2aPanelProps) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-base font-semibold text-slate-950">
            <Network size={17} aria-hidden="true" />
            A2A Agent
          </h2>
          <p className="mt-1 text-sm leading-5 text-slate-500">
            理解远程 Agent、Agent Card 和跨 Agent 任务消息
          </p>
        </div>
        <button
          className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
          onClick={onRefresh}
          title="刷新 A2A"
          type="button"
        >
          <RefreshCcw size={16} aria-hidden="true" />
        </button>
      </div>

      <div className="mt-4 grid gap-4">
        <ConceptsView state={concepts} />
        <AgentListView state={agents} />
        <AgentCardView state={agentCard} />
      </div>
    </div>
  );
}


function ConceptsView({ state }: { state: LoadState<A2aConceptsData> }) {
  if (state.type === "loading") {
    return <p className="text-sm text-slate-500">正在读取 A2A 概念...</p>;
  }
  if (state.type === "error") {
    return <p className="text-sm text-rose-600">{state.message}</p>;
  }
  return (
    <div>
      <h3 className="text-sm font-semibold text-slate-900">核心角色</h3>
      <div className="mt-2 grid gap-2">
        {state.data.roles.map((role) => (
          <div
            className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2"
            key={role.name}
          >
            <div className="text-sm font-medium text-slate-900">
              {role.name}
            </div>
            <p className="mt-1 text-xs leading-5 text-slate-600">
              {role.responsibility}
            </p>
            <p className="mt-1 text-xs leading-5 text-slate-500">
              {role.system_mapping}
            </p>
          </div>
        ))}
      </div>
      <p className="mt-2 text-xs leading-5 text-slate-500">
        下一步：{state.data.next_step}
      </p>
    </div>
  );
}


function AgentListView({ state }: { state: LoadState<A2aRemoteAgentListData> }) {
  if (state.type === "loading") {
    return <p className="text-sm text-slate-500">正在读取 A2A Agent 配置...</p>;
  }
  if (state.type === "error") {
    return <p className="text-sm text-rose-600">{state.message}</p>;
  }
  return (
    <div>
      <h3 className="text-sm font-semibold text-slate-900">已配置远程 Agent</h3>
      <div className="mt-2 grid gap-2">
        {state.data.items.map((agent) => (
          <div
            className="rounded-md border border-slate-200 bg-white px-3 py-2"
            key={agent.key}
          >
            <div className="flex items-center justify-between gap-3 text-sm">
              <span className="font-medium text-slate-900">{agent.name}</span>
              <span className="text-xs text-slate-500">
                {agent.transport} · {agent.enabled ? "enabled" : "disabled"}
              </span>
            </div>
            <p className="mt-1 text-xs leading-5 text-slate-500">
              {agent.description}
            </p>
            <p className="mt-1 truncate text-xs text-sky-700">{agent.url}</p>
          </div>
        ))}
      </div>
    </div>
  );
}


function AgentCardView({ state }: { state: LoadState<A2aAgentCardData> }) {
  if (state.type === "loading") {
    return <p className="text-sm text-slate-500">正在读取 Agent Card...</p>;
  }
  if (state.type === "error") {
    return <p className="text-sm text-rose-600">{state.message}</p>;
  }
  return (
    <div>
      <h3 className="text-sm font-semibold text-slate-900">示例 Agent Card</h3>
      <div className="mt-2 rounded-md border border-slate-200 bg-white px-3 py-2">
        <div className="flex items-center justify-between gap-3 text-sm">
          <span className="font-medium text-slate-900">{state.data.name}</span>
          <span className="text-xs text-slate-500">v{state.data.version}</span>
        </div>
        <p className="mt-1 text-xs leading-5 text-slate-500">
          {state.data.description}
        </p>
        <div className="mt-3 grid gap-2">
          {state.data.capabilities.map((capability) => (
            <div
              className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2"
              key={capability.name}
            >
              <div className="text-xs font-semibold text-slate-900">
                {capability.name}
              </div>
              <p className="mt-1 text-xs leading-5 text-slate-600">
                {capability.description}
              </p>
              <p className="mt-1 text-xs leading-5 text-slate-500">
                示例：{capability.example}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
