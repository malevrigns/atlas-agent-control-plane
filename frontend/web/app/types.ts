import type { LucideIcon } from "lucide-react";

export type ApiErrorData = {
  type: string;
  source: string;
  user_message: string;
  suggestion: string;
  request_id: string | null;
  details: Record<string, unknown> | null;
};

export type ApiResponse<T> = {
  code: number;
  message: string;
  data: T | null;
  error?: ApiErrorData | null;
};

export type ApiStatusData = {
  service: string;
  environment: string;
  status: string;
  version: string;
};

export type DatabaseStatusData = {
  status: string;
};

export type SandboxInstanceData = {
  id: string; // 当前任务沙箱 ID，现阶段固定为 default。
  name: string; // Compose 容器名，用于排查当前连接的是哪个沙箱。
  base_url: string; // 主 API 访问 Sandbox 的地址，只做状态展示。
  status: string; // ready/unavailable/released，决定面板颜色和文案。
  message: string; // 主 API 返回的状态说明，直接展示给用户。
};

export type VncStatusData = {
  enabled: boolean; // 是否启用 VNC/noVNC 远程桌面。
  display: string; // Xvfb 虚拟显示器编号，例如 :99。
  vnc_port: number; // 容器内 x11vnc 端口，主要用于排查。
  web_port: number; // 容器内 noVNC/websockify 端口，Nginx 会代理它。
  iframe_path: string; // 前端 iframe 打开的路径，通常是 /sandbox-vnc/vnc.html。
  websocket_path: string; // noVNC 连接 websockify 使用的 WebSocket 路径。
  message: string; // 状态说明，显示在 VNC 面板中。
};

export type McpServerItem = {
  name: string; // MCP Server 配置名。
  enabled: boolean; // 是否启用。
  transport: string; // demo、stdio、sse 或 streamable_http。
  description: string; // 配置说明。
};

export type McpServerListData = {
  items: McpServerItem[];
};

export type McpToolItem = {
  server_name: string; // 工具来自哪个 MCP Server。
  name: string; // MCP 工具名。
  description: string; // 工具说明。
  input_schema: Record<string, unknown>; // MCP tools/list 返回的参数 JSON Schema。
};

export type McpToolListData = {
  items: McpToolItem[];
};

export type A2aRoleItem = {
  name: string; // Host Agent、Remote Agent、Agent Card 或 Task。
  responsibility: string; // 这个角色在 A2A 协作中负责什么。
  system_mapping: string; // 在 AtlasAgent 中会映射到哪里。
};

export type A2aConceptsData = {
  roles: A2aRoleItem[];
  protocol: string; // A2A 协议解决的问题。
  next_step: string; // 下一章会继续实现什么。
};

export type A2aCapabilityItem = {
  name: string; // 远程 Agent 声明的能力名。
  description: string; // 能力说明。
  example: string; // 示例任务。
};

export type A2aAgentCardData = {
  name: string; // 远程 Agent 名称。
  description: string; // 远程 Agent 做什么。
  url: string; // 远程 Agent 地址；demo 会使用 demo:// 协议。
  version: string; // Agent Card 版本。
  capabilities: A2aCapabilityItem[];
  default_input_modes: string[];
  default_output_modes: string[];
};

export type A2aRemoteAgentItem = {
  key: string; // A2A 配置文件中的 Agent key。
  enabled: boolean; // 是否启用该远程 Agent。
  transport: string; // demo 或 http。
  name: string; // 远程 Agent 名称。
  description: string; // 远程 Agent 职责说明。
  url: string; // 远程 Agent 地址。
  version: string; // Agent Card 版本。
  capabilities: A2aCapabilityItem[];
};

export type A2aRemoteAgentListData = {
  items: A2aRemoteAgentItem[];
};

export type MultiAgentRoleItem = {
  key: string; // 程序识别角色的稳定标识，例如 manager。
  name: string; // 展示给用户看的角色名称。
  responsibility: string; // 角色在协作流程中负责什么。
  capability: string; // 角色擅长处理的任务类型。
};

export type MultiAgentRoleListData = {
  items: MultiAgentRoleItem[];
};

export type SettingsItem = {
  name: string; // 配置项名称，例如 LLM provider、MCP Server 或远程 Agent key。
  description: string; // 配置项说明。
  enabled: boolean; // 该配置项当前是否可用。
  metadata: Record<string, unknown>; // transport、url、api_key_env 等额外信息。
};

