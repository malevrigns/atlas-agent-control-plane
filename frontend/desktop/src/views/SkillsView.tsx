import {
  ArrowClockwise,
  CheckCircle,
  Crosshair,
  MagnifyingGlass,
  Plus,
  PuzzlePiece,
} from "@phosphor-icons/react";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { skillsApi } from "../api";
import { InlineNotice, ThemeSelect, formatTimestamp } from "../components";
import type {
  Skill,
  SkillContextPreview,
  SkillRiskLevel,
  SkillStatus,
  Theme,
} from "../types";

const STATUS_LABELS: Record<SkillStatus, string> = {
  draft: "草稿",
  published: "已发布",
  deprecated: "已废弃",
  archived: "已归档",
};

const RISK_LABELS: Record<SkillRiskLevel, string> = {
  low: "低风险",
  medium: "中风险",
  high: "高风险",
  critical: "关键风险",
};

interface DraftForm {
  skill_key: string;
  name: string;
  description: string;
  instructions: string;
  version: string;
  risk_level: SkillRiskLevel;
  tags: string;
}

const emptyDraft: DraftForm = {
  skill_key: "",
  name: "",
  description: "",
  instructions: "",
  version: "1.0.0",
  risk_level: "low",
  tags: "",
};

interface SkillsViewProps {
  theme: Theme;
  setTheme: Dispatch<SetStateAction<Theme>>;
}

