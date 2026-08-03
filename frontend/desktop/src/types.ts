export type ApiState = "checking" | "connected" | "offline";
export type CheckpointState = "done" | "running" | "pending";
export type HttpMethod = "GET" | "POST" | "PATCH" | "DELETE";
export type Theme = "ink" | "dawn" | "contrast";
export type ToolPolicy = "自动允许" | "每次询问" | "本次拒绝";

export interface AtlasRequestOptions {
  method?: HttpMethod;
  body?: unknown;
}

export interface ApiEnvelope<T> {
  code?: number | string;
  message?: string;
  data?: T;
}

export interface TaskState {
  id: string;
  project_id: string;
  title: string;
  status: string;
  next_actions: Array<Record<string, unknown>>;
  version: number;
  updated_at: string;
}

export interface TaskStateList {
  items: TaskState[];
}

export interface Checkpoint {
  id: string;
  kind: string;
  covered_event_start: number;
  covered_event_end: number;
  state_hash: string;
  validator_report: {
    valid?: unknown;
  };
  created_at: string;
}

export interface CheckpointList {
  items: Checkpoint[];
}

export interface CheckpointRestoreResult {
  checkpoint_id: string;
  resumed: boolean;
  task: TaskState;
}

export interface CheckpointView {
  id: string;
  rawId?: string;
  title: string;
  description: string;
  time: string;
  state: CheckpointState;
  eventRange: string;
  stateHash?: string;
}
