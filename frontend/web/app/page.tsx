"use client";

import { Bot, CheckCircle2, Clock3, PanelLeftOpen, Wifi } from "lucide-react";
import { useEffect, useState } from "react";

import { AppSidebar } from "./components/app-sidebar";
import type { MainView } from "./components/app-sidebar";
import { ChatWorkspace } from "./components/chat-workspace";
import { CommandPalette } from "./components/command-palette";
import { KnowledgeWorkspace } from "./components/knowledge-workspace";
import { SettingsWorkspace } from "./components/settings-workspace";
import { SkillsWorkspace } from "./components/skills-workspace";
import { StatusBadge } from "./components/status-badge";
import { useSessionWorkspace } from "./hooks/use-session-workspace";
import { ApiRequestError, createApiSession, requestApi } from "./lib/api";
import { fetchVncStatus } from "./lib/sandbox-api";
import {
  createSettingsIntegration,
  deleteSettingsIntegration,
  deleteSettingsItem,
  fetchAppSettings,
  updateSettingsItem,
  updateSettingsModule,
} from "./lib/settings-api";
import type {
  AppSettingsData,
  ApiStatusData,
  DatabaseStatusData,
  LoadState,
  StatusBadgeView,
  VncStatusData,
} from "./types";

export default function Home() {
  const [access, setAccess] = useState<"checking" | "allowed" | "locked">(
    "checking",
  );

  useEffect(() => {
    requestApi<DatabaseStatusData>("/api/status/database")
      .then(() => setAccess("allowed"))
      .catch((error) => {
        setAccess(error instanceof ApiRequestError && error.status === 401 ? "locked" : "allowed");
      });
  }, []);

  if (access === "checking") {
    return (
      <main className="grid h-[100dvh] place-items-center bg-(--page) text-sm text-(--text-4)">
        正在验证控制平面…
      </main>
    );
  }
  if (access === "locked") {
    return <AccessGate onAuthenticated={() => setAccess("allowed")} />;
  }
  return <WorkspaceHome />;
}

function AccessGate({ onAuthenticated }: { onAuthenticated: () => void }) {
  const [apiKey, setApiKey] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await createApiSession(apiKey);
      setApiKey("");
      onAuthenticated();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "认证失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-scene relative grid h-[100dvh] place-items-center overflow-hidden px-5">
      {/* 背景：极光光斑 + 渐隐网格，纯装饰。 */}
      <div aria-hidden="true" className="login-aurora login-aurora-a" />
      <div aria-hidden="true" className="login-aurora login-aurora-b" />
      <div aria-hidden="true" className="login-grid" />

      <div className="relative w-full max-w-md">
        <form
          className="palette-in rounded-[28px] border border-white/12 bg-white/6 p-8 shadow-2xl shadow-black/50 backdrop-blur-2xl"
          onSubmit={submit}
        >
          <div className="flex items-center gap-3">
            <div className="brand-gradient squircle flex h-12 w-12 items-center justify-center rounded-2xl border border-white/25 text-white shadow-lg shadow-blue-500/40">
              <Bot size={26} aria-hidden="true" />
            </div>
            <div>
              <div className="text-lg font-bold tracking-wide text-white">
                AtlasAgent
              </div>
              <div className="mt-0.5 text-[11px] uppercase tracking-[0.24em] text-slate-400">
                Agent Control Plane
              </div>
            </div>
          </div>

          <h1 className="mt-7 text-2xl font-semibold text-white">进入控制平面</h1>
          <p className="mt-2 text-sm leading-6 text-slate-400">
            输入启动脚本打印的 API Key。密钥只用于换取 HttpOnly
            会话，不会保存在浏览器存储中。
          </p>

          <label className="mt-6 block text-xs font-medium text-slate-300">
            API Key
            <input
              autoComplete="current-password"
              autoFocus
              className="mt-2 h-12 w-full rounded-xl border border-white/12 bg-black/30 px-4 font-mono text-sm text-white outline-none transition placeholder:text-slate-600 focus:border-blue-400/60 focus:shadow-[0_0_0_3px_rgba(96,165,250,0.15)]"
              onChange={(event) => setApiKey(event.target.value)}
              placeholder="sk-••••••••"
              type="password"
              value={apiKey}
            />
          </label>
          {error ? <p className="mt-3 text-sm text-rose-300">{error}</p> : null}
          <button
            className="brand-gradient sheen-btn mt-6 h-12 w-full rounded-xl text-sm font-semibold text-white shadow-lg shadow-blue-500/30 transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-45"
            disabled={!apiKey || submitting}
            type="submit"
          >
            {submitting ? "验证中…" : "验证并进入"}
          </button>
        </form>
        <p className="mt-5 text-center text-xs text-slate-500">
          可追溯记忆 · 受治理工具 · 可验证恢复
        </p>
      </div>
    </main>
  );
}

