import {
  ArrowClockwise,
  CaretDown,
  CaretUp,
  Check,
  CheckCircle,
  Clock,
  ListDashes,
  Pause,
  Play,
  Warning,
} from "@phosphor-icons/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Dispatch, RefObject, SetStateAction } from "react";
import { atlasRequest } from "../api";
import { InlineNotice, ThemeSelect, formatTimestamp } from "../components";
import type {
  ApiState,
  Checkpoint,
  CheckpointList,
  CheckpointRestoreResult,
  CheckpointView,
  TaskState,
  TaskStateList,
  Theme,
} from "../types";

function mapCheckpoint(checkpoint: Checkpoint, index: number): CheckpointView {
  const createdAt = new Date(checkpoint.created_at);
  const valid = Boolean(checkpoint.validator_report?.valid);
  return {
    id: `CP-${String(index + 1).padStart(3, "0")}`,
    rawId: checkpoint.id,
    title: checkpoint.kind === "incremental" ? "增量检查点" : `检查点 · ${checkpoint.kind}`,
    description: valid ? "状态哈希与证据范围已通过校验" : "检查点校验未通过",
    time: Number.isNaN(createdAt.valueOf())
      ? "--:--"
      : createdAt.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }),
    state: valid ? "done" : "pending",
    eventRange: `${checkpoint.covered_event_start}–${checkpoint.covered_event_end}`,
    stateHash: String(checkpoint.state_hash || "").replace("sha256:", "").slice(0, 16),
  };
}

function taskStatusLabel(status: string): string {
  if (status === "running") return "进行中";
  if (status === "paused") return "已暂停";
  if (status === "done") return "已完成";
  if (status === "failed") return "已失败";
  return status || "待启动";
}

interface TasksViewProps {
  theme: Theme;
  setTheme: Dispatch<SetStateAction<Theme>>;
  onApiState: (state: ApiState) => void;
}