export type SettingsModule = {
  key: "llm" | "search" | "mcp" | "a2a" | "multi_agent" | "sandbox";
  name: string; // 模块展示名称。
  description: string; // 模块说明。
  enabled: boolean; // 设置页中的运行时启用状态。
  default_item: string | null; // 当前默认项。
  items: SettingsItem[]; // 模块下的配置项列表。
  status: "ready" | "warning" | "disabled" | string; // 模块健康状态。
  status_message: string; // 面向用户的配置说明。
  source: string; // 配置来源，例如 .env 或 config/llm.yaml。
  verify_command: string; // 可以复制执行的验证命令。
};

export type SettingsIntegration = {
  id: string; // 运行时集成记录 ID。
  kind: "llm" | "search" | "mcp" | "a2a" | "multi_agent" | "sandbox"; // 集成类型。
  name: string; // 集成名称。
  description: string; // 集成说明。
  endpoint: string | null; // 外部服务地址。
  enabled: boolean; // 是否启用。
};

export type AppSettingsData = {
  modules: SettingsModule[];
  integrations: SettingsIntegration[];
};

export type HarnessExpectation = {
  required_events: string[]; // 用例必须出现的事件类型。
  required_tools: string[]; // 用例必须调用的工具名。
  required_files: string[]; // 用例必须生成的文件名或文件标识。
  forbidden_events: string[]; // 一旦出现就判定异常的事件类型。
};

export type HarnessCaseItem = {
  id: string;
  title: string;
  task: string;
  description: string;
  tags: string[];
  expectation: HarnessExpectation;
};

export type HarnessCaseListData = {
  items: HarnessCaseItem[];
};

export type HarnessAssertionItem = {
  name: string; // 断言名称，例如 required_tool:browser_open。
  passed: boolean; // true 表示通过。
  detail: string; // 断言解释，失败时会给出缺少项。
};

