"use client";

import {
  BookOpenText,
  Bot,
  PanelLeftClose,
  Plus,
  Puzzle,
  RefreshCw,
  Search,
  Settings,
} from "lucide-react";
import { useLayoutEffect, useRef, useState } from "react";

import { SessionList } from "./session-list";
import { ThemeMenu } from "./theme-menu";
import { workspaceSurface } from "../lib/design-tokens";
import type { LoadState, SessionItem } from "../types";

/** 主区域可切换的视图。 */
export type MainView = "workspace" | "settings" | "knowledge" | "skills";

type AppSidebarProps = {
  actionError: string | null;
  activeView: MainView;
  onCollapse: () => void;
  onOpenPalette: () => void;
  onCreateSession: () => void;
  onDeleteSession: (sessionId: string) => void;
  onRefresh: () => void;
  onViewChange: (view: MainView) => void;
  onSelectSession: (sessionId: string) => void;
  selectedSessionId: string | null;
  sessions: LoadState<SessionItem[]>;
  submitting: boolean;
};

export function AppSidebar({
  actionError,
  activeView,
  onCollapse,
  onOpenPalette,
  onCreateSession,
  onDeleteSession,
  onRefresh,
  onViewChange,
  onSelectSession,
  selectedSessionId,
  sessions,
  submitting,
}: AppSidebarProps) {
  // 工作区切换的滑动指示器：测量激活按钮的位置，让渐变胶囊平滑滑过去。
  const railRef = useRef<HTMLDivElement | null>(null);
  const viewButtonRefs = useRef(new Map<MainView, HTMLButtonElement | null>());
  const [pill, setPill] = useState<{
    left: number;
    top: number;
    width: number;
    height: number;
  } | null>(null);

  useLayoutEffect(() => {
    function measure() {
      const rail = railRef.current;
      const element = viewButtonRefs.current.get(activeView);
      if (!rail || !element) {
        setPill(null);
        return;
      }
      const railRect = rail.getBoundingClientRect();
      const rect = element.getBoundingClientRect();
      setPill({
        left: rect.left - railRect.left,
        top: rect.top - railRect.top,
        width: rect.width,
        height: rect.height,
      });
    }
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [activeView]);

  const registerViewButton = (view: MainView) => (element: HTMLButtonElement | null) => {
    viewButtonRefs.current.set(view, element);
  };

  return (
    <aside className="cockpit flex h-screen min-h-0 flex-col overflow-hidden border-r border-(--line) px-4 py-5 max-lg:h-auto max-lg:max-h-[40dvh] max-lg:border-b max-lg:border-r-0 max-sm:max-h-[34dvh] max-sm:px-4 max-sm:py-4">
      <div className="flex shrink-0 items-center gap-3 px-2">
        <div className="brand-gradient squircle flex h-10 w-10 items-center justify-center rounded-xl border border-white/25 text-white shadow-lg shadow-blue-500/40">
          <Bot size={22} aria-hidden="true" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="brand-title text-base font-bold leading-5 tracking-wide">
            AtlasAgent
          </div>
          <div className="mt-1 text-[11px] uppercase tracking-[0.22em] text-(--text-4)">
            Agent Workspace
          </div>
        </div>
        <button
          aria-label="隐藏侧边栏"
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-(--text-4) transition hover:bg-(--fill-2) hover:text-(--text-1)"
          onClick={onCollapse}
          title="隐藏侧边栏"
          type="button"
        >
          <PanelLeftClose size={17} aria-hidden="true" />
        </button>
      </div>

      <button
        className="mt-4 flex w-full shrink-0 items-center gap-2 rounded-xl border border-(--line) bg-(--fill-1) px-3 py-2 text-sm text-(--text-4) transition hover:border-(--line-strong) hover:text-(--text-2)"
        onClick={onOpenPalette}
        type="button"
      >
        <Search size={15} aria-hidden="true" />
        <span className="flex-1 text-left">搜索或跳转…</span>
        <kbd className="rounded-md border border-(--line) bg-(--fill-2) px-1.5 py-0.5 text-[10px] font-semibold tracking-wide">
          ⌘K
        </kbd>
      </button>

      <div
        className={`relative mt-4 flex shrink-0 items-center justify-between rounded-2xl px-3 py-2 max-sm:mt-3 ${workspaceSurface.panel}`}
        ref={railRef}
      >
        {/* 滑动指示器：渐变胶囊滑向当前激活视图（Originkit animated tabs 模式）。 */}
        {pill ? (
          <span
            aria-hidden="true"
            className="nav-pill brand-gradient squircle"
            style={{
              left: pill.left,
              top: pill.top,
              width: pill.width,
              height: pill.height,
            }}
          />
        ) : null}
        <button
          aria-label="切换到对话工作台"
          className={`relative rounded-full px-3 py-1.5 text-sm font-medium transition ${
            activeView === "workspace"
              ? "text-white"
              : "text-(--text-4) hover:text-(--text-1)"
          }`}
          onClick={() => onViewChange("workspace")}
          ref={registerViewButton("workspace")}
          type="button"
        >
          对话
        </button>
        <div className="flex items-center gap-1">
          <button
            aria-label="知识库管理"
            className={`relative flex h-8 w-8 items-center justify-center rounded-full transition ${
              activeView === "knowledge"
                ? "text-white"
                : "text-(--text-5) hover:bg-(--fill-2) hover:text-(--text-1)"
            }`}
            onClick={() => onViewChange("knowledge")}
            ref={registerViewButton("knowledge")}
            title="知识库（RAG）"
            type="button"
          >
            <BookOpenText size={15} aria-hidden="true" />
          </button>
          <button
            aria-label="技能注册中心"
            className={`relative flex h-8 w-8 items-center justify-center rounded-full transition ${
              activeView === "skills"
                ? "text-white"
                : "text-(--text-5) hover:bg-(--fill-2) hover:text-(--text-1)"
            }`}
            onClick={() => onViewChange("skills")}
            ref={registerViewButton("skills")}
            title="技能注册中心"
            type="button"
          >
            <Puzzle size={15} aria-hidden="true" />
          </button>
          <ThemeMenu />
          <button
            aria-label="打开设置"
            className={`relative flex h-8 w-8 items-center justify-center rounded-full transition ${
              activeView === "settings"
                ? "text-white"
                : "text-(--text-5) hover:bg-(--fill-2) hover:text-(--text-1)"
            }`}
            onClick={() => onViewChange("settings")}
            ref={registerViewButton("settings")}
            title="设置"
            type="button"
          >
            <Settings size={15} aria-hidden="true" />
          </button>
        </div>
      </div>

      <button
        className="brand-gradient sheen-btn mt-6 flex h-10 w-full shrink-0 items-center justify-center gap-2 rounded-xl text-sm font-semibold text-white shadow-lg shadow-blue-500/30 transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50 max-sm:mt-4"
        disabled={submitting}
        onClick={onCreateSession}
        title="新建工作区"
        type="button"
      >
        <Plus size={18} aria-hidden="true" />
        新建工作区
      </button>

      <div className="mt-6 flex shrink-0 items-center justify-between max-sm:mt-4">
        <div className="flex items-center gap-2">
          <span className="brand-gradient h-3.5 w-[3px] rounded-full" />
          <span className="text-xs font-semibold uppercase tracking-[0.2em] text-(--text-3)">
            任务列表
          </span>
        </div>
        <button
          aria-label="刷新任务列表"
          className="flex h-8 w-8 items-center justify-center rounded-md text-(--text-4) transition hover:bg-(--fill-2) hover:text-(--text-1)"
          onClick={onRefresh}
          title="刷新"
          type="button"
        >
          <RefreshCw size={16} aria-hidden="true" />
        </button>
      </div>

      <SessionList
        onDelete={onDeleteSession}
        onSelect={onSelectSession}
        selectedId={selectedSessionId}
        state={sessions}
      />

      {actionError ? (
        <div className="mt-4 shrink-0 rounded-md border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
          {actionError}
        </div>
      ) : null}
    </aside>
  );
}
