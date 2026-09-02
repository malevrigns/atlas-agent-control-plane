"use client";

import {
  Activity,
  AlertTriangle,
  CircleCheck,
  Clock,
  GitBranch,
  Loader2,
  RefreshCcw,
  Target,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { CheckpointTrack } from "./control-plane/checkpoint-track";
import { InvocationTable } from "./control-plane/invocation-table";
import { RunTimeline } from "./control-plane/run-timeline";
import { TodoBoardPanel } from "./control-plane/todo-board";
import { SelectMenu } from "./select-menu";
import {
  fetchCheckpoints,
  fetchControlPlaneTasks,
  fetchTodoBoard,
  fetchToolInvocations,
  restoreCheckpoint,
} from "../lib/control-plane-api";
import type {
  Checkpoint,
  TaskState,
  TodoBoard,
  ToolInvocation,
} from "../lib/control-plane-api";
import { fetchEvents } from "../lib/session-api";
import { formatDateTime } from "../lib/format";
import { buildRunTrace, formatDuration } from "../lib/run-trace";
import { workspaceSurface, workspaceText } from "../lib/design-tokens";
import type { SessionEventItem } from "../types";

const STATUS_FILTERS = [
  { value: "", label: "全部状态" },
  { value: "pending", label: "待开始" },
  { value: "running", label: "执行中" },
  { value: "blocked", label: "阻塞" },
  { value: "done", label: "已完成" },
  { value: "failed", label: "失败" },
];

const STATUS_TONES: Record<string, string> = {
  running: "border-(--accent)/50 text-(--accent)",
  done: "border-emerald-400/50 text-(--success-text)",
  completed: "border-emerald-400/50 text-(--success-text)",
  failed: "border-red-400/50 text-(--error-text)",
  blocked: "border-amber-400/50 text-(--warn-text)",
};

function statusTone(status: string): string {
  return STATUS_TONES[status] ?? "border-(--line) text-(--text-4)";
}

/** 任务的完成度：优先用 progress 三列，读不到就退回 acceptance_criteria 数量。 */
function taskProgress(task: TaskState): { done: number; total: number } {
  const done = task.progress?.done?.length ?? 0;
  const doing = task.progress?.doing?.length ?? 0;
  const blocked = task.progress?.blocked?.length ?? 0;
  const total = done + doing + blocked;
  return { done, total };
}

/**
 * 任务驾驶舱：以任务为单位看 agent 的长程执行。
 *
 * 对话工作台是"一次会话"的视角，够不到长程任务的真实形态——跑几小时、
 * 跨多轮、中途失败重试、从检查点续跑。这里把控制面已经存下来的东西摊开：
 * 执行轨迹、三级门禁结论、检查点父子链、工具调用留痕。
 */
export function ControlPlaneWorkspace() {
  const [tasks, setTasks] = useState<TaskState[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [loadingTasks, setLoadingTasks] = useState(true);
  const [events, setEvents] = useState<SessionEventItem[]>([]);
  const [loadingEvents, setLoadingEvents] = useState(false);
  const [checkpoints, setCheckpoints] = useState<Checkpoint[]>([]);
  const [loadingCheckpoints, setLoadingCheckpoints] = useState(false);
  const [invocations, setInvocations] = useState<ToolInvocation[]>([]);
  const [loadingInvocations, setLoadingInvocations] = useState(false);
  const [board, setBoard] = useState<TodoBoard | null>(null);
  const [loadingBoard, setLoadingBoard] = useState(false);
  const [restoringId, setRestoringId] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [noticeTone, setNoticeTone] = useState<"info" | "danger">("info");

  const report = useCallback((message: string, tone: "info" | "danger" = "info") => {
    setNotice(message);
    setNoticeTone(tone);
  }, []);

  const refreshTasks = useCallback(async () => {
    setLoadingTasks(true);
    try {
      const data = await fetchControlPlaneTasks({ limit: 200 });
      setTasks(data.items);
      setSelectedId((current) =>
        current && data.items.some((task) => task.id === current)
          ? current
          : data.items[0]?.id ?? null,
      );
    } catch (error) {
      report(error instanceof Error ? error.message : "读取任务失败", "danger");
    } finally {
      setLoadingTasks(false);
    }
  }, [report]);

  useEffect(() => {
    void refreshTasks();
  }, [refreshTasks]);

  // 成功类通知短暂展示后自动消退；错误类保留，等用户手动关闭。
  useEffect(() => {
    if (!notice || noticeTone !== "info") {
      return;
    }
    const timer = window.setTimeout(() => setNotice(""), 4500);
    return () => window.clearTimeout(timer);
  }, [notice, noticeTone]);

  const selected = useMemo(
    () => tasks.find((task) => task.id === selectedId) ?? null,
    [tasks, selectedId],
  );

  const visibleTasks = useMemo(
    () => (statusFilter ? tasks.filter((task) => task.status === statusFilter) : tasks),
    [tasks, statusFilter],
  );

  // 选中任务变化时拉它的三份明细。事件挂在 session 上，没有关联会话就跳过。
  useEffect(() => {
    if (!selected) {
      setEvents([]);
      setCheckpoints([]);
      setInvocations([]);
      setBoard(null);
      setLoadingBoard(false);
      return;
    }
    let cancelled = false;
    const taskId = selected.id;
    const sessionId = selected.session_id;

    async function load() {
      setLoadingCheckpoints(true);
      setLoadingInvocations(true);
      setLoadingEvents(Boolean(sessionId));
      setLoadingBoard(Boolean(sessionId));
      try {
        const [checkpointResult, invocationResult] = await Promise.allSettled([
          fetchCheckpoints(taskId),
          fetchToolInvocations({ taskId, limit: 200 }),
        ]);
        if (cancelled) {
          return;
        }
        if (checkpointResult.status === "fulfilled") {
          setCheckpoints(checkpointResult.value.items);
        }
        if (invocationResult.status === "fulfilled") {
          setInvocations(invocationResult.value.items);
        }
      } finally {
        if (!cancelled) {
          setLoadingCheckpoints(false);
          setLoadingInvocations(false);
        }
      }

      if (!sessionId) {
        setEvents([]);
        setBoard(null);
        setLoadingBoard(false);
        return;
      }
      const [eventResult, boardResult] = await Promise.allSettled([
        fetchEvents(sessionId),
        fetchTodoBoard(sessionId),
      ]);
      if (cancelled) {
        return;
      }
      setEvents(eventResult.status === "fulfilled" ? eventResult.value : []);
      setBoard(boardResult.status === "fulfilled" ? boardResult.value : null);
      setLoadingEvents(false);
      setLoadingBoard(false);
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [selected]);

  const trace = useMemo(() => buildRunTrace(events), [events]);

  async function handleRestore(checkpoint: Checkpoint, resume: boolean) {
    if (!selected) {
      return;
    }
    setRestoringId(checkpoint.id);
    try {
      const result = await restoreCheckpoint(selected.id, checkpoint.id, {
        expected_version: selected.version,
        resume,
      });
      setTasks((current) =>
        current.map((task) => (task.id === result.task.id ? result.task : task)),
      );
      report(
        resume
          ? `已回滚到事件 ${checkpoint.covered_event_end} 并继续执行`
          : `已回滚到事件 ${checkpoint.covered_event_end}`,
      );
    } catch (error) {
      report(
        error instanceof Error ? error.message : "回滚失败，任务版本可能已变化",
        "danger",
      );
    } finally {
      setRestoringId(null);
    }
  }

  return (
    <section className="flex h-full min-h-0 gap-4 p-4 max-lg:flex-col max-lg:overflow-y-auto">
      {/* ============ 左：任务列表 ============ */}
      <div
        className={`flex w-[300px] min-h-0 shrink-0 flex-col rounded-xl max-lg:w-full ${workspaceSurface.panel}`}
      >
        <header className="flex items-center gap-2 border-b border-(--line) px-3 py-2.5">
          <Target size={15} aria-hidden="true" className="text-(--accent)" />
          <h2 className={`flex-1 text-sm ${workspaceText.heading}`}>长程任务</h2>
          <button
            aria-label="刷新任务列表"
            className="flex h-7 w-7 items-center justify-center rounded-md text-(--text-4) transition hover:bg-(--fill-2) hover:text-(--text-1)"
            onClick={() => void refreshTasks()}
            title="刷新任务列表"
            type="button"
          >
            <RefreshCcw size={14} aria-hidden="true" />
          </button>
        </header>

        <div className="border-b border-(--line) px-3 py-2">
          <SelectMenu
            ariaLabel="按状态筛选任务"
            className="w-full"
            onChange={setStatusFilter}
            options={STATUS_FILTERS}
            value={statusFilter}
          />
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2 max-lg:max-h-[240px]">
          {loadingTasks ? (
            <div className="flex items-center gap-2 px-2 py-4 text-sm text-(--text-4)">
              <Loader2 className="animate-spin" size={15} aria-hidden="true" />
              读取中…
            </div>
          ) : visibleTasks.length === 0 ? (
            <p className="px-2 py-4 text-sm leading-6 text-(--text-4)">
              还没有长程任务。用 POST /api/control-plane/tasks 建一个，或在对话里让
              agent 拆解一个多步目标。
            </p>
          ) : (
            <ul className="flex flex-col gap-1">
              {visibleTasks.map((task) => {
                const { done, total } = taskProgress(task);
                const active = task.id === selectedId;
                return (
                  <li key={task.id}>
                    <button
                      className={`w-full rounded-lg border px-2.5 py-2 text-left transition ${
                        active
                          ? "border-(--accent)/50 bg-(--fill-2)"
                          : "border-transparent hover:border-(--line) hover:bg-(--fill-1)"
                      }`}
                      onClick={() => setSelectedId(task.id)}
                      type="button"
                    >
                      <div className="flex items-center gap-2">
                        <span className="min-w-0 flex-1 truncate text-sm text-(--text-2)">
                          {task.title}
                        </span>
                        <span
                          className={`shrink-0 rounded border bg-(--fill-1) px-1.5 py-0.5 text-[10px] ${statusTone(task.status)}`}
                        >
                          {task.status}
                        </span>
                      </div>
                      <div className="mt-1.5 flex items-center gap-2 text-[11px] text-(--text-5)">
                        <span className="font-mono">v{task.version}</span>
                        {total > 0 ? (
                          <span>
                            {done}/{total} 步
                          </span>
                        ) : null}
                        <span className="ml-auto">{formatDateTime(task.updated_at)}</span>
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>

      {/* ============ 右：任务详情 ============ */}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-3 max-lg:overflow-visible">
        {notice ? (
          <div
            aria-live="polite"
            className={`flex shrink-0 items-center gap-2 rounded-lg border px-3 py-2 text-sm ${
              noticeTone === "danger"
                ? "border-red-400/40 bg-red-500/10 text-red-200"
                : "border-(--line) bg-(--fill-1) text-(--text-3)"
            }`}
          >
            <p className="min-w-0 flex-1">{notice}</p>
            <button
              aria-label="关闭通知"
              className="shrink-0 rounded-md p-1 transition hover:bg-(--fill-2) hover:text-(--text-1)"
              onClick={() => setNotice("")}
              type="button"
            >
              <X size={13} aria-hidden="true" />
            </button>
          </div>
        ) : null}

        {!selected ? (
          <div
            className={`flex flex-1 items-center justify-center rounded-xl px-6 text-center text-sm leading-7 text-(--text-4) ${workspaceSurface.panel}`}
          >
            选一个任务，这里会显示它的执行轨迹、门禁结论与检查点。
          </div>
        ) : (
          <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pr-0.5 max-lg:overflow-visible">
            <TaskHeader task={selected} trace={trace} board={board} />

            <Panel icon={Activity} title="执行轨迹" count={trace.entries.length}>
              <RunTimeline entries={trace.entries} loading={loadingEvents} />
            </Panel>

            <Panel icon={Target} title="任务清单" count={board?.items.length ?? 0}>
              <TodoBoardPanel board={board} loading={loadingBoard} />
            </Panel>

            <Panel icon={GitBranch} title="检查点" count={checkpoints.length}>
              <CheckpointTrack
                checkpoints={checkpoints}
                loading={loadingCheckpoints}
                onRestore={handleRestore}
                restoringId={restoringId}
              />
            </Panel>

            <Panel icon={Clock} title="工具调用留痕" count={invocations.length}>
              <InvocationTable invocations={invocations} loading={loadingInvocations} />
            </Panel>
          </div>
        )}
      </div>
    </section>
  );
}

/** 区块外壳：标题 + 计数徽标。运维界面用统一外壳，不做卡片套卡片。 */
function Panel({
  icon: Icon,
  title,
  count,
  children,
}: {
  icon: typeof Activity;
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <div className={`shrink-0 rounded-xl ${workspaceSurface.panel}`}>
      <header className="flex items-center gap-2 border-b border-(--line) px-3 py-2.5">
        <Icon size={15} aria-hidden="true" className="text-(--text-4)" />
        <h3 className={`text-sm ${workspaceText.heading}`}>{title}</h3>
        <span className="rounded-full border border-(--line) bg-(--fill-2) px-2 py-0.5 text-[11px] text-(--text-4)">
          {count}
        </span>
      </header>
      <div className="px-3 py-2.5">{children}</div>
    </div>
  );
}

/** 单个指标格。数字用等宽字体，方便纵向对比。 */
function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-(--line) bg-(--fill-1) px-2.5 py-2">
      <div className="text-[11px] text-(--text-5)">{label}</div>
      <div className="mt-1 font-mono text-sm text-(--text-2)">{value}</div>
    </div>
  );
}

/**
 * 任务头部：目标、门禁结论、以及五个长程任务真正关心的指标。
 *
 * 指标的选择是有取舍的：不放"创建时间"这类查一下就知道的东西，放的是
 * 「跑了多久、走了多少步、调了多少次工具、失败几次、下一步是什么」——
 * 一个任务跑了三小时之后，人最想知道的就是这五个。
 */
function TaskHeader({
  task,
  trace,
  board,
}: {
  task: TaskState;
  trace: ReturnType<typeof buildRunTrace>;
  board: TodoBoard | null;
}) {
  const percent = board ? board.progress.percent : null;
  return (
    <div className={`shrink-0 rounded-xl ${workspaceSurface.panel}`}>
      <div className="flex flex-wrap items-start gap-x-3 gap-y-2 border-b border-(--line) px-3 py-2.5">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h2 className={`truncate text-sm ${workspaceText.heading}`}>{task.title}</h2>
            <span
              className={`shrink-0 rounded border bg-(--fill-1) px-1.5 py-0.5 text-[10px] ${statusTone(task.status)}`}
            >
              {task.status}
            </span>
          </div>
          <p className="mt-1 line-clamp-2 text-xs leading-5 text-(--text-4)">{task.goal}</p>
        </div>
        <span
          className="shrink-0 font-mono text-[11px] text-(--text-5)"
          title={`state_hash ${task.state_hash}`}
        >
          v{task.version} · {task.state_hash.slice(0, 10)}
        </span>
      </div>

      {trace.blockedReason ? (
        <div className="flex items-start gap-2 border-b border-(--line) bg-amber-500/5 px-3 py-2">
          <AlertTriangle
            size={14}
            aria-hidden="true"
            className="mt-0.5 shrink-0 text-(--warn-text)"
          />
          <p className="text-xs leading-5 text-(--warn-text)">{trace.blockedReason}</p>
        </div>
      ) : null}

      <div className="grid grid-cols-5 gap-2 px-3 py-2.5 max-md:grid-cols-3 max-sm:grid-cols-2">
        <Metric label="已运行" value={formatDuration(trace.elapsedMs)} />
        <Metric label="步骤" value={String(trace.stepCount)} />
        <Metric label="工具调用" value={String(trace.toolCount)} />
        <Metric label="失败" value={String(trace.failureCount)} />
        <Metric
          label="清单进度"
          value={percent === null ? "—" : `${percent.toFixed(0)}%`}
        />
      </div>

      {trace.gates.length > 0 ? (
        <div className="flex flex-wrap items-center gap-2 border-t border-(--line) px-3 py-2.5">
          <span className="text-[11px] text-(--text-5)">门禁链</span>
          {trace.gates.map((gate, index) => (
            <span
              className={`flex items-center gap-1 rounded border bg-(--fill-1) px-1.5 py-0.5 text-[11px] ${
                gate.verdict === "passed"
                  ? "border-emerald-400/40 text-emerald-300"
                  : gate.verdict === "failed"
                    ? "border-red-400/40 text-red-300"
                    : "border-(--line) text-(--text-5)"
              }`}
              key={`${gate.stage}-${index}`}
              title={gate.detail || undefined}
            >
              {gate.verdict === "passed" ? (
                <CircleCheck size={10} aria-hidden="true" />
              ) : null}
              {gate.stage}
            </span>
          ))}
        </div>
      ) : null}

      {board?.next_runnable ? (
        <div className="flex items-center gap-2 border-t border-(--line) px-3 py-2.5">
          <span className="shrink-0 text-[11px] text-(--text-5)">下一步</span>
          <span className="min-w-0 flex-1 truncate text-xs text-(--text-3)">
            {board.next_runnable.title}
          </span>
          {board.next_runnable.verify_command ? (
            <code className="shrink-0 rounded border border-(--line) bg-(--fill-2) px-1.5 py-0.5 font-mono text-[10px] text-(--text-4)">
              {board.next_runnable.verify_command}
            </code>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
