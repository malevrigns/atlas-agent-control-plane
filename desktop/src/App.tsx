import "@fontsource-variable/inter";
import {
  ArrowClockwise,
  CaretDown,
  CaretUp,
  Check,
  CheckCircle,
  CirclesFour,
  Clock,
  Cube,
  DotsThree,
  Funnel,
  Gear,
  GitBranch,
  ListChecks,
  Pause,
  Play,
  Plus,
  PuzzlePiece,
  RocketLaunch,
  TerminalWindow,
} from "@phosphor-icons/react";
import type { Icon } from "@phosphor-icons/react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Dispatch, RefObject, SetStateAction } from "react";
import type {
  ApiEnvelope,
  ApiState,
  AtlasRequestOptions,
  Checkpoint,
  CheckpointList,
  CheckpointRestoreResult,
  CheckpointView,
  TaskState,
  TaskStateList,
  Theme,
  ToolPolicy,
} from "./types";

const API_BASE = import.meta.env.VITE_ATLAS_API_BASE || "http://localhost:8088";

const demoCheckpoints: CheckpointView[] = [
  {
    id: "CP-001",
    title: "需求梳理与边界对齐",
    description: "对齐重构目标、非目标与验收标准",
    time: "10:12",
    state: "done",
    eventRange: "1–48",
  },
  {
    id: "CP-002",
    title: "记忆模型重构",
    description: "设计新版记忆结构与检索策略",
    time: "10:47",
    state: "done",
    eventRange: "49–116",
  },
  {
    id: "CP-003",
    title: "Memory 层实现与迁移",
    description: "实现记忆层并完成数据迁移与回归验证",
    time: "11:38",
    state: "done",
    eventRange: "117–181",
  },
  {
    id: "CP-004",
    title: "工具运行时接入",
    description: "接入工具运行时并校验授权与兼容性",
    time: "12:28",
    state: "running",
    eventRange: "182–236",
  },
  {
    id: "CP-005",
    title: "端到端验证",
    description: "端到端流程验证与性能回归",
    time: "13:05",
    state: "pending",
    eventRange: "待生成",
  },
];

async function atlasRequest<T>(path: string, options: AtlasRequestOptions = {}): Promise<T> {
  if (window.atlasDesktop?.request) {
    return window.atlasDesktop.request<T>(path, options);
  }
  const response = await fetch(`${API_BASE}${path}`, {
    method: options.method || "GET",
    headers: options.body ? { "Content-Type": "application/json" } : undefined,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const payload = (await response.json()) as ApiEnvelope<T>;
  if (!response.ok || Number(payload.code ?? response.status) >= 400) {
    throw new Error(payload.message || `Atlas API returned ${response.status}`);
  }
  if (payload.data === undefined) {
    throw new Error("Atlas API returned an empty response");
  }
  return payload.data;
}

function mapCheckpoint(checkpoint: Checkpoint, task: TaskState, index: number): CheckpointView {
  const createdAt = new Date(checkpoint.created_at);
  const valid = Boolean(checkpoint.validator_report?.valid);
  return {
    id: `CP-${String(index + 1).padStart(3, "0")}`,
    rawId: checkpoint.id,
    title: checkpoint.kind === "incremental" ? task.title : `${task.title} · ${checkpoint.kind}`,
    description: valid ? "状态哈希与证据范围已通过校验" : "检查点校验未通过",
    time: Number.isNaN(createdAt.valueOf())
      ? "--:--"
      : createdAt.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }),
    state: valid ? "done" : "pending",
    eventRange: `${checkpoint.covered_event_start}–${checkpoint.covered_event_end}`,
    stateHash: String(checkpoint.state_hash || "").replace("sha256:", "").slice(0, 16),
  };
}

function formatTimestamp(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? "时间未知"
    : date.toLocaleString("zh-CN", { hour12: false });
}

const themeOptions: Array<{ value: Theme; label: string }> = [
  { value: "ink", label: "墨夜" },
  { value: "dawn", label: "晨光" },
  { value: "contrast", label: "高对比" },
];