function WorkspaceHome() {
  // 命令面板（⌘K）：搜索会话、快速跳转、创建任务。
  const [paletteOpen, setPaletteOpen] = useState(false);
  // 左侧导航可隐藏：隐藏时对话区自动铺满整个宽度，偏好持久化。
  const [sidebarOpen, setSidebarOpen] = useState(true);

  useEffect(() => {
    if (window.localStorage.getItem("atlas-sidebar-open") === "0") {
      setSidebarOpen(false);
    }
  }, []);

  function toggleSidebar() {
    setSidebarOpen((open) => {
      window.localStorage.setItem("atlas-sidebar-open", open ? "0" : "1");
      return !open;
    });
  }

  const [activeView, setActiveView] = useState<MainView>("workspace");
  // API 和数据库属于工作台的基础健康状态。
  // VNC 只在用户点击浏览器工具详情时出现，所以这里只保留连接信息，不再渲染常驻演示面板。
  const [apiStatus, setApiStatus] = useState<LoadState<ApiStatusData>>({
    type: "loading",
  });
  const [databaseStatus, setDatabaseStatus] = useState<
    LoadState<DatabaseStatusData>
  >({ type: "loading" });
  const [vncStatus, setVncStatus] = useState<LoadState<VncStatusData>>({
    type: "loading",
  });
  const [appSettings, setAppSettings] = useState<LoadState<AppSettingsData>>({
    type: "loading",
  });
  const workspace = useSessionWorkspace();

  async function loadStatus() {
    // ===================== 第1步：读取首页真正需要的基础状态 =====================
    // 工作台首页不再加载 MCP、A2A、多 Agent 等演示数据。那些配置属于设置页，
    // 真实对话区只关心 API/数据库健康、VNC 连接信息和应用设置。
    const [
      apiData,
      databaseData,
      vncData,
      appSettingsData,
    ] = await Promise.all([
      requestApi<ApiStatusData>("/api/status"),
      requestApi<DatabaseStatusData>("/api/status/database"),
      fetchVncStatus(),
      fetchAppSettings(),
    ]);
    setApiStatus({ type: "ready", data: apiData });
    setDatabaseStatus({ type: "ready", data: databaseData });
    setVncStatus({ type: "ready", data: vncData });
    setAppSettings({ type: "ready", data: appSettingsData });
  }

  async function refreshAll() {
    // 左侧刷新按钮负责刷新“工作台整体状态”。
    // 会话列表和健康状态一起刷新，避免页面显示旧会话但状态已经变化。
    workspace.setActionError(null);
    try {
      await Promise.all([loadStatus(), workspace.refreshSessions()]);
    } catch (error) {
      const message = error instanceof Error ? error.message : "unknown error";
      setApiStatus((current) =>
        current.type === "loading" ? { type: "error", message } : current,
      );
      setDatabaseStatus((current) =>
        current.type === "loading" ? { type: "error", message } : current,
      );
      setVncStatus((current) =>
        current.type === "loading" ? { type: "error", message } : current,
      );
      setAppSettings((current) =>
        current.type === "loading" ? { type: "error", message } : current,
      );
      workspace.setActionError(message);
    }
  }

  function refreshContext() {
    // 上下文数据只和当前会话相关，没有选中会话时不发请求。
    if (workspace.selectedSessionId) {
      workspace.loadSessionContext(workspace.selectedSessionId);
    }
  }

  useEffect(() => {
    loadStatus().catch((error) => {
      const message = error instanceof Error ? error.message : "unknown error";
      setApiStatus({ type: "error", message });
      setDatabaseStatus({ type: "error", message });
      setVncStatus({ type: "error", message });
      setAppSettings({ type: "error", message });
    });
  }, []);

  async function refreshVnc() {
    setVncStatus({ type: "loading" });
    try {
      const vnc = await fetchVncStatus();
      setVncStatus({ type: "ready", data: vnc });
    } catch (error) {
      const message = error instanceof Error ? error.message : "unknown error";
      setVncStatus({ type: "error", message });
    }
  }

  async function refreshSettings() {
    setAppSettings({ type: "loading" });
    try {
      const settings = await fetchAppSettings();
      setAppSettings({ type: "ready", data: settings });
    } catch (error) {
      const message = error instanceof Error ? error.message : "unknown error";
      setAppSettings({ type: "error", message });
    }
  }

  async function toggleSettingsModule(moduleKey: string, enabled: boolean) {
    try {
      await updateSettingsModule(moduleKey, { enabled });
      await refreshSettings();
    } catch (error) {
      const message = error instanceof Error ? error.message : "unknown error";
      setAppSettings({ type: "error", message });
    }
  }

  async function addSettingsIntegration(payload: {
    kind: string;
    name: string;
    description: string;
    endpoint: string;
  }) {
    try {
      await createSettingsIntegration(payload);
      await refreshSettings();
    } catch (error) {
      const message = error instanceof Error ? error.message : "unknown error";
      setAppSettings({ type: "error", message });
    }
  }

  async function removeSettingsIntegration(integrationId: string) {
    try {
      await deleteSettingsIntegration(integrationId);
      await refreshSettings();
    } catch (error) {
      const message = error instanceof Error ? error.message : "unknown error";
      setAppSettings({ type: "error", message });
    }
  }

  async function toggleSettingsItem(
    moduleKey: string,
    itemName: string,
    enabled: boolean,
  ) {
    try {
      await updateSettingsItem(moduleKey, itemName, { enabled });
      await refreshSettings();
    } catch (error) {
      const message = error instanceof Error ? error.message : "unknown error";
      setAppSettings({ type: "error", message });
    }
  }

  async function removeSettingsItem(moduleKey: string, itemName: string) {
    try {
      await deleteSettingsItem(moduleKey, itemName);
      await refreshSettings();
    } catch (error) {
      const message = error instanceof Error ? error.message : "unknown error";
      setAppSettings({ type: "error", message });
    }
  }

  const apiBadge = getBadge(apiStatus, "API 正常", "API 异常");
  const dbBadge = getBadge(databaseStatus, "数据库正常", "数据库异常");

  return (
    <main className="relative h-[100dvh] overflow-hidden bg-(--page) text-(--text-1)">
      <CommandPalette
        onClose={() => setPaletteOpen(false)}
        onCreateSession={() => {
          workspace.createSession();
          setActiveView("workspace");
        }}
        onSelectSession={(sessionId) => {
          workspace.selectSession(sessionId);
          setActiveView("workspace");
        }}
        onToggle={() => setPaletteOpen((open) => !open)}
        onViewChange={setActiveView}
        open={paletteOpen}
        sessions={workspace.sessionItems}
      />
      {!sidebarOpen ? (
        <button
          aria-label="展开侧边栏"
          className="absolute left-3 top-3 z-50 flex h-9 w-9 items-center justify-center rounded-xl border border-(--line) bg-(--surface-3)/90 text-(--text-3) shadow-lg shadow-black/20 backdrop-blur-xl transition hover:border-(--accent)/40 hover:text-(--text-1)"
          onClick={toggleSidebar}
          title="展开侧边栏"
          type="button"
        >
          <PanelLeftOpen size={17} aria-hidden="true" />
        </button>
      ) : null}
      <div
        className={`grid h-full min-h-0 ${
          sidebarOpen
            ? "grid-cols-[300px_1fr] max-lg:grid-cols-1 max-lg:grid-rows-[auto_1fr]"
            : "grid-cols-1"
        }`}
      >
        {sidebarOpen ? (
          <AppSidebar
            actionError={workspace.actionError}
            activeView={activeView}
            onCollapse={toggleSidebar}
            onOpenPalette={() => setPaletteOpen(true)}
            onCreateSession={(dir, full) => workspace.createSession(dir, full)}
            onDeleteSession={workspace.deleteSession}
            onRefresh={refreshAll}
            onSelectSession={workspace.selectSession}
            onViewChange={setActiveView}
            selectedSessionId={workspace.selectedSessionId}
            sessions={workspace.sessions}
            submitting={workspace.submitting}
          />
        ) : null}

        <section className="agent-grid-bg flex min-h-0 min-w-0 flex-col overflow-hidden bg-(--page)">
          {activeView === "settings" ? (
            <header className="flex min-h-24 items-center justify-between border-b border-(--line) bg-(--page)/80 px-8 backdrop-blur-2xl max-sm:flex-col max-sm:items-start max-sm:gap-3 max-sm:px-4 max-sm:py-4">
              <div>
                <div className="mb-2 text-xs font-medium uppercase tracking-[0.2em] text-(--accent)/80">
                  Control Center
                </div>
                <h1 className="text-3xl font-semibold tracking-normal text-(--text-1) max-sm:text-2xl">
                  设置
                </h1>
                <p className="mt-2 text-sm text-(--text-4)">
                  集中管理模型、工具、远程 Agent 和多 Agent 配置
                </p>
              </div>
              <div className="flex gap-2 max-sm:flex-wrap">
                <StatusBadge badge={apiBadge} />
                <StatusBadge badge={dbBadge} />
              </div>
            </header>
          ) : null}

          <div
            className={`min-h-0 flex-1 ${
              activeView === "workspace"
                ? "overflow-hidden p-0"
                : "overflow-y-auto p-5 max-md:p-3"
            }`}
          >
            {activeView === "workspace" ? (
              <ChatWorkspace
                attachments={workspace.attachments}
                clearingUnread={workspace.clearingUnread}
                context={workspace.context}
                draft={workspace.draft}
                events={workspace.events}
                files={workspace.files}
                filePreview={workspace.filePreview}
                liveAnswer={workspace.liveAnswer}
                liveThinking={workspace.liveThinking}
                messages={workspace.messages}
                onClearUnread={workspace.clearUnread}
                onDraftChange={workspace.setDraft}
                onPreviewFile={workspace.loadFilePreview}
                onRefreshContext={refreshContext}
                onRefreshVnc={refreshVnc}
                onSend={workspace.sendMessage}
                onSelectFile={workspace.selectFile}
                onStop={workspace.stopSession}
                onUploadFile={workspace.uploadAttachment}
                onDeleteFile={workspace.deleteAttachment}
                onRetry={workspace.retryLastMessage}
                executingPlan={workspace.executingPlan}
                plan={workspace.latestPlan}
                planning={workspace.planning}
                task={workspace.currentTask}
                vnc={vncStatus}
                selectedFile={workspace.selectedFile}
                selectedSession={workspace.selectedSession}
                sending={workspace.sendingMessage}
                stopping={workspace.stoppingSession}
                uploadingFile={workspace.uploadingFile}
                deletingFileId={workspace.deletingFileId}
              />
            ) : null}
            {activeView === "settings" ? (
              <SettingsWorkspace
                onCreateIntegration={addSettingsIntegration}
                onDeleteIntegration={removeSettingsIntegration}
                onDeleteItem={removeSettingsItem}
                onRefresh={refreshSettings}
                onToggleItem={toggleSettingsItem}
                onToggleModule={toggleSettingsModule}
                settings={appSettings}
              />
            ) : null}
            {activeView === "knowledge" ? <KnowledgeWorkspace /> : null}
            {activeView === "skills" ? <SkillsWorkspace /> : null}
          </div>
        </section>
      </div>
    </main>
  );
}

function getBadge<T>(
  state: LoadState<T>,
  readyLabel: string,
  errorLabel: string,
): StatusBadgeView {
  if (state.type === "ready") {
    return {
      label: readyLabel,
      className: "border-emerald-200 bg-emerald-50 text-emerald-700",
      icon: CheckCircle2,
    };
  }
  if (state.type === "error") {
    return {
      label: errorLabel,
      className: "border-rose-200 bg-rose-50 text-rose-700",
      icon: Wifi,
    };
  }
  return {
    label: "检测中",
    className: "border-slate-200 bg-white text-slate-600",
    icon: Clock3,
  };
}
