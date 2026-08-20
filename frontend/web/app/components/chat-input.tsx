"use client";

import { Loader2, SendHorizontal, X, Zap } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { workspaceSurface } from "../lib/design-tokens";
import { fetchSkills } from "../lib/skills-api";
import type { Skill } from "../lib/skills-api";

type ChatInputProps = {
  disabled: boolean;
  draft: string;
  onDraftChange: (value: string) => void;
  onSend: (skillIds: string[]) => void;
  sending: boolean;
};

const MAX_INPUT_HEIGHT = 176;

export function ChatInput({
  disabled,
  draft,
  onDraftChange,
  onSend,
  sending,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  // 输入 / 触发技能选择：已发布且启用的技能，按名称/键名过滤。
  const [skills, setSkills] = useState<Skill[]>([]);
  const [skillsLoaded, setSkillsLoaded] = useState(false);
  const [pickerIndex, setPickerIndex] = useState(0);
  const [selectedSkills, setSelectedSkills] = useState<Skill[]>([]);

  const slashQuery = draft.startsWith("/")
    ? draft.slice(1).trim().toLowerCase()
    : null;
  const pickerOpen = slashQuery !== null && !disabled && !sending;

  useEffect(() => {
    if (!pickerOpen || skillsLoaded) {
      return;
    }
    fetchSkills({ status: "published" })
      .then((data) => setSkills(data.items.filter((skill) => skill.enabled)))
      .catch(() => setSkills([]))
      .finally(() => setSkillsLoaded(true));
  }, [pickerOpen, skillsLoaded]);

  const pickerItems = useMemo(() => {
    if (!pickerOpen) {
      return [];
    }
    return skills
      .filter((skill) => !selectedSkills.some((item) => item.id === skill.id))
      .filter(
        (skill) =>
          !slashQuery ||
          skill.name.toLowerCase().includes(slashQuery) ||
          skill.skill_key.toLowerCase().includes(slashQuery),
      )
      .slice(0, 6);
  }, [pickerOpen, skills, selectedSkills, slashQuery]);

  useEffect(() => {
    setPickerIndex(0);
  }, [slashQuery]);

  // 随内容自动伸缩：先归零再按内容高度设置，超过上限后内部滚动。
  useEffect(() => {
    const element = textareaRef.current;
    if (!element) {
      return;
    }
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, MAX_INPUT_HEIGHT)}px`;
    element.style.overflowY =
      element.scrollHeight > MAX_INPUT_HEIGHT ? "auto" : "hidden";
  }, [draft]);

  function chooseSkill(skill: Skill) {
    setSelectedSkills((list) => [...list, skill]);
    onDraftChange("");
    textareaRef.current?.focus();
  }

  function submit() {
    if (disabled || sending || !draft.trim()) {
      return;
    }
    onSend(selectedSkills.map((skill) => skill.id));
    setSelectedSkills([]);
  }

  return (
    <form
      className="mx-auto max-w-5xl"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      {selectedSkills.length ? (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {selectedSkills.map((skill) => (
            <span
              className="inline-flex items-center gap-1.5 rounded-full border border-(--accent)/30 bg-(--accent)/10 px-2.5 py-1 text-xs font-medium text-(--accent)"
              key={skill.id}
            >
              <Zap size={11} aria-hidden="true" />
              {skill.name}
              <button
                aria-label={`移除技能 ${skill.name}`}
                className="text-(--accent)/70 transition hover:text-(--accent)"
                onClick={() =>
                  setSelectedSkills((list) =>
                    list.filter((item) => item.id !== skill.id),
                  )
                }
                type="button"
              >
                <X size={11} aria-hidden="true" />
              </button>
            </span>
          ))}
        </div>
      ) : null}
      <div
        className={`aurora-shell ${sending ? "aurora-active" : ""} flex items-end gap-2 rounded-3xl p-2 pl-5 ring-1 ring-(--accent)/15 max-sm:pl-4 ${workspaceSurface.panelStrong}`}
      >
        {/* 聚焦或发送中时，底部浮起的极光光带。 */}
        <span aria-hidden="true" className="aurora-veil" />
        {pickerOpen ? (
          <div className="palette-in absolute bottom-full left-0 right-0 z-30 mb-2 overflow-hidden rounded-2xl border border-(--line) bg-(--surface-3)/95 shadow-2xl shadow-black/40 backdrop-blur-xl">
            <div className="border-b border-(--line-soft) px-4 py-2 text-[11px] text-(--text-5)">
              选择技能注入本轮对话 — ↑↓ 选择 · Enter 确认 · Esc 取消
            </div>
            <div className="max-h-60 overflow-y-auto p-1.5">
              {!skillsLoaded ? (
                <div className="px-3 py-4 text-sm text-(--text-4)">加载技能中…</div>
              ) : pickerItems.length === 0 ? (
                <div className="px-3 py-4 text-sm text-(--text-4)">
                  没有匹配的已发布技能，可在「技能中心」创建并发布。
                </div>
              ) : (
                pickerItems.map((skill, index) => (
                  <button
                    className={`flex w-full items-start gap-2.5 rounded-xl px-3 py-2 text-left transition ${
                      index === pickerIndex
                        ? "bg-(--accent)/14"
                        : "hover:bg-(--fill-1)"
                    }`}
                    key={skill.id}
                    onClick={() => chooseSkill(skill)}
                    onMouseEnter={() => setPickerIndex(index)}
                    type="button"
                  >
                    <Zap
                      aria-hidden="true"
                      className="mt-1 shrink-0 text-(--accent)"
                      size={13}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="flex items-baseline gap-2">
                        <span className="text-sm font-semibold text-(--text-1)">
                          {skill.name}
                        </span>
                        <span className="truncate text-[11px] text-(--text-5)">
                          /{skill.skill_key} · v{skill.version}
                        </span>
                      </span>
                      <span className="mt-0.5 line-clamp-1 text-xs text-(--text-4)">
                        {skill.description || skill.instructions}
                      </span>
                    </span>
                  </button>
                ))
              )}
            </div>
          </div>
        ) : null}
        <textarea
          aria-label="任务输入框"
          className="w-full flex-1 resize-none border-0 bg-transparent py-2.5 text-base font-medium leading-6 text-(--text-1) outline-none placeholder:text-(--text-5) disabled:bg-transparent max-sm:py-2 max-sm:text-sm"
          disabled={disabled || sending}
          onChange={(event) => onDraftChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.nativeEvent.isComposing) {
              return;
            }
            // 技能选择浮层打开时接管键盘：↑↓ 移动、Enter 选中、Esc 取消。
            if (pickerOpen) {
              if (event.key === "ArrowDown" && pickerItems.length) {
                event.preventDefault();
                setPickerIndex((index) => (index + 1) % pickerItems.length);
                return;
              }
              if (event.key === "ArrowUp" && pickerItems.length) {
                event.preventDefault();
                setPickerIndex(
                  (index) => (index - 1 + pickerItems.length) % pickerItems.length,
                );
                return;
              }
              if (event.key === "Enter" && pickerItems.length) {
                event.preventDefault();
                chooseSkill(pickerItems[pickerIndex]);
                return;
              }
              if (event.key === "Escape") {
                event.preventDefault();
                onDraftChange("");
                return;
              }
            }
            // Enter 直接发送，Shift+Enter 换行。
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
          placeholder={
            disabled
              ? "先创建或选择一个会话"
              : "分配一个任务或提问任何问题，输入 / 调用技能..."
          }
          ref={textareaRef}
          rows={1}
          value={draft}
        />
        <button
          aria-label={sending ? "任务执行中" : "发送任务"}
          className="sheen-btn mb-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-(--line) bg-(--fill-2) text-(--text-1) shadow-lg shadow-black/30 transition hover:border-(--accent)/40 hover:bg-blue-500 disabled:cursor-not-allowed disabled:bg-(--fill-1) disabled:text-(--text-5) disabled:shadow-none max-sm:h-9 max-sm:w-9"
          disabled={disabled || sending || !draft.trim()}
          title={sending ? "任务执行中" : "发送并开始执行（Enter）"}
          type="submit"
        >
          {sending ? (
            <Loader2 className="animate-spin" size={19} aria-hidden="true" />
          ) : (
            <SendHorizontal size={19} aria-hidden="true" />
          )}
        </button>
      </div>
    </form>
  );
}