function isTheme(value: string | null): value is Theme {
  return value === "ink" || value === "dawn" || value === "contrast";
}

function useTheme(): [Theme, Dispatch<SetStateAction<Theme>>] {
  const [theme, setTheme] = useState<Theme>(() => {
    const savedTheme = localStorage.getItem("atlas-theme");
    return isTheme(savedTheme) ? savedTheme : "ink";
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("atlas-theme", theme);
  }, [theme]);
  return [theme, setTheme];
}

interface IconRailProps {
  apiState: ApiState;
}

interface TaskSidebarProps {
  activeCheckpoint: string;
  completedCollapsed: boolean;
  onCollapseCompleted: () => void;
  onSelectCheckpoint: (checkpointId: string) => void;
  checkpoints: CheckpointView[];
}

interface TimelineCheckpointProps {
  checkpoint: CheckpointView;
  expanded: boolean;
  onToggle: () => void;
  toolPolicy: ToolPolicy;
  onToolPolicyChange: (policy: ToolPolicy) => void;
  onRun: () => void;
  onRestore: () => void | Promise<void>;
}

interface DetailProps {
  label: string;
  value: string;
}

interface CommandComposerProps {
  command: string;
  inputRef: RefObject<HTMLInputElement | null>;
  notice: string;
  onChange: (value: string) => void;
  onSubmit: () => void | Promise<void>;
  onSuggestion: (value: string) => void;
  submitting: boolean;
}

