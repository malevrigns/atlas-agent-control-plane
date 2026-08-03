import { GitBranch, RefreshCcw } from "lucide-react";

import type { LoadState, MultiAgentRoleListData } from "../types";

type MultiAgentPanelProps = {
  onRefresh: () => void;
  roles: LoadState<MultiAgentRoleListData>;
};


// ===================== 第1步：展示多 Agent 协作角色 =====================
export function MultiAgentPanel({ onRefresh, roles }: MultiAgentPanelProps) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-base font-semibold text-slate-950">
            <GitBranch size={17} aria-hidden="true" />
            多 Agent 协作
          </h2>
          <p className="mt-1 text-sm leading-5 text-slate-500">
            Manager 拆解任务，Worker 执行子任务，Reviewer 评审结果
          </p>
        </div>
        <button
          className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
          onClick={onRefresh}
          title="刷新多 Agent 角色"
          type="button"
        >
          <RefreshCcw size={16} aria-hidden="true" />
        </button>
      </div>

      <div className="mt-4">
        <RoleList state={roles} />
      </div>
    </div>
  );
}


function RoleList({ state }: { state: LoadState<MultiAgentRoleListData> }) {
  if (state.type === "loading") {
    return <p className="text-sm text-slate-500">正在读取协作角色...</p>;
  }

  if (state.type === "error") {
    return <p className="text-sm text-rose-600">{state.message}</p>;
  }

  return (
    <div className="grid gap-2">
      {state.data.items.map((role) => (
        <div
          className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2"
          key={role.key}
        >
          <div className="text-sm font-medium text-slate-900">{role.name}</div>
          <p className="mt-1 text-xs leading-5 text-slate-600">
            {role.responsibility}
          </p>
          <p className="mt-1 text-xs leading-5 text-slate-500">
            能力：{role.capability}
          </p>
        </div>
      ))}
    </div>
  );
}