export type HarnessEventItem = {
  id: string;
  type: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type HarnessRunData = {
  id: string;
  case_id: string;
  mode: string;
  status: "passed" | "failed";
  task: string;
  prompt_summary: string;
  events: HarnessEventItem[];
  assertions: HarnessAssertionItem[];
  started_at: string;
  completed_at: string | null;
};

export type HarnessReplayData = {
  run: HarnessRunData;
  events: HarnessEventItem[];
};

export type ObservabilityCheckItem = {
  key: string;
  name: string;
  category: string; // core、agent、tooling 等诊断分类。
  description: string; // 这条诊断项解决什么排查问题。
  command: string; // 可以直接复制执行的 curl 或命令。
  expected: string; // 正常情况下应该看到什么结果。
};

export type ObservabilityCheckListData = {
  items: ObservabilityCheckItem[];
};

export type SecurityCheckItem = {
  key: string;
  name: string;
  category: string; // configuration、uploads、sandbox、integrations、memory。
  severity: "info" | "warning" | "risk"; // 风险等级，用于决定前端徽标颜色。
  risk: string; // 不处理这条边界会带来什么风险。
  recommendation: string; // 推荐的配置、架构或上线前处理方式。
  verify_command: string; // 可复制执行的验证命令。
};

export type SecurityCheckListData = {
  items: SecurityCheckItem[];
};

export type ProductAcceptanceItem = {
  key: string;
  title: string;
  category: string;
  status: "ready" | "needs_manual_check";
  evidence: string;
  verify_steps: string[];
  related_routes: string[];
};

export type ProductAcceptanceSummary = {
  total: number;
  ready: number;
  needs_manual_check: number;
};

export type ProductAcceptanceChecklistData = {
  summary: ProductAcceptanceSummary;
  items: ProductAcceptanceItem[];
};

export type MemoryKind =
  | "user_preference"
  | "project_fact"
  | "task_experience"
  | "constraint";

export type AgentMemoryItem = {
  id: string; // 长期记忆 ID。
  kind: MemoryKind; // 记忆分类，用来决定后续如何注入上下文。
  content: string; // 记忆正文，后续会进入 Agent 上下文。
  importance: number; // 重要度，1-5；第41章检索会用它参与排序。
  enabled: boolean; // false 表示保留但不参与后续检索。
  source_session_id: string | null; // 记忆来源会话，方便追溯。
  source_event_id: string | null; // 记忆来源事件，方便追溯。
  expires_at: string | null; // 过期时间；为空表示长期有效。
  metadata: Record<string, unknown>; // 抽取来源、规则等额外信息。
  created_at: string | null;
  updated_at: string | null;
};

export type AgentMemoryListData = {
  items: AgentMemoryItem[];
};

export type MemoryCandidateItem = {
  kind: MemoryKind;
  content: string;
  importance: number;
  reason: string;
  source_session_id: string | null;
  source_event_id: string | null;
  metadata: Record<string, unknown>;
};

export type MemoryCandidateListData = {
  items: MemoryCandidateItem[];
};

export type SessionItem = {
  id: string;
  title: string;
  status: string;
  unread_count: number;
  created_at: string;
  updated_at: string;
};

export type SessionListData = {
  items: SessionItem[];
};

export type ChatMessage = {
  id: string;
  session_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
};

export type MessageListData = {
  items: ChatMessage[];
};

export type SessionEventItem = {
  id: string;
  session_id: string;
  type: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type SessionEventListData = {
  items: SessionEventItem[];
};

export type MessageCreateData = {
  message: ChatMessage;
  event: SessionEventItem;
};

export type PlanStep = {
  id: string;
  title: string;
  description: string;
  expected_output: string;
  status: string;
};

export type AgentPlan = {
  id: string;
  title: string;
  goal: string;
  source: string;
  steps: PlanStep[];
};

export type PlanCreateData = {
  plan: AgentPlan;
  event: SessionEventItem;
};

export type PlanExecuteData = {
  events: SessionEventItem[];
};

export type AgentTaskItem = {
  id: string;
  session_id: string;
  type: string;
  status:
    | "queued"
    | "running"
    | "waiting"
    | "completed"
    | "succeeded"
    | "failed"
    | "stopped"
    | "cancelled";
  error: string | null;
  created_at: string;
  updated_at: string;
  parent_task_id: string | null;
  retry_count: number;
};

export type ContextMessage = {
  role: string;
  content: string;
  original_chars: number; // 原始消息长度，用来提示裁剪前有多少内容。
  truncated: boolean; // true 表示 content 已经按上下文预算裁剪。
  created_at: string;
};

export type ContextEventSummary = {
  type: string;
  count: number; // 最近事件窗口里同类型事件出现的次数。
  latest_at: string; // 同类型事件最近一次发生的时间。
};

export type ContextFileReference = {
  id: string;
  name: string;
  content_type: string;
  size: number;
  usage_hint: string; // 给 Agent 或用户看的文件使用建议。
};

export type MemoryContextItem = {
  id: string;
  kind: MemoryKind;
  content: string;
  importance: number;
  relevance_score: number; // 相关度、重要度和新鲜度合成后的分数。
  matched_terms: string[]; // 与当前任务匹配的可解释关键词。
  original_chars: number;
  truncated: boolean;
  source_session_id: string | null;
  source_event_id: string | null;
  updated_at: string | null;
};

export type MemoryContext = {
  query: string; // 当前任务、会话标题和最近消息组成的检索文本。
  items: MemoryContextItem[];
  candidate_count: number;
  omitted_count: number;
  total_chars: number;
  max_chars: number;
};

export type ContextBudget = {
  message_limit: number;
  event_limit: number;
  max_message_chars: number;
  included_messages: number; // 本次快照实际纳入的消息条数。
  omitted_messages: number; // 因预算限制没有纳入的历史消息条数。
  included_events: number; // 本次快照参考的最近事件数量。
  omitted_events: number; // 因预算限制没有纳入的历史事件数量。
  total_message_chars: number; // 裁剪后消息内容的总字符数。
  memory_limit: number;
  max_memory_chars: number;
  included_memories: number; // 本次真正注入 Agent 的长期记忆数。
  omitted_memories: number; // 因相关度或预算没有注入的候选数。
  total_memory_chars: number; // 长期记忆区域实际使用的字符数。
};

export type SessionContextData = {
  session_id: string;
  summary: string;
  messages: ContextMessage[];
  event_summaries: ContextEventSummary[];
  files: ContextFileReference[];
  memory_context: MemoryContext;
  budget: ContextBudget;
};

export type UploadedFile = {
  id: string;
  original_name: string;
  content_type: string;
  size: number;
  download_url: string;
  created_at: string;
};

export type SessionFileItem = {
  id: string;
  session_id: string;
  file: UploadedFile;
  created_at: string;
};

export type SessionFileListData = {
  items: SessionFileItem[];
};

export type FilePreviewData = {
  file: UploadedFile;
  content: string;
  file_type: string;
  language: string | null;
  line_count: number;
  parse_status: string;
  parse_message: string;
  references: Array<{
    label: string;
    excerpt: string;
    start_line: number | null;
    end_line: number | null;
  }>;
  summary: string;
  truncated: boolean;
};

export type StreamEvent = {
  event: string;
  data: Record<string, unknown>;
};

export type LoadState<T> =
  | { type: "loading" }
  | { type: "ready"; data: T }
  | { type: "error"; message: string };

export type StatusBadgeView = {
  label: string;
  className: string;
  icon: LucideIcon;
};
