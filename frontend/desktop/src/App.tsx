import "@fontsource-variable/inter";
import {
  Books,
  ChatCircleDots,
  Cube,
  Gear,
  GitBranch,
  ListChecks,
  Play,
  PuzzlePiece,
  RocketLaunch,
  TerminalWindow,
} from "@phosphor-icons/react";
import type { Icon } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { atlasRequest } from "./api";
import { ChatView } from "./views/ChatView";
import { KnowledgeView } from "./views/KnowledgeView";
import { SkillsView } from "./views/SkillsView";
import { TasksView } from "./views/TasksView";
import type { ApiState, Theme, WorkspaceView } from "./types";

function isTheme(value: string | null): value is Theme {
  return value === "ink" || value === "dawn" || value === "contrast";
}

function useTheme(): [Theme, Dispatch<SetStateAction<Theme>>] {
  const [theme, setTheme] = useState<Theme>(() => {
    const savedTheme = localStorage.getItem("atlas-theme");
    return isTheme(savedTheme) ? savedTheme : "ink";
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("atlas-theme", theme);
  }, [theme]);
  return [theme, setTheme];
}

interface IconRailProps {
  apiState: ApiState;
  view: WorkspaceView;
  onNavigate: (view: WorkspaceView) => void;
}

export function App() {
  const [theme, setTheme] = useTheme();
  const [view, setView] = useState<WorkspaceView>("chat");
  const [apiState, setApiState] = useState<ApiState>("checking");

  // 应用启动即探测 /api/status（免认证），指示灯不依赖任何具体视图。
  useEffect(() => {
    let disposed = false;
    atlasRequest("/api/status")
      .then(() => {
        if (!disposed) setApiState("connected");
      })
      .catch(() => {
        if (!disposed) setApiState("offline");
      });
    return () => {
      disposed = true;
    };
  }, []);

  return (
    <main className="atlas-shell">
      <IconRail apiState={apiState} view={view} onNavigate={setView} />
      {view === "chat" ? (
        <ChatView theme={theme} setTheme={setTheme} onApiState={setApiState} />
      ) : null}
      {view === "tasks" ? (
        <TasksView theme={theme} setTheme={setTheme} onApiState={setApiState} />
      ) : null}
      {view === "skills" ? <SkillsView theme={theme} setTheme={setTheme} /> : null}
      {view === "knowledge" ? <KnowledgeView theme={theme} setTheme={setTheme} /> : null}
    </main>
  );
}

function IconRail({ apiState, view, onNavigate }: IconRailProps) {
  const navigable: Array<{ icon: Icon; label: string; target: WorkspaceView }> = [
    { icon: ChatCircleDots, label: "对话", target: "chat" },
    { icon: Play, label: "任务", target: "tasks" },
    { icon: PuzzlePiece, label: "技能", target: "skills" },
    { icon: Books, label: "知识库", target: "knowledge" },
  ];
  const placeholders: Array<[Icon, string]> = [
    [ListChecks, "运行记录"],
    [GitBranch, "事件关系"],
    [Cube, "制品"],
    [TerminalWindow, "终端"],
    [Gear, "设置"],
  ];
  return (
    <nav className="icon-rail" aria-label="主导航">
      <button className="brand-mark" type="button" aria-label="AtlasAgent 首页" onClick={() => onNavigate("chat")}>
        <RocketLaunch size={27} weight="fill" />
      </button>
      <div className="rail-divider" />
      <div className="rail-items">
        {navigable.map(({ icon: ItemIcon, label, target }) => (
          <button
            key={label}
            className={`rail-button ${view === target ? "active" : ""}`}
            type="button"
            aria-label={label}
            aria-current={view === target ? "page" : undefined}
            title={label}
            onClick={() => onNavigate(target)}
          >
            <ItemIcon size={22} weight={view === target ? "fill" : "regular"} />
          </button>
        ))}
        <div className="rail-divider" />
        {placeholders.map(([ItemIcon, label]) => (
          <button
            key={label}
            className="rail-button placeholder"
            type="button"
            disabled
            aria-label={`${label}（暂未开放，请使用 Web 端）`}
            title={`${label}（暂未开放，请使用 Web 端）`}
          >
            <ItemIcon size={22} weight="regular" />
          </button>
        ))}
      </div>
      <div
        className={`api-indicator ${apiState}`}
        title={apiState === "connected" ? "API 已连接" : apiState === "offline" ? "API 未连接" : "正在检测 API"}
      >
        <span />
      </div>
    </nav>
  );
}