export function App() {
  const [theme, setTheme] = useTheme();
  const [activeCheckpoint, setActiveCheckpoint] = useState("CP-004");
  const [paused, setPaused] = useState(false);
  const [completedCollapsed, setCompletedCollapsed] = useState(false);
  const [command, setCommand] = useState("");
  const [toolPolicy, setToolPolicy] = useState<ToolPolicy>("自动允许");
  const [notice, setNotice] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [apiState, setApiState] = useState<ApiState>("checking");
  const [task, setTask] = useState<TaskState | null>(null);
  const [checkpoints, setCheckpoints] = useState<CheckpointView[]>(demoCheckpoints);
  const composerRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let disposed = false;
    atlasRequest<TaskStateList>("/api/control-plane/tasks?project_id=default&limit=1")
      .then(async (data) => {
        const liveTask = data?.items?.[0];
        if (!liveTask || disposed) throw new Error("no task");
        const checkpointData = await atlasRequest<CheckpointList>(`/api/control-plane/tasks/${liveTask.id}/checkpoints`);
        if (disposed) return;
        const liveCheckpoints = (checkpointData?.items || []).map((checkpoint, index) => mapCheckpoint(checkpoint, liveTask, index));
        setTask(liveTask);
        setPaused(liveTask.status === "paused");
        if (liveCheckpoints.length) {
          setCheckpoints(liveCheckpoints);
          setActiveCheckpoint(liveCheckpoints[0].id);
        }
        setApiState("connected");
      })
      .catch(() => {
        if (!disposed) setApiState("offline");
      });
    return () => {
      disposed = true;
    };
  }, []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        composerRef.current?.focus();
      }
      if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
        event.preventDefault();
        submitCommand();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  });

  const active = useMemo(
    () => checkpoints.find((checkpoint) => checkpoint.id === activeCheckpoint) || checkpoints[0],
    [activeCheckpoint, checkpoints],
  );

  function applySuggestion(value: string) {
    setCommand(value);
    window.requestAnimationFrame(() => composerRef.current?.focus());
  }

  async function submitCommand() {
    const clean = command.trim();
    if (!clean || submitting) return;
    setSubmitting(true);
    try {
      if (!task) throw new Error("当前是离线演示数据，无法提交");
      const nextActions = [...(task.next_actions || []), { text: clean, source: "desktop" }];
      const updated = await atlasRequest<TaskState>(`/api/control-plane/tasks/${task.id}`, {
        method: "PATCH",
        body: { expected_version: task.version, next_actions: nextActions },
      });
      setTask(updated);
      setNotice("命令已写入控制平面的下一步动作。");
      setSubmitting(false);
      setCommand("");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "提交失败");
      setSubmitting(false);
    }
  }

  async function togglePaused() {
    if (!task) {
      setNotice("当前是离线演示数据，无法修改任务状态。");
      return;
    }
    const nextPaused = !paused;
    try {
      const updated = await atlasRequest<TaskState>(`/api/control-plane/tasks/${task.id}`, {
        method: "PATCH",
        body: { expected_version: task.version, status: nextPaused ? "paused" : "running" },
      });
      setTask(updated);
      setPaused(nextPaused);
      setNotice(nextPaused ? "任务已在控制平面暂停。" : "任务已在控制平面继续。");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "状态更新失败");
    }
  }

  async function restoreCheckpoint(checkpoint: CheckpointView) {
    if (!task || !checkpoint.rawId) {
      setNotice("离线演示数据不能执行恢复。");
      return;
    }
    try {
      const restored = await atlasRequest<CheckpointRestoreResult>(
        `/api/control-plane/tasks/${task.id}/checkpoints/${checkpoint.rawId}/restore`,
        { method: "POST", body: { expected_version: task.version, resume: false } },
      );
      setTask(restored.task);
      setPaused(true);
      setNotice(`已恢复到 ${checkpoint.id}，任务保持暂停等待确认。`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "恢复失败");
    }
  }

  return (
    <main className="atlas-shell">
      <IconRail apiState={apiState} />
      <TaskSidebar
        activeCheckpoint={activeCheckpoint}
        completedCollapsed={completedCollapsed}
        onCollapseCompleted={() => setCompletedCollapsed((value) => !value)}
        onSelectCheckpoint={setActiveCheckpoint}
        checkpoints={checkpoints}
      />
      <section className="task-workspace" aria-label="任务执行工作区">
        <header className="task-header">
          <div className="task-heading">
            <h1>{task?.title || "重构 Agent Memory 与 Tool Runtime"}</h1>
            <div className="task-meta">
              <span className="live-status"><span className="status-pulse" />{paused ? "已暂停" : "进行中"}</span>
              <span>{task ? `更新于 ${formatTimestamp(task.updated_at)}` : "离线演示数据"}</span>
              <span>项目 {task?.project_id || "default"}</span>
              <span>{task ? `版本 v${task.version}` : "未连接控制平面"}</span>
            </div>
          </div>
          <div className="header-actions">
            <label className="theme-control">
              <CirclesFour size={17} weight="regular" aria-hidden="true" />
              <span className="sr-only">选择主题</span>
              <select value={theme} onChange={(event) => setTheme(event.target.value as Theme)} aria-label="选择界面主题">
                {themeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
            <button className="outline-button" type="button" onClick={togglePaused}>
              {paused ? <Play size={18} weight="fill" /> : <Pause size={18} weight="fill" />}
              {paused ? "继续任务" : "暂停任务"}
            </button>
            <button className="icon-button" type="button" aria-label="更多任务操作"><DotsThree size={22} weight="bold" /></button>
          </div>
        </header>

        <div className="timeline-scroll">
          <div className="timeline" aria-label="检查点时间线">
            {checkpoints.map((checkpoint) => (
              <TimelineCheckpoint
                key={checkpoint.id}
                checkpoint={checkpoint}
                expanded={checkpoint.id === active.id}
                onToggle={() => setActiveCheckpoint(checkpoint.id)}
                toolPolicy={toolPolicy}
                onToolPolicyChange={setToolPolicy}
                onRun={() => applySuggestion("运行兼容性测试并将完整输出保存为 Artifact")}
                onRestore={() => restoreCheckpoint(checkpoint)}
              />
            ))}
          </div>
        </div>

        <CommandComposer
          command={command}
          inputRef={composerRef}
          notice={notice}
          onChange={setCommand}
          onSubmit={submitCommand}
          onSuggestion={applySuggestion}
          submitting={submitting}
        />
      </section>
    </main>
  );
}