export function TasksView({ theme, setTheme, onApiState }: TasksViewProps) {
  const [tasks, setTasks] = useState<TaskState[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [checkpoints, setCheckpoints] = useState<CheckpointView[]>([]);
  const [activeCheckpoint, setActiveCheckpoint] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);
  const [command, setCommand] = useState("");
  const [notice, setNotice] = useState("");
  const [noticeTone, setNoticeTone] = useState<"info" | "danger">("info");
  const [submitting, setSubmitting] = useState(false);
  const composerRef = useRef<HTMLInputElement>(null);
  const selectedTaskIdRef = useRef<string | null>(null);
  selectedTaskIdRef.current = selectedTaskId;

  const task = useMemo(
    () => tasks.find((item) => item.id === selectedTaskId) || null,
    [tasks, selectedTaskId],
  );
  const paused = task?.status === "paused";

  const report = useCallback((message: string, tone: "info" | "danger" = "info") => {
    setNotice(message);
    setNoticeTone(tone);
  }, []);

  const refreshTasks = useCallback(async () => {
    setLoading(true);
    try {
      const data = await atlasRequest<TaskStateList>(
        "/api/control-plane/tasks?project_id=default&limit=20",
      );
      setTasks(data.items || []);
      setOffline(false);
      onApiState("connected");
      setSelectedTaskId((current) => {
        if (current && (data.items || []).some((item) => item.id === current)) return current;
        return data.items?.[0]?.id ?? null;
      });
    } catch (error) {
      setOffline(true);
      onApiState("offline");
      report(error instanceof Error ? error.message : "无法连接控制平面", "danger");
    } finally {
      setLoading(false);
    }
  }, [onApiState, report]);

  const loadCheckpoints = useCallback(async (taskId: string) => {
    try {
      const data = await atlasRequest<CheckpointList>(
        `/api/control-plane/tasks/${taskId}/checkpoints`,
      );
      if (selectedTaskIdRef.current !== taskId) return;
      const mapped = (data.items || []).map((checkpoint, index) =>
        mapCheckpoint(checkpoint, index),
      );
      setCheckpoints(mapped);
      setActiveCheckpoint(mapped[mapped.length - 1]?.id ?? null);
    } catch {
      if (selectedTaskIdRef.current === taskId) {
        setCheckpoints([]);
        setActiveCheckpoint(null);
      }
    }
  }, []);

  useEffect(() => {
    void refreshTasks();
  }, [refreshTasks]);

  useEffect(() => {
    setCheckpoints([]);
    setActiveCheckpoint(null);
    if (selectedTaskId) void loadCheckpoints(selectedTaskId);
  }, [selectedTaskId, loadCheckpoints]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        composerRef.current?.focus();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const active = useMemo(
    () => checkpoints.find((checkpoint) => checkpoint.id === activeCheckpoint) || null,
    [activeCheckpoint, checkpoints],
  );

  function applySuggestion(value: string) {
    setCommand(value);
    window.requestAnimationFrame(() => composerRef.current?.focus());
  }

  async function submitCommand() {
    const clean = command.trim();
    if (!clean || submitting) return;
    if (!task) {
      report("当前没有可操作的任务，请先在控制平面创建任务。", "danger");
      return;
    }
    setSubmitting(true);
    try {
      const nextActions = [...(task.next_actions || []), { text: clean, source: "desktop" }];
      const updated = await atlasRequest<TaskState>(`/api/control-plane/tasks/${task.id}`, {
        method: "PATCH",
        body: { expected_version: task.version, next_actions: nextActions },
      });
      setTasks((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      report("命令已写入控制平面的下一步动作。");
      setCommand("");
    } catch (error) {
      report(error instanceof Error ? error.message : "提交失败", "danger");
    } finally {
      setSubmitting(false);
    }
  }

  async function togglePaused() {
    if (!task) {
      report("当前没有可操作的任务。", "danger");
      return;
    }
    const nextPaused = !paused;
    try {
      const updated = await atlasRequest<TaskState>(`/api/control-plane/tasks/${task.id}`, {
        method: "PATCH",
        body: { expected_version: task.version, status: nextPaused ? "paused" : "running" },
      });
      setTasks((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      report(nextPaused ? "任务已在控制平面暂停。" : "任务已在控制平面继续。");
    } catch (error) {
      report(error instanceof Error ? error.message : "状态更新失败", "danger");
    }
  }

  async function restoreCheckpoint(checkpoint: CheckpointView) {
    if (!task || !checkpoint.rawId) return;
    try {
      const restored = await atlasRequest<CheckpointRestoreResult>(
        `/api/control-plane/tasks/${task.id}/checkpoints/${checkpoint.rawId}/restore`,
        { method: "POST", body: { expected_version: task.version, resume: false } },
      );
      setTasks((current) =>
        current.map((item) => (item.id === restored.task.id ? restored.task : item)),
      );
      report(`已恢复到 ${checkpoint.id}，任务保持暂停等待确认。`);
    } catch (error) {
      report(error instanceof Error ? error.message : "恢复失败", "danger");
    }
  }

  const pendingActions = (task?.next_actions || [])
    .map((action) => String((action as Record<string, unknown>).text ?? ""))
    .filter(Boolean)
    .slice(-3)
    .reverse();

  return (
    <>
      <aside className="task-sidebar" aria-label="任务与检查点">
        <div className="sidebar-title-row">
          <h2>任务</h2>
          <div>
            <button
              className="icon-button"
              type="button"
              aria-label="刷新任务"
              onClick={() => void refreshTasks()}
            >
              <ArrowClockwise size={18} className={loading ? "spin" : undefined} />
            </button>
          </div>
        </div>
        <div className="task-list-scroll">
          {tasks.length === 0 && !loading ? (
            <p className="empty-hint sidebar-empty">
              {offline
                ? "未连接控制平面。"
                : "还没有任务。通过对话或控制平面 API 创建任务后，会显示在这里。"}
            </p>
          ) : null}
          {tasks.map((item) => (
            <button
              key={item.id}
              className={`selected-task ${item.id === selectedTaskId ? "current" : ""}`}
              type="button"
              onClick={() => setSelectedTaskId(item.id)}
            >
              <span className="task-dot" />
              <span>
                <strong>{item.title}</strong>
                <small>
                  {taskStatusLabel(item.status)} · 更新于 {formatTimestamp(item.updated_at)}
                </small>
              </span>
            </button>
          ))}
        </div>
        <div className="checkpoint-list">
          {checkpoints.length === 0 ? (
            <p className="empty-hint sidebar-empty">
              {task ? "该任务还没有检查点。" : ""}
            </p>
          ) : (
            checkpoints.map((checkpoint) => (
              <button
                key={checkpoint.id}
                className={`checkpoint-nav ${activeCheckpoint === checkpoint.id ? "selected" : ""}`}
                type="button"
                onClick={() => setActiveCheckpoint(checkpoint.id)}
              >
                <span className={`nav-node ${checkpoint.state}`}>
                  {checkpoint.state === "done" ? <Check size={10} weight="bold" /> : null}
                </span>
                <span>
                  <strong>{checkpoint.id} · {checkpoint.title}</strong>
                  <small>
                    {checkpoint.state === "done" ? "已验证" : "未通过校验"} · {checkpoint.time}
                  </small>
                </span>
              </button>
            ))
          )}
        </div>
      </aside>
      <section className="task-workspace" aria-label="任务执行工作区">
        <header className="task-header">
          <div className="task-heading">
            <h1>{task?.title || (offline ? "未连接控制平面" : "还没有任务")}</h1>
            <div className="task-meta">
              {task ? (
                <>
                  <span className="live-status">
                    <span className="status-pulse" />
                    {taskStatusLabel(task.status)}
                  </span>
                  <span>更新于 {formatTimestamp(task.updated_at)}</span>
                  <span>项目 {task.project_id}</span>
                  <span>版本 v{task.version}</span>
                </>
              ) : (
                <span>
                  {offline
                    ? "请先启动后端服务（scripts/start.sh 或本地开发模式）"
                    : "使用对话或 POST /api/control-plane/tasks 创建第一个任务"}
                </span>
              )}
            </div>
          </div>
          <div className="header-actions">
            <ThemeSelect theme={theme} onChange={setTheme} />
            {task ? (
              <button className="outline-button" type="button" onClick={togglePaused}>
                {paused ? <Play size={18} weight="fill" /> : <Pause size={18} weight="fill" />}
                {paused ? "继续任务" : "暂停任务"}
              </button>
            ) : null}
          </div>
        </header>

        <InlineNotice notice={notice} tone={noticeTone} />

        <div className="timeline-scroll">
          {offline ? (
            <div className="workspace-empty">
              <Warning size={38} weight="duotone" />
              <h2>未连接控制平面</h2>
              <p>
                桌面端不展示演示数据。请先启动后端（默认 <code>http://127.0.0.1:8088</code>），
                然后点击左上角刷新按钮重试。
              </p>
              <button className="outline-button" type="button" onClick={() => void refreshTasks()}>
                <ArrowClockwise size={16} /> 重新连接
              </button>
            </div>
          ) : null}
          {!offline && !loading && !task ? (
            <div className="workspace-empty">
              <ListDashes size={38} weight="duotone" />
              <h2>控制平面里还没有任务</h2>
              <p>
                在「对话」里下达一个包含执行意图的指令，或调用
                <code>POST /api/control-plane/tasks</code> 创建结构化任务后，
                这里会展示任务的检查点时间线。
              </p>
            </div>
          ) : null}
          {task && checkpoints.length === 0 && !offline ? (
            <div className="workspace-empty">
              <Clock size={38} weight="duotone" />
              <h2>该任务还没有检查点</h2>
              <p>
                任务执行过程中调用
                <code>POST /api/control-plane/tasks/{"{task_id}"}/checkpoints</code>
                后，可验证的恢复点会出现在这条时间线上。
              </p>
            </div>
          ) : null}
          <div className="timeline" aria-label="检查点时间线">
            {checkpoints.map((checkpoint) => (
              <TimelineCheckpoint
                key={checkpoint.id}
                checkpoint={checkpoint}
                expanded={checkpoint.id === active?.id}
                mustPreserve={task?.must_preserve?.[0] || ""}
                pendingActions={pendingActions}
                onToggle={() => setActiveCheckpoint(checkpoint.id)}
                onRestore={() => restoreCheckpoint(checkpoint)}
              />
            ))}
          </div>
        </div>

        <CommandComposer
          command={command}
          inputRef={composerRef}
          disabled={!task || submitting}
          onChange={setCommand}
          onSubmit={submitCommand}
          onSuggestion={applySuggestion}
          submitting={submitting}
        />
      </section>
    </>
  );
}

interface TimelineCheckpointProps {
  checkpoint: CheckpointView;
  expanded: boolean;
  mustPreserve: string;
  pendingActions: string[];
  onToggle: () => void;
  onRestore: () => void | Promise<void>;
}

function TimelineCheckpoint({
  checkpoint,
  expanded,
  mustPreserve,
  pendingActions,
  onToggle,
  onRestore,
}: TimelineCheckpointProps) {
  const isDone = checkpoint.state === "done";
  return (
    <article className={`timeline-item ${expanded ? "expanded" : ""}`}>
      <time>{checkpoint.time}</time>
      <span className={`timeline-node ${checkpoint.state}`}>
        {isDone ? <CheckCircle size={24} weight="duotone" /> : <Clock size={22} />}
      </span>
      <div className="timeline-content">
        <button className="timeline-summary" type="button" onClick={onToggle} aria-expanded={expanded}>
          <span>
            <strong>{checkpoint.id} · {checkpoint.title}</strong>
            <small>{checkpoint.description}</small>
          </span>
          <span className="summary-status">
            <span>事件 {checkpoint.eventRange}</span>
            {isDone ? (
              <span className="verified">已验证，可恢复</span>
            ) : (
              <span>校验未通过</span>
            )}
            {expanded ? <CaretUp size={16} /> : <CaretDown size={16} />}
          </span>
        </button>
        {expanded ? (
          <div className="checkpoint-card">
            <div className="checkpoint-evidence">
              {mustPreserve ? (
                <div className="detail-block">
                  <span>保留的需求</span>
                  <strong>{mustPreserve}</strong>
                </div>
              ) : null}
              <div className="detail-block">
                <span>事件覆盖</span>
                <strong>事件 {checkpoint.eventRange}</strong>
              </div>
              <div className="detail-block">
                <span>状态摘要</span>
                {isDone ? (
                  <strong className="verified">
                    <CheckCircle size={17} weight="fill" /> 已验证，可恢复
                  </strong>
                ) : (
                  <strong>校验未通过，恢复前请先检查任务状态</strong>
                )}
              </div>
            </div>
            <div className="checkpoint-actions">
              {checkpoint.stateHash ? (
                <div className="state-hash">
                  <span>状态哈希</span>
                  <code>{checkpoint.stateHash}</code>
                </div>
              ) : null}
              {pendingActions.length ? (
                <div className="next-action">
                  <span>待执行动作（来自控制平面）</span>
                  <ul className="pending-actions">
                    {pendingActions.map((action, index) => (
                      <li key={`${action}-${index}`}>{action}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              <button className="outline-button" type="button" onClick={onRestore}>
                恢复到此检查点
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </article>
  );
}

interface CommandComposerProps {
  command: string;
  inputRef: RefObject<HTMLInputElement | null>;
  disabled: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void | Promise<void>;
  onSuggestion: (value: string) => void;
  submitting: boolean;
}

function CommandComposer({
  command,
  inputRef,
  disabled,
  onChange,
  onSubmit,
  onSuggestion,
  submitting,
}: CommandComposerProps) {
  return (
    <div className="composer-wrap">
      <div className="composer">
        <label className="agent-picker">AtlasAgent <CaretDown size={15} /></label>
        <input
          ref={inputRef}
          value={command}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) void onSubmit();
          }}
          placeholder="把下一步动作写入当前任务（Ctrl/⌘+K 聚焦）"
          aria-label="向当前任务写入下一步动作"
          disabled={disabled && !submitting}
        />
        <kbd>⌘K</kbd>
        <button
          className="send-button"
          type="button"
          onClick={() => void onSubmit()}
          disabled={!command.trim() || disabled}
          aria-label="写入下一步动作"
        >
          {submitting ? <ArrowClockwise className="spin" size={19} /> : <Play size={19} weight="fill" />}
        </button>
        <div className="suggestions">
          <span>快捷填充：</span>
          <button type="button" onClick={() => onSuggestion("继续执行当前检查点")}>继续执行</button>
          <button type="button" onClick={() => onSuggestion("总结当前进度、风险与下一步")}>总结进度</button>
          <button type="button" onClick={() => onSuggestion("回滚到上一个已验证检查点并说明原因")}>回滚检查点</button>
        </div>
      </div>
    </div>
  );
}
