import { requestApi } from "./api";

// ===================== 控制面类型 =====================

/** 任务进度看板：三列各自是一组条目。 */
export type TaskProgress = {
  done: Array<Record<string, unknown>>;
  doing: Array<Record<string, unknown>>;
  blocked: Array<Record<string, unknown>>;
};

export type TaskState = {
  id: string;
  session_id: string | null;
  project_id: string;
  title: string;
  goal: string;
  acceptance_criteria: string[];
  status: string;
  requirements: Array<Record<string, unknown>>;
  decisions: Array<Record<string, unknown>>;
  progress: TaskProgress;
  known_failures: Array<Record<string, unknown>>;
  open_questions: Array<Record<string, unknown>>;
  next_actions: Array<Record<string, unknown>>;
  must_preserve: string[];
  environment_ref: string | null;
  artifact_refs: string[];
  current_event_seq: number;
  version: number;
  state_hash: string;
  created_at: string;
  updated_at: string;
};

export type Checkpoint = {
  id: string;
  task_id: string;
  parent_checkpoint_id: string | null;
  kind: string;
  covered_event_start: number;
  covered_event_end: number;
  snapshot: Record<string, unknown>;
  state_hash: string;
  validator_report: Record<string, unknown>;
  created_at: string;
};

export type CheckpointRestoreResult = {
  checkpoint_id: string;
  resumed: boolean;
  task: TaskState;
};

export type ToolInvocation = {
  id: string;
  tool_name: string;
  tool_version: string;
  task_id: string | null;
  session_id: string | null;
  project_id: string;
  idempotency_key: string | null;
  request_hash: string;
  risk_level: string;
  permissions: string[];
  decision: string;
  decision_reason: string;
  status: string;
  arguments: Record<string, unknown>;
  output_preview: string;
  artifact_id: string | null;
  error: string | null;
  duration_ms: number | null;
  started_at: string;
  finished_at: string | null;
};

// ===================== 控制面 API =====================

export function fetchControlPlaneTasks(params: {
  projectId?: string;
  limit?: number;
} = {}): Promise<{ items: TaskState[] }> {
  const query = new URLSearchParams();
  query.set("project_id", params.projectId ?? "default");
  if (params.limit) {
    query.set("limit", String(params.limit));
  }
  return requestApi<{ items: TaskState[] }>(`/api/control-plane/tasks?${query.toString()}`);
}

export function fetchControlPlaneTask(taskId: string): Promise<TaskState> {
  return requestApi<TaskState>(`/api/control-plane/tasks/${taskId}`);
}

export function fetchCheckpoints(
  taskId: string,
  limit = 100,
): Promise<{ items: Checkpoint[] }> {
  return requestApi<{ items: Checkpoint[] }>(
    `/api/control-plane/tasks/${taskId}/checkpoints?limit=${limit}`,
  );
}

/** 落一个检查点。事件区间由调用方给出，服务端算 state_hash 与校验报告。 */
export function createCheckpoint(
  taskId: string,
  input: {
    kind?: string;
    parent_checkpoint_id?: string | null;
    covered_event_start: number;
    covered_event_end: number;
  },
): Promise<Checkpoint> {
  return requestApi<Checkpoint>(`/api/control-plane/tasks/${taskId}/checkpoints`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind: "incremental", ...input }),
  });
}

/**
 * 回滚到某个检查点。
 *
 * ``expected_version`` 是乐观锁：读到任务的哪个版本就回填哪个版本，中间被
 * 别人改过就会失败而不是静默覆盖。resume=true 表示回滚后立刻继续执行。
 */
export function restoreCheckpoint(
  taskId: string,
  checkpointId: string,
  input: { expected_version: number; resume: boolean },
): Promise<CheckpointRestoreResult> {
  return requestApi<CheckpointRestoreResult>(
    `/api/control-plane/tasks/${taskId}/checkpoints/${checkpointId}/restore`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    },
  );
}

export function fetchToolInvocations(params: {
  projectId?: string;
  taskId?: string | null;
  limit?: number;
} = {}): Promise<{ items: ToolInvocation[] }> {
  const query = new URLSearchParams();
  query.set("project_id", params.projectId ?? "default");
  if (params.taskId) {
    query.set("task_id", params.taskId);
  }
  if (params.limit) {
    query.set("limit", String(params.limit));
  }
  return requestApi<{ items: ToolInvocation[] }>(
    `/api/control-plane/tool-invocations?${query.toString()}`,
  );
}
export type TodoItem = {
  id: string;
  title: string;
  description: string;
  status: "pending" | "in_progress" | "done" | "failed" | "skipped";
  verify_command: string | null;
  depends_on: string[];
  step_index: number;
};

export type TodoProgress = {
  total: number;
  done: number;
  failed: number;
  pending: number;
  percent: number;
};

/** Todo 看板是 plan_created 事件的派生视图，不落库。 */
export type TodoBoard = {
  items: TodoItem[];
  progress: TodoProgress;
  /** 按依赖拓扑算出的下一个可执行项；全部完成或全被阻塞时为 null。 */
  next_runnable: TodoItem | null;
};

export function fetchTodoBoard(sessionId: string): Promise<TodoBoard> {
  return requestApi<TodoBoard>(`/api/sessions/${sessionId}/todos`);
}

export function updateTodoStatus(
  sessionId: string,
  todoId: string,
  status: TodoItem["status"],
): Promise<TodoProgress> {
  return requestApi<TodoProgress>(
    `/api/sessions/${sessionId}/todos/${todoId}/status`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    },
  );
}
