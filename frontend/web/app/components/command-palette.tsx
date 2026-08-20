"use client";

import {
  BookOpenText,
  CornerDownLeft,
  MessageSquare,
  Monitor,
  Moon,
  Plus,
  Puzzle,
  Search,
  Settings,
  Sun,
} from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";

import type { MainView } from "./app-sidebar";
import { useThemePreference } from "../lib/theme";
import type { SessionItem } from "../types";

type PaletteItem = {
  id: string;
  group: string;
  label: string;
  icon: ReactNode;
  run: () => void;
};

type CommandPaletteProps = {
  open: boolean;
  onClose: () => void;
  /** ⌘K / Ctrl+K 全局切换开合。 */
  onToggle: () => void;
  sessions: SessionItem[];
  onSelectSession: (sessionId: string) => void;
  onCreateSession: () => void;
  onViewChange: (view: MainView) => void;
};

/**
 * 命令面板（⌘K）：搜索会话、快速跳转视图、切换主题、按输入创建任务。
 * 键盘优先：↑↓ 选择、Enter 执行、Esc 关闭。
 */
export function CommandPalette({
  open,
  onClose,
  onToggle,
  sessions,
  onSelectSession,
  onCreateSession,
  onViewChange,
}: CommandPaletteProps) {
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [, setThemePreference] = useThemePreference();

  const items = useMemo<PaletteItem[]>(() => {
    const keyword = query.trim().toLowerCase();
    const matched: PaletteItem[] = [];

    const sessionHits = sessions
      .filter((session) =>
        keyword ? session.title.toLowerCase().includes(keyword) : true,
      )
      .slice(0, keyword ? 8 : 6);
    for (const session of sessionHits) {
      matched.push({
        id: `session-${session.id}`,
        group: "会话",
        label: session.title,
        icon: <MessageSquare size={15} aria-hidden="true" />,
        run: () => onSelectSession(session.id),
      });
    }

    if (keyword) {
      matched.push({
        id: "create-session",
        group: "操作",
        label: "新建工作区",
        icon: <Plus size={15} aria-hidden="true" />,
        run: () => onCreateSession(),
      });
    }

    const navigation: Array<[MainView, string, ReactNode]> = [
      ["workspace", "回到对话", <MessageSquare key="w" size={15} aria-hidden="true" />],
      ["knowledge", "打开知识库", <BookOpenText key="k" size={15} aria-hidden="true" />],
      ["skills", "打开技能中心", <Puzzle key="s" size={15} aria-hidden="true" />],
      ["settings", "打开设置", <Settings key="c" size={15} aria-hidden="true" />],
    ];
    for (const [view, label, icon] of navigation) {
      if (!keyword || label.toLowerCase().includes(keyword)) {
        matched.push({
          id: `view-${view}`,
          group: "操作",
          label,
          icon,
          run: () => onViewChange(view),
        });
      }
    }

    const themes: Array<["light" | "dark" | "system", string, ReactNode]> = [
      ["light", "主题：亮色", <Sun key="l" size={15} aria-hidden="true" />],
      ["dark", "主题：暗色", <Moon key="d" size={15} aria-hidden="true" />],
      ["system", "主题：跟随系统", <Monitor key="m" size={15} aria-hidden="true" />],
    ];
    for (const [preference, label, icon] of themes) {
      if (!keyword || label.toLowerCase().includes(keyword) || "主题".includes(keyword)) {
        matched.push({
          id: `theme-${preference}`,
          group: "主题",
          label,
          icon,
          run: () => setThemePreference(preference),
        });
      }
    }

    return matched;
  }, [query, sessions, onSelectSession, onCreateSession, onViewChange, setThemePreference]);

  // 打开时重置并聚焦；列表变化时收敛选中项。
  useEffect(() => {
    if (open) {
      setQuery("");
      setActiveIndex(0);
      window.setTimeout(() => inputRef.current?.focus(), 30);
    }
  }, [open]);

  useEffect(() => {
    setActiveIndex((index) => Math.min(index, Math.max(items.length - 1, 0)));
  }, [items.length]);

  // 全局快捷键：⌘K / Ctrl+K 开合；打开时接管方向键与回车。
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        onToggle();
        return;
      }
      if (!open) {
        return;
      }
      if (event.key === "Escape") {
        onClose();
      } else if (event.key === "ArrowDown") {
        event.preventDefault();
        setActiveIndex((index) => (index + 1) % Math.max(items.length, 1));
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setActiveIndex(
          (index) => (index - 1 + Math.max(items.length, 1)) % Math.max(items.length, 1),
        );
      } else if (event.key === "Enter") {
        event.preventDefault();
        const item = items[activeIndex];
        if (item) {
          item.run();
          onClose();
        }
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, items, activeIndex, onClose, onToggle]);

  if (!open) {
    return null;
  }

  let lastGroup = "";
  return (
    <div
      aria-modal="true"
      className="fixed inset-0 z-[80] flex items-start justify-center bg-black/45 px-4 pt-[14dvh] backdrop-blur-sm"
      onClick={onClose}
      role="dialog"
    >
      <div
        className="palette-in w-full max-w-lg overflow-hidden rounded-2xl border border-(--line) bg-(--surface-3)/95 shadow-2xl shadow-black/50 backdrop-blur-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center gap-2.5 border-b border-(--line-soft) px-4">
          <Search aria-hidden="true" className="shrink-0 text-(--text-4)" size={16} />
          <input
            aria-label="搜索会话或输入命令"
            className="h-12 w-full bg-transparent text-sm text-(--text-1) outline-none placeholder:text-(--text-5)"
            onChange={(event) => {
              setQuery(event.target.value);
              setActiveIndex(0);
            }}
            placeholder="搜索会话，或输入命令…"
            ref={inputRef}
            value={query}
          />
          <kbd className="shrink-0 rounded-md border border-(--line) bg-(--fill-1) px-1.5 py-0.5 text-[10px] font-semibold text-(--text-4)">
            Esc
          </kbd>
        </div>
        <div className="max-h-[46dvh] overflow-y-auto p-2">
          {items.length === 0 ? (
            <div className="px-3 py-8 text-center text-sm text-(--text-4)">
              没有匹配的结果
            </div>
          ) : (
            items.map((item, index) => {
              const showGroup = item.group !== lastGroup;
              lastGroup = item.group;
              return (
                <div key={item.id}>
                  {showGroup ? (
                    <div className="px-3 pb-1 pt-2.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-(--text-5)">
                      {item.group}
                    </div>
                  ) : null}
                  <button
                    className={`flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-left text-sm transition ${
                      index === activeIndex
                        ? "bg-(--accent)/14 text-(--text-1)"
                        : "text-(--text-3) hover:bg-(--fill-1)"
                    }`}
                    onClick={() => {
                      item.run();
                      onClose();
                    }}
                    onMouseEnter={() => setActiveIndex(index)}
                    type="button"
                  >
                    <span className="text-(--text-4)">{item.icon}</span>
                    <span className="min-w-0 flex-1 truncate">{item.label}</span>
                    {index === activeIndex ? (
                      <CornerDownLeft
                        aria-hidden="true"
                        className="shrink-0 text-(--text-5)"
                        size={13}
                      />
                    ) : null}
                  </button>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
