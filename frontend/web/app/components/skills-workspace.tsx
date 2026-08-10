"use client";

import {
  Loader2,
  Plus,
  Puzzle,
  RefreshCcw,
  Search,
  Sparkles,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { SelectMenu } from "./select-menu";
import {
  createSkillDraft,
  createSkillVersion,
  deleteSkill,
  deprecateSkill,
  fetchSkills,
  previewSkillContext,
  publishSkill,
  setSkillEnabled,
  updateSkill,
} from "../lib/skills-api";
import type { Skill, SkillContextPreview, SkillRiskLevel } from "../lib/skills-api";

const RISK_OPTIONS = [
  { value: "low" as SkillRiskLevel, label: "低风险", hint: "只读或纯文本指引" },
  { value: "medium" as SkillRiskLevel, label: "中风险", hint: "涉及外部调用" },
  { value: "high" as SkillRiskLevel, label: "高风险", hint: "有副作用的操作" },
  { value: "critical" as SkillRiskLevel, label: "关键风险", hint: "生产环境敏感操作" },
];

const STATUS_FILTER_OPTIONS = [
  { value: "", label: "全部状态" },
  { value: "draft", label: "草稿" },
  { value: "published", label: "已发布" },
  { value: "deprecated", label: "已废弃" },
];

const STATUS_LABELS: Record<string, string> = {
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

const EMPTY_DRAFT = {
  skill_key: "",
  name: "",
  description: "",
  instructions: "",
  version: "0.1.0",
  risk_level: "low" as SkillRiskLevel,
  tags: "",
};

/**
 * Web 版 Skill 注册中心：草稿、发布、启停、版本与注入预览。
 * 与桌面端共用同一套 /api/skills 接口。
 */
export function SkillsWorkspace() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState("");
  const [noticeTone, setNoticeTone] = useState<"info" | "danger">("info");
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState({ ...EMPTY_DRAFT });
  const [editForm, setEditForm] = useState<{
    name: string;
    description: string;
    instructions: string;
    risk_level: SkillRiskLevel;
  } | null>(null);
  const [previewQuery, setPreviewQuery] = useState("");
  const [previewing, setPreviewing] = useState(false);
  const [preview, setPreview] = useState<SkillContextPreview | null>(null);

  const selected = useMemo(
    () => skills.find((skill) => skill.id === selectedId) ?? null,
    [skills, selectedId],
  );

  const report = useCallback((message: string, tone: "info" | "danger" = "info") => {
    setNotice(message);
    setNoticeTone(tone);
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchSkills({
        search: search.trim() || undefined,
        status: statusFilter || undefined,
      });
      setSkills(data.items);
      setSelectedId((current) =>
        current && data.items.some((skill) => skill.id === current)
          ? current
          : data.items[0]?.id ?? null,
      );
    } catch (error) {
      report(error instanceof Error ? error.message : "读取技能失败", "danger");
    } finally {
      setLoading(false);
    }
  }, [report, search, statusFilter]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    setEditForm(null);
  }, [selectedId]);

  async function run(action: () => Promise<unknown>, successMessage: string) {
    try {
      await action();
      report(successMessage);
      await refresh();
    } catch (error) {
      report(error instanceof Error ? error.message : "操作失败", "danger");
    }
  }

  async function submitCreate() {
    if (!draft.skill_key.trim() || !draft.name.trim() || !draft.instructions.trim()) {
      report("skill_key、名称与指引内容都是必填项。", "danger");
      return;
    }
    await run(
      () =>
        createSkillDraft({
          skill_key: draft.skill_key.trim(),
          name: draft.name.trim(),
          description: draft.description.trim(),
          instructions: draft.instructions,
          version: draft.version.trim() || "0.1.0",
          risk_level: draft.risk_level,
          tags: draft.tags
            .split(/[,，]/)
            .map((tag) => tag.trim())
            .filter(Boolean),
        }),
      "技能草稿已创建。",
    );
    setCreating(false);
    setDraft({ ...EMPTY_DRAFT });
  }

  async function runPreview() {
    if (!previewQuery.trim()) return;
    setPreviewing(true);
    try {
      setPreview(await previewSkillContext(previewQuery.trim()));
    } catch (error) {
      report(error instanceof Error ? error.message : "预览失败", "danger");
    } finally {
      setPreviewing(false);
    }
  }

  const inputClass =
    "h-10 w-full rounded-xl border border-(--line) bg-(--field) px-3 text-sm text-(--text-1) outline-none transition placeholder:text-(--text-5) focus:border-(--accent)/60";

  return (
    <section className="mx-auto flex h-full min-h-[640px] w-full max-w-[1080px] flex-col overflow-hidden rounded-[28px] border border-(--line) bg-(--surface)/95 shadow-2xl shadow-black/25">
      <header className="flex shrink-0 items-start justify-between gap-4 border-b border-(--line) px-6 py-5">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-semibold text-(--text-1)">
            <Puzzle size={19} aria-hidden="true" />
            技能注册中心
          </h2>
          <p className="mt-1 text-sm leading-6 text-(--text-4)">
            draft → published 生命周期治理；启用的技能按相关度注入 Agent 上下文
          </p>
        </div>
        <div className="flex gap-2">
          <button
            className="inline-flex h-10 items-center gap-2 rounded-2xl bg-blue-500 px-4 text-sm font-medium text-white transition hover:bg-blue-400"
            onClick={() => setCreating((value) => !value)}
            type="button"
          >
            <Plus size={15} aria-hidden="true" /> 新建草稿
          </button>
          <button
            className="inline-flex h-10 w-10 items-center justify-center rounded-2xl border border-(--line) bg-(--fill-1) text-(--text-3) hover:bg-(--fill-2) hover:text-(--text-1)"
            onClick={() => void refresh()}
            title="刷新"
            type="button"
          >
            <RefreshCcw className={loading ? "animate-spin" : ""} size={16} aria-hidden="true" />
          </button>
        </div>
      </header>

      {notice ? (
        <div
          className={`mx-6 mt-4 rounded-2xl border px-4 py-2.5 text-sm ${
            noticeTone === "danger"
              ? "border-rose-500/30 bg-rose-500/10 text-rose-300"
              : "border-(--line) bg-(--fill-1) text-(--text-3)"
          }`}
        >
          {notice}
        </div>
      ) : null}

      {creating ? (
        <div className="mx-6 mt-4 rounded-2xl border border-(--line) bg-(--fill-1) p-4">
          <div className="grid grid-cols-2 gap-3 max-md:grid-cols-1">
            <input
              className={inputClass}
              onChange={(event) => setDraft({ ...draft, skill_key: event.target.value })}
              placeholder="skill_key（如 deploy-checklist）"
              value={draft.skill_key}
            />
            <input
              className={inputClass}
              onChange={(event) => setDraft({ ...draft, name: event.target.value })}
              placeholder="技能名称"
              value={draft.name}
            />
            <input
              className={inputClass}
              onChange={(event) => setDraft({ ...draft, description: event.target.value })}
              placeholder="一句话描述"
              value={draft.description}
            />
            <div className="flex gap-3">
              <input
                className={`${inputClass} flex-1`}
                onChange={(event) => setDraft({ ...draft, version: event.target.value })}
                placeholder="版本 0.1.0"
                value={draft.version}
              />
              <SelectMenu
                ariaLabel="风险等级"
                className="w-36 shrink-0"
                onChange={(value) => setDraft({ ...draft, risk_level: value })}
                options={RISK_OPTIONS}
                value={draft.risk_level}
              />
            </div>
            <input
              className={`${inputClass} col-span-2 max-md:col-span-1`}
              onChange={(event) => setDraft({ ...draft, tags: event.target.value })}
              placeholder="标签（逗号分隔，如：部署,回滚）"
              value={draft.tags}
            />
            <textarea
              className="col-span-2 min-h-28 w-full rounded-xl border border-(--line) bg-(--field) px-3 py-2.5 text-sm leading-6 text-(--text-1) outline-none placeholder:text-(--text-5) focus:border-(--accent)/60 max-md:col-span-1"
              onChange={(event) => setDraft({ ...draft, instructions: event.target.value })}
              placeholder="技能指引内容（Markdown）：Agent 命中该技能时会把这段指引注入上下文…"
              value={draft.instructions}
            />
          </div>
          <div className="mt-3 flex justify-end gap-2">
            <button
              className="rounded-xl border border-(--line) bg-(--fill-1) px-4 py-2 text-sm text-(--text-3) hover:text-(--text-1)"
              onClick={() => setCreating(false)}
              type="button"
            >
              取消
            </button>
            <button
              className="rounded-xl bg-blue-500 px-4 py-2 text-sm font-medium text-white hover:bg-blue-400"
              onClick={() => void submitCreate()}
              type="button"
            >
              创建草稿
            </button>
          </div>
        </div>
      ) : null}

      <div className="grid min-h-0 flex-1 grid-cols-[300px_1fr] max-lg:grid-cols-1">
        <aside className="flex min-h-0 flex-col border-r border-(--line) p-4 max-lg:border-b max-lg:border-r-0">
          <div className="flex gap-2">
            <div className="flex h-9 flex-1 items-center gap-2 rounded-xl border border-(--line) bg-(--field) px-2.5">
              <Search className="shrink-0 text-(--text-5)" size={14} aria-hidden="true" />
              <input
                className="w-full bg-transparent text-sm text-(--text-1) outline-none placeholder:text-(--text-5)"
                onChange={(event) => setSearch(event.target.value)}
                placeholder="搜索技能"
                value={search}
              />
            </div>
            <SelectMenu
              ariaLabel="按状态筛选"
              className="w-28 shrink-0 [&>button]:h-9 [&>button]:text-xs"
              onChange={setStatusFilter}
              options={STATUS_FILTER_OPTIONS}
              value={statusFilter}
            />
          </div>
          <div className="mt-3 grid min-h-0 flex-1 content-start gap-2 overflow-y-auto">
            {skills.length === 0 && !loading ? (
              <p className="px-2 text-sm leading-6 text-(--text-4)">
                还没有技能。把团队沉淀的操作指引变成受治理的 Agent 行为规范。
              </p>
            ) : null}
            {skills.map((skill) => (
              <button
                className={`rounded-2xl border p-3 text-left transition ${
                  skill.id === selectedId
                    ? "border-(--accent)/50 bg-(--accent)/10"
                    : "border-(--line) bg-(--fill-1) hover:bg-(--fill-2)"
                }`}
                key={skill.id}
                onClick={() => setSelectedId(skill.id)}
                type="button"
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="truncate text-sm font-semibold text-(--text-1)">
                    {skill.name}
                  </span>
                  <span className="shrink-0 text-[11px] text-(--text-4)">v{skill.version}</span>
                </div>
                <div className="mt-1 truncate text-xs text-(--text-4)">{skill.skill_key}</div>
                <div className="mt-2 flex flex-wrap gap-1.5 text-[11px]">
                  <span
                    className={`rounded-full border px-2 py-0.5 ${
                      skill.status === "published"
                        ? "border-emerald-500/40 text-emerald-400"
                        : skill.status === "deprecated"
                          ? "border-rose-500/40 text-rose-400"
                          : "border-(--line) text-(--text-4)"
                    }`}
                  >
                    {STATUS_LABELS[skill.status] || skill.status}
                  </span>
                  {skill.enabled ? (
                    <span className="rounded-full border border-(--accent)/40 px-2 py-0.5 text-(--accent)">
                      已启用
                    </span>
                  ) : null}
                  <span className="rounded-full border border-(--line) px-2 py-0.5 text-(--text-4)">
                    {RISK_LABELS[skill.risk_level]}
                  </span>
                </div>
              </button>
            ))}
          </div>
        </aside>

        <section className="min-h-0 overflow-y-auto p-5">
          {selected ? (
            <div className="grid gap-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="text-base font-semibold text-(--text-1)">
                    {selected.name}
                    <span className="ml-2 text-xs font-normal text-(--text-4)">
                      {selected.skill_key} · v{selected.version}
                    </span>
                  </h3>
                  <p className="mt-1 text-sm text-(--text-4)">
                    {selected.description || "（无描述）"}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {selected.status === "draft" ? (
                    <>
                      <button
                        className="rounded-xl border border-(--line) px-3 py-1.5 text-xs text-(--text-3) hover:text-(--text-1)"
                        onClick={() =>
                          setEditForm(
                            editForm
                              ? null
                              : {
                                  name: selected.name,
                                  description: selected.description,
                                  instructions: selected.instructions,
                                  risk_level: selected.risk_level,
                                },
                          )
                        }
                        type="button"
                      >
                        {editForm ? "取消编辑" : "编辑草稿"}
                      </button>
                      <button
                        className="rounded-xl bg-blue-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-400"
                        onClick={() =>
                          void run(() => publishSkill(selected.id), "技能已发布（内容冻结）。")
                        }
                        type="button"
                      >
                        发布
                      </button>
                    </>
                  ) : null}
                  {selected.status === "published" ? (
                    <>
                      <button
                        className="rounded-xl border border-(--line) px-3 py-1.5 text-xs text-(--text-3) hover:text-(--text-1)"
                        onClick={() =>
                          void run(
                            () => setSkillEnabled(selected.id, !selected.enabled),
                            selected.enabled ? "技能已停用。" : "技能已启用，可被注入上下文。",
                          )
                        }
                        type="button"
                      >
                        {selected.enabled ? "停用" : "启用"}
                      </button>
                      <button
                        className="rounded-xl border border-(--line) px-3 py-1.5 text-xs text-(--text-3) hover:text-(--text-1)"
                        onClick={() =>
                          void run(
                            () => createSkillVersion(selected.id),
                            "已派生新草稿版本。",
                          )
                        }
                        type="button"
                      >
                        派生新版本
                      </button>
                      <button
                        className="rounded-xl border border-amber-500/40 px-3 py-1.5 text-xs text-amber-400 hover:bg-amber-500/10"
                        onClick={() =>
                          void run(() => deprecateSkill(selected.id), "技能已废弃。")
                        }
                        type="button"
                      >
                        废弃
                      </button>
                    </>
                  ) : null}
                  {selected.status !== "published" || !selected.enabled ? (
                    <button
                      className="rounded-xl border border-rose-500/40 px-3 py-1.5 text-xs text-rose-400 hover:bg-rose-500/10"
                      onClick={() =>
                        void run(() => deleteSkill(selected.id), "技能已删除。")
                      }
                      type="button"
                    >
                      删除
                    </button>
                  ) : null}
                </div>
              </div>

              {editForm ? (
                <div className="rounded-2xl border border-(--line) bg-(--fill-1) p-4">
                  <div className="grid gap-3">
                    <input
                      className={inputClass}
                      onChange={(event) =>
                        setEditForm({ ...editForm, name: event.target.value })
                      }
                      value={editForm.name}
                    />
                    <input
                      className={inputClass}
                      onChange={(event) =>
                        setEditForm({ ...editForm, description: event.target.value })
                      }
                      placeholder="描述"
                      value={editForm.description}
                    />
                    <textarea
                      className="min-h-32 w-full rounded-xl border border-(--line) bg-(--field) px-3 py-2.5 text-sm leading-6 text-(--text-1) outline-none focus:border-(--accent)/60"
                      onChange={(event) =>
                        setEditForm({ ...editForm, instructions: event.target.value })
                      }
                      value={editForm.instructions}
                    />
                    <div className="flex items-center justify-between">
                      <SelectMenu
                        ariaLabel="风险等级"
                        className="w-36"
                        onChange={(value) =>
                          setEditForm({ ...editForm, risk_level: value })
                        }
                        options={RISK_OPTIONS}
                        value={editForm.risk_level}
                      />
                      <button
                        className="rounded-xl bg-blue-500 px-4 py-2 text-sm font-medium text-white hover:bg-blue-400"
                        onClick={() =>
                          void run(() => updateSkill(selected.id, editForm), "草稿已保存。").then(
                            () => setEditForm(null),
                          )
                        }
                        type="button"
                      >
                        保存草稿
                      </button>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="rounded-2xl border border-(--line) bg-(--fill-1) p-4">
                  <h4 className="text-sm font-semibold text-(--text-1)">技能指引</h4>
                  <pre className="mt-2 whitespace-pre-wrap break-words text-sm leading-7 text-(--text-3)">
                    {selected.instructions}
                  </pre>
                </div>
              )}

              <div className="rounded-2xl border border-(--line) bg-(--fill-1) p-4">
                <h4 className="flex items-center gap-2 text-sm font-semibold text-(--text-1)">
                  <Sparkles size={14} aria-hidden="true" /> 注入命中预览
                </h4>
                <p className="mt-1 text-xs text-(--text-4)">
                  输入一个用户任务，查看启用中的技能会以怎样的相关度被注入 Agent 上下文
                </p>
                <div className="mt-3 flex gap-2">
                  <input
                    className={inputClass}
                    onChange={(event) => setPreviewQuery(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") void runPreview();
                    }}
                    placeholder="例如：帮我做一次生产发布"
                    value={previewQuery}
                  />
                  <button
                    className="inline-flex h-10 shrink-0 items-center gap-2 rounded-xl bg-blue-500 px-4 text-sm font-medium text-white hover:bg-blue-400 disabled:opacity-50"
                    disabled={previewing}
                    onClick={() => void runPreview()}
                    type="button"
                  >
                    {previewing ? (
                      <Loader2 className="animate-spin" size={14} aria-hidden="true" />
                    ) : (
                      "预览"
                    )}
                  </button>
                </div>
                {preview ? (
                  <div className="mt-3 grid gap-2">
                    <p className="text-xs text-(--text-4)">
                      候选 {preview.candidate_count} · 命中 {preview.items.length} · 注入{" "}
                      {preview.total_chars} 字符
                    </p>
                    {preview.items.length ? (
                      preview.items.map((item) => (
                        <div
                          className="rounded-xl border border-(--line) bg-(--surface) p-3"
                          key={item.id}
                        >
                          <div className="flex items-baseline justify-between gap-3">
                            <span className="text-xs font-semibold text-(--accent)">
                              {item.name}（v{item.version}）
                            </span>
                            <span className="text-[11px] text-(--text-4)">
                              相关度 {item.relevance_score.toFixed(2)}
                            </span>
                          </div>
                          <p className="mt-1.5 line-clamp-3 whitespace-pre-wrap text-xs leading-5 text-(--text-4)">
                            {item.instructions}
                          </p>
                        </div>
                      ))
                    ) : (
                      <p className="text-sm text-(--text-4)">
                        没有命中的技能（需要已发布且启用的技能）。
                      </p>
                    )}
                  </div>
                ) : null}
              </div>
            </div>
          ) : (
            <p className="text-sm text-(--text-4)">选择左侧技能，或创建一个新草稿。</p>
          )}
        </section>
      </div>
    </section>
  );
}