export function SkillsView({ theme, setTheme }: SkillsViewProps) {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [versions, setVersions] = useState<Skill[]>([]);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"" | SkillStatus>("");
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);
  const [notice, setNotice] = useState("");
  const [noticeTone, setNoticeTone] = useState<"info" | "danger">("info");
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<DraftForm>(emptyDraft);
  const [editForm, setEditForm] = useState<DraftForm | null>(null);
  const [contextQuery, setContextQuery] = useState("");
  const [contextPreview, setContextPreview] = useState<SkillContextPreview | null>(null);

  const selected = useMemo(
    () => skills.find((skill) => skill.id === selectedId) || null,
    [skills, selectedId],
  );

  const report = useCallback((message: string, tone: "info" | "danger" = "info") => {
    setNotice(message);
    setNoticeTone(tone);
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await skillsApi.list({
        search: search || undefined,
        status: statusFilter || undefined,
      });
      setSkills(data.items);
      setOffline(false);
      setSelectedId((current) => {
        if (current && data.items.some((skill) => skill.id === current)) return current;
        return data.items[0]?.id ?? null;
      });
    } catch (error) {
      setOffline(true);
      report(error instanceof Error ? error.message : "无法连接技能注册中心", "danger");
    } finally {
      setLoading(false);
    }
  }, [search, statusFilter, report]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    setEditForm(null);
    setVersions([]);
    if (!selected) return;
    skillsApi
      .versions(selected.skill_key)
      .then((data) => setVersions(data.items))
      .catch(() => setVersions([]));
  }, [selectedId, selected]);

  async function run<T>(action: () => Promise<T>, successMessage: string): Promise<T | null> {
    try {
      const result = await action();
      report(successMessage);
      await refresh();
      return result;
    } catch (error) {
      report(error instanceof Error ? error.message : "操作失败", "danger");
      return null;
    }
  }

  async function submitDraft() {
    if (!draft.skill_key.trim() || !draft.name.trim() || !draft.instructions.trim()) {
      report("skill_key、名称与指引正文都是必填项。", "danger");
      return;
    }
    const created = await run(
      () =>
        skillsApi.create({
          skill_key: draft.skill_key.trim(),
          name: draft.name.trim(),
          description: draft.description.trim(),
          instructions: draft.instructions.trim(),
          version: draft.version.trim() || "1.0.0",
          risk_level: draft.risk_level,
          tags: draft.tags.split(/[,，\s]+/).filter(Boolean),
        }),
      "技能草稿已创建。",
    );
    if (created) {
      setCreating(false);
      setDraft(emptyDraft);
      setSelectedId(created.id);
    }
  }

  async function submitEdit() {
    if (!selected || !editForm) return;
    const updated = await run(
      () =>
        skillsApi.update(selected.id, {
          name: editForm.name.trim(),
          description: editForm.description.trim(),
          instructions: editForm.instructions.trim(),
          risk_level: editForm.risk_level,
          tags: editForm.tags.split(/[,，\s]+/).filter(Boolean),
        }),
      "草稿已保存。",
    );
    if (updated) setEditForm(null);
  }

  async function previewContext() {
    const clean = contextQuery.trim();
    if (!clean) return;
    try {
      setContextPreview(await skillsApi.previewContext(clean));
      report("已生成注入预览。");
    } catch (error) {
      report(error instanceof Error ? error.message : "预览失败", "danger");
    }
  }

  return (
    <section className="panel-workspace" aria-label="技能注册中心">
      <header className="panel-header">
        <div>
          <h1><PuzzlePiece size={22} weight="duotone" /> 技能注册中心</h1>
          <p className="panel-subtitle">
            团队沉淀的操作指引在这里治理：草稿可改，发布冻结，启用后按相关度注入 Agent 上下文。
          </p>
        </div>
        <div className="header-actions">
          <ThemeSelect theme={theme} onChange={setTheme} />
          <button
            className="outline-button"
            type="button"
            onClick={() => {
              setCreating((value) => !value);
              setDraft(emptyDraft);
            }}
          >
            <Plus size={17} weight="bold" /> 新建技能
          </button>
        </div>
      </header>

      <InlineNotice notice={notice} tone={noticeTone} />
      {offline ? (
        <InlineNotice notice="未连接控制平面：请启动后端后重试。" tone="danger" />
      ) : null}

      <div className="panel-toolbar">
        <label className="search-box">
          <MagnifyingGlass size={16} />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="按 key、名称或描述搜索"
            aria-label="搜索技能"
          />
        </label>
        <select
          value={statusFilter}
          onChange={(event) => setStatusFilter(event.target.value as "" | SkillStatus)}
          aria-label="按状态筛选"
        >
          <option value="">全部状态</option>
          <option value="draft">草稿</option>
          <option value="published">已发布</option>
          <option value="deprecated">已废弃</option>
        </select>
        <button className="icon-button" type="button" onClick={() => void refresh()} aria-label="刷新列表">
          <ArrowClockwise size={18} className={loading ? "spin" : undefined} />
        </button>
      </div>

      {creating ? (
        <div className="editor-card" aria-label="新建技能草稿">
          <h2>新建技能草稿</h2>
          <div className="form-grid">
            <label>skill_key
              <input
                value={draft.skill_key}
                onChange={(event) => setDraft({ ...draft, skill_key: event.target.value })}
                placeholder="deploy-check"
              />
            </label>
            <label>版本
              <input
                value={draft.version}
                onChange={(event) => setDraft({ ...draft, version: event.target.value })}
                placeholder="1.0.0"
              />
            </label>
            <label>名称
              <input
                value={draft.name}
                onChange={(event) => setDraft({ ...draft, name: event.target.value })}
                placeholder="部署前检查"
              />
            </label>
            <label>风险等级
              <select
                value={draft.risk_level}
                onChange={(event) =>
                  setDraft({ ...draft, risk_level: event.target.value as SkillRiskLevel })
                }
              >
                {Object.entries(RISK_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </label>
            <label className="span-2">描述
              <input
                value={draft.description}
                onChange={(event) => setDraft({ ...draft, description: event.target.value })}
                placeholder="一句话说明这个技能什么时候用"
              />
            </label>
            <label className="span-2">标签（空格或逗号分隔）
              <input
                value={draft.tags}
                onChange={(event) => setDraft({ ...draft, tags: event.target.value })}
                placeholder="部署 发布"
              />
            </label>
            <label className="span-2">指引正文（注入 Agent 上下文的内容）
              <textarea
                rows={6}
                value={draft.instructions}
                onChange={(event) => setDraft({ ...draft, instructions: event.target.value })}
                placeholder="1. 先运行测试…&#10;2. 核对迁移…"
              />
            </label>
          </div>
          <div className="editor-actions">
            <button className="outline-button" type="button" onClick={() => setCreating(false)}>取消</button>
            <button className="primary-button" type="button" onClick={() => void submitDraft()}>创建草稿</button>
          </div>
        </div>
      ) : null}

      <div className="panel-body">
        <div className="entity-list" role="list" aria-label="技能列表">
          {skills.length === 0 && !loading ? (
            <p className="empty-hint">还没有技能。点击「新建技能」创建第一条团队指引。</p>
          ) : null}
          {skills.map((skill) => (
            <button
              key={skill.id}
              type="button"
              role="listitem"
              className={`entity-item ${skill.id === selectedId ? "selected" : ""}`}
              onClick={() => setSelectedId(skill.id)}
            >
              <span className="entity-title">
                <strong>{skill.name}</strong>
                <code>{skill.skill_key}@{skill.version}</code>
              </span>
              <span className="entity-meta">
                <span className={`status-chip ${skill.status}`}>{STATUS_LABELS[skill.status]}</span>
                {skill.enabled ? <span className="status-chip enabled">已启用</span> : null}
                <span className="risk-chip">{RISK_LABELS[skill.risk_level]}</span>
              </span>
            </button>
          ))}
        </div>

        <div className="entity-detail" aria-label="技能详情">
          {selected ? (
            <>
              <div className="detail-header">
                <div>
                  <h2>{selected.name}</h2>
                  <p className="detail-meta">
                    <code>{selected.skill_key}@{selected.version}</code>
                    <span className={`status-chip ${selected.status}`}>{STATUS_LABELS[selected.status]}</span>
                    {selected.enabled ? <span className="status-chip enabled">已启用</span> : null}
                    <span>更新于 {formatTimestamp(selected.updated_at)}</span>
                  </p>
                </div>
                <div className="detail-actions">
                  {selected.status === "draft" ? (
                    <>
                      <button
                        className="outline-button"
                        type="button"
                        onClick={() =>
                          setEditForm(
                            editForm
                              ? null
                              : {
                                  skill_key: selected.skill_key,
                                  version: selected.version,
                                  name: selected.name,
                                  description: selected.description,
                                  instructions: selected.instructions,
                                  risk_level: selected.risk_level,
                                  tags: selected.tags.join(" "),
                                },
                          )
                        }
                      >
                        {editForm ? "取消编辑" : "编辑草稿"}
                      </button>
                      <button
                        className="primary-button"
                        type="button"
                        onClick={() => void run(() => skillsApi.publish(selected.id), "技能已发布，内容从此冻结。")}
                      >
                        发布
                      </button>
                    </>
                  ) : null}
                  {selected.status === "published" ? (
                    <>
                      <button
                        className="primary-button"
                        type="button"
                        onClick={() =>
                          void run(
                            () => skillsApi.setEnabled(selected.id, !selected.enabled),
                            selected.enabled ? "技能已停用，不再注入上下文。" : "技能已启用。",
                          )
                        }
                      >
                        {selected.enabled ? "停用" : "启用"}
                      </button>
                      <button
                        className="outline-button"
                        type="button"
                        onClick={() => void run(() => skillsApi.newVersion(selected.id), "已创建下一个草稿版本。")}
                      >
                        新版本
                      </button>
                      <button
                        className="outline-button danger"
                        type="button"
                        onClick={() => void run(() => skillsApi.deprecate(selected.id), "技能已废弃。")}
                      >
                        废弃
                      </button>
                    </>
                  ) : null}
                  {!(selected.status === "published" && selected.enabled) ? (
                    <button
                      className="outline-button danger"
                      type="button"
                      onClick={() => void run(() => skillsApi.remove(selected.id), "技能已删除（软删除，保留审计）。")}
                    >
                      删除
                    </button>
                  ) : null}
                </div>
              </div>

              {editForm ? (
                <div className="editor-card">
                  <h3>编辑草稿</h3>
                  <div className="form-grid">
                    <label>名称
                      <input
                        value={editForm.name}
                        onChange={(event) => setEditForm({ ...editForm, name: event.target.value })}
                      />
                    </label>
                    <label>风险等级
                      <select
                        value={editForm.risk_level}
                        onChange={(event) =>
                          setEditForm({ ...editForm, risk_level: event.target.value as SkillRiskLevel })
                        }
                      >
                        {Object.entries(RISK_LABELS).map(([value, label]) => (
                          <option key={value} value={value}>{label}</option>
                        ))}
                      </select>
                    </label>
                    <label className="span-2">描述
                      <input
                        value={editForm.description}
                        onChange={(event) => setEditForm({ ...editForm, description: event.target.value })}
                      />
                    </label>
                    <label className="span-2">标签
                      <input
                        value={editForm.tags}
                        onChange={(event) => setEditForm({ ...editForm, tags: event.target.value })}
                      />
                    </label>
                    <label className="span-2">指引正文
                      <textarea
                        rows={7}
                        value={editForm.instructions}
                        onChange={(event) => setEditForm({ ...editForm, instructions: event.target.value })}
                      />
                    </label>
                  </div>
                  <div className="editor-actions">
                    <button className="primary-button" type="button" onClick={() => void submitEdit()}>保存草稿</button>
                  </div>
                </div>
              ) : (
                <>
                  {selected.description ? <p className="detail-description">{selected.description}</p> : null}
                  {selected.tags.length ? (
                    <p className="tag-row">
                      {selected.tags.map((tag) => <span key={tag} className="tag">{tag}</span>)}
                    </p>
                  ) : null}
                  <div className="instructions-block">
                    <h3>指引正文</h3>
                    <pre>{selected.instructions || "（空）"}</pre>
                  </div>
                </>
              )}

              {versions.length > 1 ? (
                <div className="versions-block">
                  <h3>版本历史</h3>
                  <ul>
                    {versions.map((version) => (
                      <li key={version.id}>
                        <button
                          type="button"
                          className={version.id === selected.id ? "selected" : ""}
                          onClick={() => setSelectedId(version.id)}
                        >
                          <code>{version.version}</code>
                          <span className={`status-chip ${version.status}`}>{STATUS_LABELS[version.status]}</span>
                          {version.enabled ? <CheckCircle size={14} weight="fill" className="ok" /> : null}
                          <span className="version-time">{formatTimestamp(version.created_at)}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </>
          ) : (
            <p className="empty-hint">选择左侧技能查看详情，或创建一个新技能。</p>
          )}

          <div className="context-preview-block">
            <h3><Crosshair size={16} /> 注入命中调试</h3>
            <p className="panel-subtitle">输入一个任务描述，预览哪些已启用技能会注入 Agent 上下文。</p>
            <div className="query-row">
              <input
                value={contextQuery}
                onChange={(event) => setContextQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") void previewContext();
                }}
                placeholder="例如：准备一次生产部署发布"
                aria-label="注入预览查询"
              />
              <button className="primary-button" type="button" onClick={() => void previewContext()}>预览</button>
            </div>
            {contextPreview ? (
              <div className="context-preview-result">
                <p className="detail-meta">
                  候选 {contextPreview.candidate_count} · 命中 {contextPreview.items.length} ·
                  {" "}{contextPreview.total_chars} 字符
                </p>
                {contextPreview.items.length ? (
                  contextPreview.items.map((item) => (
                    <div key={item.id} className="hit-card">
                      <strong>{item.name}</strong>
                      <code>{item.skill_key}@{item.version}</code>
                      <span>相关度 {item.relevance_score.toFixed(2)}</span>
                      {item.matched_terms.length ? (
                        <span className="matched">命中：{item.matched_terms.slice(0, 5).join("、")}</span>
                      ) : null}
                    </div>
                  ))
                ) : (
                  <p className="empty-hint">没有技能命中该任务描述。</p>
                )}
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </section>
  );
}
