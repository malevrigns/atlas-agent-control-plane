export type ApiState = "checking" | "connected" | "offline";
export type WorkspaceView = "tasks" | "skills" | "knowledge";
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

// ===================== Skill 注册中心 =====================

export type SkillStatus = "draft" | "published" | "deprecated" | "archived";
export type SkillRiskLevel = "low" | "medium" | "high" | "critical";

export interface Skill {
  id: string;
  skill_key: string;
  version: string;
  name: string;
  description: string;
  instructions: string;
  definition: Record<string, unknown>;
  risk_level: SkillRiskLevel;
  status: SkillStatus;
  enabled: boolean;
  tags: string[];
  test_record: Record<string, unknown>;
  created_by: string;
  created_at: string | null;
  updated_at: string | null;
  published_at: string | null;
}

export interface SkillList {
  items: Skill[];
}

export interface SkillDraftInput {
  skill_key: string;
  name: string;
  description: string;
  instructions: string;
  version: string;
  risk_level: SkillRiskLevel;
  tags: string[];
}

export interface SkillContextItem {
  id: string;
  skill_key: string;
  version: string;
  name: string;
  instructions: string;
  risk_level: string;
  relevance_score: number;
  matched_terms: string[];
}

export interface SkillContextPreview {
  query: string;
  items: SkillContextItem[];
  candidate_count: number;
  omitted_count: number;
  total_chars: number;
  rendered: string;
}

// ===================== RAG 知识库 =====================

export type DocumentStatus = "pending" | "processing" | "ready" | "failed";

export interface KnowledgeBase {
  id: string;
  name: string;
  description: string;
  project_id: string;
  embedding_provider: string;
  embedding_model: string;
  embedding_dim: number;
  chunk_size: number;
  chunk_overlap: number;
  document_count: number;
  chunk_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface KnowledgeBaseList {
  items: KnowledgeBase[];
}

export interface KnowledgeDocument {
  id: string;
  knowledge_base_id: string;
  title: string;
  source_type: string;
  source_ref: string;
  status: DocumentStatus;
  chunk_count: number;
  content_chars: number;
  error: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface KnowledgeDocumentList {
  items: KnowledgeDocument[];
}

export interface RetrievedChunk {
  chunk_id: string;
  document_id: string;
  document_title: string;
  seq: number;
  content: string;
  vector_score: number;
  lexical_score: number;
  final_score: number;
  matched_terms: string[];
  citation: string;
}

export interface RagQueryResult {
  query: string;
  knowledge_base_id: string;
  backend: string;
  embedding_provider: string;
  top_k: number;
  candidate_count: number;
  total_chars: number;
  context_text: string;
  chunks: RetrievedChunk[];
}
