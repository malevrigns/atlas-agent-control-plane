"use client";

import { CircleCheck, CircleSlash, History, Loader2, RotateCcw } from "lucide-react";

import { formatDateTime } from "../../lib/format";
import type { Checkpoint } from "../../lib/control-plane-api";
import { workspaceSurface } from "../../lib/design-tokens";

type CheckpointTrackProps = {
  checkpoints: Checkpoint[];
  loading: boolean;
  restoringId: string | null;
  onRestore: (checkpoint: Checkpoint, resume: boolean) => void;
};

/** validator_report 里没有统一字段名，这里只判断"有没有报告、报告说没通过"。 */
function reportVerdict(report: Record<string, unknown>): "passed" | "failed" | "unknown" {
  if (!report || Object.keys(report).length === 0) {
    return "unknown";
  }
  const passed = report.passed ?? report.ok ?? report.valid;
  if (passed === true) {
    return "passed";
  }
  if (passed === false) {
    return "failed";
  }
  return "unknown";
}

/**
 * 检查点轨道：一条竖线串起父子链，每个节点标出它覆盖的事件区间。
 *
 * 长程任务的价值就在这里——第 38 步崩了，不用从头再来，挑一个检查点回滚。
 * 所以"覆盖了哪段事件"必须显式可见，否则用户没法判断该回到哪个点。
 */
export function CheckpointTrack({
  checkpoints,
  loading,
  restoringId,
  onRestore,
}: CheckpointTrackProps) {
  if (loading) {
    return (
      <div className="flex items-center gap-2 px-1 py-6 text-sm text-(--text-4)">
        <Loader2 className="animate-spin" size={15} aria-hidden="true" />
        读取检查点…
      </div>
    );
  }

  if (checkpoints.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-(--line) px-4 py-6 text-sm text-(--text-4)">
        还没有检查点。任务执行中会按事件区间落点，届时可从任意一点恢复。
      </div>
    );
  }

  // 后端按时间倒序返回，这里正序展示，读起来才是"从头跑到哪"。
  const ordered = [...checkpoints].sort(
    (left, right) => left.covered_event_start - right.covered_event_start,
  );

  return (
    <ol className="relative flex flex-col gap-2 pl-6">
      {/* 轨道竖线：绝对定位在节点圆心，父子链一眼看得出是一条链。 */}
      <span
        aria-hidden="true"
        className="absolute bottom-3 left-[9px] top-3 w-px bg-(--line)"
      />
      {ordered.map((checkpoint) => {
        const verdict = reportVerdict(checkpoint.validator_report);
        const restoring = restoringId === checkpoint.id;
        return (
          <li className="relative" key={checkpoint.id}>
            <span
              aria-hidden="true"
              className={`absolute -left-6 top-3.5 flex h-[19px] w-[19px] items-center justify-center rounded-full border-2 ${
                verdict === "failed"
                  ? "border-red-400/60 bg-(--surface) text-(--error-text)"
                  : "border-(--accent)/60 bg-(--surface) text-(--accent)"
              }`}
            >
              {verdict === "failed" ? (
                <CircleSlash size={11} aria-hidden="true" />
              ) : (
                <CircleCheck size={11} aria-hidden="true" />
              )}
            </span>
            <div
              className={`flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg px-3 py-2.5 ${workspaceSurface.panel}`}
            >
              <span className="font-mono text-xs text-(--text-3)">
                事件 {checkpoint.covered_event_start}–{checkpoint.covered_event_end}
              </span>
              <span className="rounded border border-(--line) bg-(--fill-2) px-1.5 py-0.5 text-[11px] text-(--text-4)">
                {checkpoint.kind === "full" ? "全量" : "增量"}
              </span>
              <span
                className="font-mono text-[11px] text-(--text-5)"
                title={`state_hash ${checkpoint.state_hash}`}
              >
                {checkpoint.state_hash.slice(0, 10)}
              </span>
              {verdict === "failed" ? (
                <span className="rounded border border-red-400/40 bg-red-500/10 px-1.5 py-0.5 text-[11px] text-(--error-text)">
                  校验未通过
                </span>
              ) : null}
              <span className="ml-auto text-xs text-(--text-5)">
                {formatDateTime(checkpoint.created_at)}
              </span>
              <div className="flex items-center gap-1.5">
                <button
                  aria-label="回滚到此检查点"
                  className="flex h-8 w-8 items-center justify-center rounded-md border border-(--line) bg-(--fill-1) text-(--text-4) transition hover:bg-(--fill-2) hover:text-(--text-1) disabled:cursor-not-allowed disabled:text-(--text-5)"
                  disabled={restoring}
                  onClick={() => onRestore(checkpoint, false)}
                  title="回滚到此检查点"
                  type="button"
                >
                  {restoring ? (
                    <Loader2 className="animate-spin" size={14} aria-hidden="true" />
                  ) : (
                    <RotateCcw size={14} aria-hidden="true" />
                  )}
                </button>
                <button
                  aria-label="回滚并继续执行"
                  className="flex h-8 w-8 items-center justify-center rounded-md border border-(--line) bg-(--fill-1) text-(--text-4) transition hover:bg-(--fill-2) hover:text-(--text-1) disabled:cursor-not-allowed disabled:text-(--text-5)"
                  disabled={restoring}
                  onClick={() => onRestore(checkpoint, true)}
                  title="回滚并继续执行"
                  type="button"
                >
                  <History size={14} aria-hidden="true" />
                </button>
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