function IconRail({ apiState }: IconRailProps) {
  const items: Array<[Icon, string, boolean?]> = [
    [Play, "任务", true],
    [ListChecks, "运行记录"],
    [GitBranch, "事件关系"],
    [Cube, "制品"],
    [TerminalWindow, "终端"],
    [PuzzlePiece, "工具"],
    [Gear, "设置"],
  ];
  return (
    <nav className="icon-rail" aria-label="主导航">
      <button className="brand-mark" type="button" aria-label="AtlasAgent 首页"><RocketLaunch size={27} weight="fill" /></button>
      <div className="rail-divider" />
      <div className="rail-items">
        {items.map(([Icon, label, active]) => (
          <button key={label} className={`rail-button ${active ? "active" : ""}`} type="button" aria-label={label} title={label}>
            <Icon size={22} weight={active ? "fill" : "regular"} />
          </button>
        ))}
      </div>
      <div className={`api-indicator ${apiState}`} title={apiState === "connected" ? "API 已连接" : apiState === "offline" ? "演示数据模式" : "正在检测 API"}>
        <span />
      </div>
    </nav>
  );
}

function TaskSidebar({
  activeCheckpoint,
  completedCollapsed,
  onCollapseCompleted,
  onSelectCheckpoint,
  checkpoints,
}: TaskSidebarProps) {
  return (
    <aside className="task-sidebar" aria-label="任务与检查点">
      <div className="sidebar-title-row">
        <h2>任务</h2>
        <div>
          <button className="icon-button" type="button" aria-label="新建任务"><Plus size={20} /></button>
          <button className="icon-button" type="button" aria-label="筛选任务"><Funnel size={19} /></button>
        </div>
      </div>
      <button className="selected-task" type="button">
        <span className="task-dot" />
        <span>
          <strong>重构 Agent Memory 与 Tool Runtime</strong>
          <small>进行中 · 更新于 14:32</small>
        </span>
      </button>
      <div className="checkpoint-list">
        {checkpoints.map((checkpoint) => (
          <button
            key={checkpoint.id}
            className={`checkpoint-nav ${activeCheckpoint === checkpoint.id ? "selected" : ""}`}
            type="button"
            onClick={() => onSelectCheckpoint(checkpoint.id)}
          >
            <span className={`nav-node ${checkpoint.state}`}>
              {checkpoint.state === "done" ? <Check size={10} weight="bold" /> : null}
            </span>
            <span>
              <strong>{checkpoint.id} · {checkpoint.title}</strong>
              <small>{checkpoint.state === "done" ? `已完成 · 08-01 ${checkpoint.time}` : checkpoint.state === "running" ? `进行中 · ${checkpoint.time}` : "等待中"}</small>
            </span>
          </button>
        ))}
      </div>
      <button className="completed-toggle" type="button" onClick={onCollapseCompleted}>
        {completedCollapsed ? <CaretUp size={15} /> : <CaretDown size={15} />}
        {completedCollapsed ? "展开已完成" : "收起已完成"}
      </button>
    </aside>
  );
}

