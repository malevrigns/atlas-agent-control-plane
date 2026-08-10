import { requestApi } from "./api";

// ===================== Skill 注册中心类型 =====================

export type SkillStatus = "draft" | "published" | "deprecated" | "archived";
export type SkillRiskLevel = "low" | "medium" | "high" | "critical";

export type Skill = {
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
};

export type SkillDraftInput = {
  skill_key: string;
  name: string;
  description: string;
  instructions: string;
  version: string;
  risk_level: SkillRiskLevel;
  tags: string[];
};

export type SkillContextPreview = {
  query: string;
  items: Array<{
    id: string;
    skill_key: string;
    version: string;
    name: string;
    instructions: string;
    risk_level: string;
    relevance_score: number;
    matched_terms: string[];
  }>;
  candidate_count: number;
  omitted_count: number;
  total_chars: number;
  rendered: string;
};

// ===================== Skill 注册中心 API =====================

export function fetchSkills(params: { search?: string; status?: string } = {}) {
  const query = new URLSearchParams();
  if (params.search) query.set("search", params.search);
  if (params.status) query.set("status", params.status);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return requestApi<{ items: Skill[] }>(`/api/skills${suffix}`);
}

export function fetchSkillVersions(skillKey: string) {
  return requestApi<{ items: Skill[] }>(
    `/api/skills/${encodeURIComponent(skillKey)}/versions`,
  );
}

export function createSkillDraft(input: SkillDraftInput) {
  return requestApi<Skill>("/api/skills", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateSkill(
  skillId: string,
  input: Partial<{
    name: string;
    description: string;
    instructions: string;
    risk_level: SkillRiskLevel;
    tags: string[];
  }>,
) {
  return requestApi<Skill>(`/api/skills/${skillId}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function publishSkill(skillId: string) {
  return requestApi<Skill>(`/api/skills/${skillId}/publish`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function setSkillEnabled(skillId: string, enabled: boolean) {
  return requestApi<Skill>(`/api/skills/${skillId}/enabled`, {
    method: "POST",
    body: JSON.stringify({ enabled }),
  });
}

export function createSkillVersion(skillId: string) {
  return requestApi<Skill>(`/api/skills/${skillId}/versions`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function deprecateSkill(skillId: string) {
  return requestApi<Skill>(`/api/skills/${skillId}/deprecate`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function deleteSkill(skillId: string) {
  return requestApi<void>(`/api/skills/${skillId}`, { method: "DELETE" });
}

export function previewSkillContext(query: string) {
  return requestApi<SkillContextPreview>(
    `/api/skills/context?query=${encodeURIComponent(query)}`,
  );
}
