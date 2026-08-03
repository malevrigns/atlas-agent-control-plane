"use client";

import {
  CheckCircle2,
  FlaskConical,
  Play,
  RefreshCcw,
  RotateCcw,
  XCircle,
} from "lucide-react";
import { useEffect, useState } from "react";

import {
  fetchHarnessCases,
  replayHarnessRun,
  runHarnessCase,
} from "../lib/harness-api";
import type {
  HarnessCaseItem,
  HarnessCaseListData,
  HarnessReplayData,
  HarnessRunData,
  LoadState,
} from "../types";

type HarnessActionState =
  | { type: "idle" }
  | { type: "running"; caseId: string }
  | { type: "error"; message: string };


// ===================== 第1步：展示 Agent Harness 回归评测入口 =====================
export function HarnessPanel() {
  const [cases, setCases] = useState<LoadState<HarnessCaseListData>>({
    type: "loading",
  });
  const [latestRun, setLatestRun] = useState<HarnessRunData | null>(null);
  const [replay, setReplay] = useState<HarnessReplayData | null>(null);
  const [action, setAction] = useState<HarnessActionState>({ type: "idle" });

  async function loadCases() {
    setCases({ type: "loading" });
    try {
      const data = await fetchHarnessCases();
      setCases({ type: "ready", data });
    } catch (error) {
      const message = error instanceof Error ? error.message : "unknown error";
      setCases({ type: "error", message });
    }
  }

  async function runCase(item: HarnessCaseItem) {
    setAction({ type: "running", caseId: item.id });
    setReplay(null);
    try {
      const run = await runHarnessCase(item.id);
      setLatestRun(run);
      setAction({ type: "idle" });
    } catch (error) {
      const message = error instanceof Error ? error.message : "unknown error";
      setAction({ type: "error", message });
    }
  }

  async function replayLatestRun() {
    if (!latestRun) {
      return;
    }
    setAction({ type: "running", caseId: latestRun.case_id });
    try {
      const data = await replayHarnessRun(latestRun.id);
      setReplay(data);
      setAction({ type: "idle" });
    } catch (error) {
      const message = error instanceof Error ? error.message : "unknown error";
      setAction({ type: "error", message });
    }
  }

  useEffect(() => {
    loadCases();
  }, []);

  return (
    <section className="rounded-md border border-slate-200 bg-white p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="flex items-center gap-2 text-base font-semibold text-slate-950">
            <FlaskConical size={18} aria-hidden="true" />
            Agent Harness
          </h3>
          <p className="mt-1 text-sm leading-6 text-slate-500">
            固定任务集、断言和失败回放，用来检查模型、提示词和工具改动是否退化
          </p>
        </div>
        <button
          className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
          onClick={loadCases}
          title="刷新 Harness 用例"
          type="button"
        >
          <RefreshCcw size={16} aria-hidden="true" />
        </button>
      </div>

      {cases.type === "loading" ? (
        <div className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-500">
          正在读取 Harness 任务集...
        </div>
      ) : null}

      {cases.type === "error" ? (
        <div className="mt-4 rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
          {cases.message}
        </div>
      ) : null}

      {action.type === "error" ? (
        <div className="mt-4 rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
          {action.message}
        </div>
      ) : null}

      {cases.type === "ready" ? (
        <div className="mt-4 grid gap-3">
          {cases.data.items.map((item) => (
            <HarnessCaseCard
              action={action}
              item={item}
              key={item.id}
              onRun={() => runCase(item)}
            />
          ))}
        </div>
      ) : null}

      {latestRun ? (
        <HarnessRunResult
          onReplay={replayLatestRun}
          replay={replay}
          run={latestRun}
        />
      ) : null}
    </section>
  );
}


// ===================== 第2步：展示单条评测用例 =====================
function HarnessCaseCard({
  action,
  item,
  onRun,
}: {
  action: HarnessActionState;
  item: HarnessCaseItem;
  onRun: () => void;
}) {
  const running = action.type === "running" && action.caseId === item.id;

  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-slate-950">
            {item.title}
          </div>
          <p className="mt-1 text-xs leading-5 text-slate-500">
            {item.description}
          </p>
          <p className="mt-2 line-clamp-2 text-xs text-slate-700">
            {item.task}
          </p>
        </div>
        <button
          className="inline-flex h-9 shrink-0 items-center gap-2 rounded-md bg-slate-950 px-3 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
          disabled={running}
          onClick={onRun}
          type="button"
        >
          <Play size={15} aria-hidden="true" />
          {running ? "运行中" : "模拟运行"}
        </button>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {item.tags.map((tag) => (
          <span
            className="rounded bg-white px-2 py-1 text-xs text-slate-600"
            key={`${item.id}-${tag}`}
          >
            {tag}
          </span>
        ))}
      </div>
    </div>
  );
}


// ===================== 第3步：展示运行结果、断言和事件回放 =====================
function HarnessRunResult({
  onReplay,
  replay,
  run,
}: {
  onReplay: () => void;
  replay: HarnessReplayData | null;
  run: HarnessRunData;
}) {
  const passed = run.status === "passed";

  return (
    <div className="mt-5 rounded-md border border-slate-200 bg-slate-50 p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
            {passed ? (
              <CheckCircle2 className="text-emerald-600" size={17} />
            ) : (
              <XCircle className="text-rose-600" size={17} />
            )}
            最近运行：{run.status}
          </div>
          <p className="mt-1 text-xs leading-5 text-slate-500">
            {run.prompt_summary}
          </p>
        </div>
        <button
          className="inline-flex h-9 shrink-0 items-center gap-2 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700 hover:bg-slate-50"
          onClick={onReplay}
          type="button"
        >
          <RotateCcw size={15} aria-hidden="true" />
          回放
        </button>
      </div>

      <div className="mt-4 grid gap-2">
        {run.assertions.map((assertion) => (
          <div
            className="flex items-start gap-2 rounded-md border border-slate-200 bg-white px-3 py-2 text-xs"
            key={assertion.name}
          >
            {assertion.passed ? (
              <CheckCircle2 className="mt-0.5 shrink-0 text-emerald-600" size={14} />
            ) : (
              <XCircle className="mt-0.5 shrink-0 text-rose-600" size={14} />
            )}
            <div className="min-w-0">
              <div className="font-medium text-slate-900">{assertion.name}</div>
              <div className="mt-1 text-slate-500">{assertion.detail}</div>
            </div>
          </div>
        ))}
      </div>

      {replay ? (
        <div className="mt-4 rounded-md border border-slate-200 bg-white p-3">
          <div className="text-xs font-semibold text-slate-900">事件回放</div>
          <div className="mt-2 grid gap-2">
            {replay.events.map((event, index) => (
              <div
                className="rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-600"
                key={event.id}
              >
                <div className="font-medium text-slate-900">
                  {index + 1}. {event.type}
                </div>
                <pre className="mt-1 max-h-28 overflow-auto whitespace-pre-wrap text-[11px] leading-5">
                  {JSON.stringify(event.payload, null, 2)}
                </pre>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