function TimelineCheckpoint({
  checkpoint,
  expanded,
  onToggle,
  toolPolicy,
  onToolPolicyChange,
  onRun,
  onRestore,
}: TimelineCheckpointProps) {
  const isDone = checkpoint.state === "done";
  return (
    <article className={`timeline-item ${expanded ? "expanded" : ""}`}>
      <time>{checkpoint.time}</time>
      <span className={`timeline-node ${checkpoint.state}`}>
        {isDone ? <CheckCircle size={24} weight="duotone" /> : checkpoint.state === "running" ? <Clock size={23} weight="duotone" /> : <Clock size={22} />}
      </span>
      <div className="timeline-content">
        <button className="timeline-summary" type="button" onClick={onToggle} aria-expanded={expanded}>
          <span>
            <strong>{checkpoint.id} · {checkpoint.title}</strong>
            <small>{checkpoint.description}</small>
          </span>
          <span className="summary-status">
            <span>事件 {checkpoint.eventRange}</span>
            {isDone ? <span className="verified">已验证，可恢复</span> : checkpoint.state === "running" ? <span className="verified">已验证，可恢复</span> : <span>预计 08-01 {checkpoint.time}</span>}
            {expanded ? <CaretUp size={16} /> : <CaretDown size={16} />}
          </span>
        </button>
        {expanded ? (
          <div className="checkpoint-card">
            <div className="checkpoint-evidence">
              <Detail label="保留的需求" value="不得把模型推测直接写入长期事实" />
              <Detail label="事件覆盖" value={`事件 ${checkpoint.eventRange}（共 55 条）`} />
              <div className="detail-block">
                <span>状态摘要</span>
                <strong className="verified"><CheckCircle size={17} weight="fill" /> 已验证，可恢复</strong>
                <small>最后验证 2026-08-01 {checkpoint.time}</small>
              </div>
            </div>
            <div className="checkpoint-actions">
              <div className="state-hash">
                <span>状态哈希</span>
                <code>{checkpoint.stateHash || "a7f9c3d8b2e1f4a9"}</code>
              </div>
              <div className="next-action">
                <span>下一步动作（建议）</span>
                <button type="button" onClick={onRun}>
                  <Play size={17} weight="fill" />
                  <span><strong>运行兼容性测试</strong><code>pytest -q tests/compat --maxfail=1</code></span>
                  <em>推荐</em>
                </button>
              </div>
              <button className="outline-button" type="button" onClick={onRestore}>恢复到此检查点</button>
              <label className="tool-policy">
                <span>工具授权</span>
                <span className="policy-select"><TerminalWindow size={18} /> pytest · 低风险 ·
                  <select value={toolPolicy} onChange={(event) => onToolPolicyChange(event.target.value as ToolPolicy)} aria-label="工具授权策略">
                    <option>自动允许</option>
                    <option>每次询问</option>
                    <option>本次拒绝</option>
                  </select>
                </span>
              </label>
            </div>
          </div>
        ) : null}
      </div>
    </article>
  );
}

function Detail({ label, value }: DetailProps) {
  return <div className="detail-block"><span>{label}</span><strong>{value}</strong></div>;
}

function CommandComposer({
  command,
  inputRef,
  notice,
  onChange,
  onSubmit,
  onSuggestion,
  submitting,
}: CommandComposerProps) {
  return (
    <div className="composer-wrap">
      {notice ? <div className="composer-notice" role="status"><CheckCircle size={16} weight="fill" />{notice}</div> : null}
      <div className="composer">
        <label className="agent-picker">AtlasAgent <CaretDown size={15} /></label>
        <input
          ref={inputRef}
          value={command}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) onSubmit();
          }}
          placeholder="输入指令或 @ 选择上下文，支持自然语言或命令"
          aria-label="向 AtlasAgent 发送指令"
        />
        <kbd>⌘K</kbd>
        <button className="send-button" type="button" onClick={onSubmit} disabled={!command.trim() || submitting} aria-label="发送指令">
          {submitting ? <ArrowClockwise className="spin" size={19} /> : <Play size={19} weight="fill" />}
        </button>
        <div className="suggestions">
          <span>建议操作：</span>
          <button type="button" onClick={() => onSuggestion("继续执行当前检查点")}>继续执行</button>
          <button type="button" onClick={() => onSuggestion("回滚到 CP-003 并重新验证")}>回滚到 CP-003</button>
          <button type="button" onClick={() => onSuggestion("跳过当前检查并记录原因")}>跳过当前检查</button>
          <button type="button" onClick={() => onSuggestion("查看 CP-004 的变更和证据")}>查看变更</button>
        </div>
      </div>
    </div>
  );
}
