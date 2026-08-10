import type { ChatMessage, PlanStep, SessionEventItem } from "../../types";

export type TimelineItem =
  | { kind: "message"; id: string; created_at: string; message: ChatMessage }
  | { kind: "plan"; id: string; created_at: string; event: SessionEventItem };

export type StepView = PlanStep & {
  startedAt: string | null;
  completedAt: string | null;
  errorEvent: SessionEventItem | null;
  toolEvent: SessionEventItem | null;
  summary: string;
};

export type MultiAgentInlineResult = {
  kind: "multi_agent_result";
  manager: string;
  subtasks: Array<{
    id: string;
    assignee: string;
    title: string;
    status: string;
    output: string;
  }>;
  review: {
    reviewer: string;
    status: string;
  };
  final_answer: string;
};

export type ToolObservation = {
  title: string;
  brief: string;
  pills: string[];
};

export type AgentRunViewModel = {
  timelineItems: TimelineItem[];
};

