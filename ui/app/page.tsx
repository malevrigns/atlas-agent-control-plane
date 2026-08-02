"use client";

import { CheckCircle2, Clock3, Wifi } from "lucide-react";
import { useEffect, useState } from "react";

import { AppSidebar } from "./components/app-sidebar";
import { ChatWorkspace } from "./components/chat-workspace";
import { SettingsWorkspace } from "./components/settings-workspace";
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
      <main className="grid h-[100dvh] place-items-center bg-[#050506] text-sm text-zinc-500">
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
    <main className="grid h-[100dvh] place-items-center bg-[#050506] px-5 text-zinc-50">
      <form className="w-full max-w-md rounded-3xl border border-white/10 bg-white/[0.04] p-8 shadow-2xl" onSubmit={submit}>
        <div className="text-xs font-medium uppercase tracking-[0.22em] text-blue-400">AtlasAgent</div>
        <h1 className="mt-3 text-3xl font-semibold">进入控制平面</h1>
        <p className="mt-3 text-sm leading-6 text-zinc-500">
          输入启动脚本生成的 API Key。密钥只用于换取 HttpOnly 会话，不会保存在浏览器存储中。
        </p>
        <label className="mt-6 block text-xs font-medium text-zinc-400">
          API Key
          <input
            autoComplete="current-password"
            autoFocus
            className="mt-2 h-12 w-full rounded-xl border border-white/10 bg-black/40 px-4 font-mono text-sm outline-none focus:border-blue-500/70"
            onChange={(event) => setApiKey(event.target.value)}
            type="password"
            value={apiKey}
          />
        </label>
        {error ? <p className="mt-3 text-sm text-rose-300">{error}</p> : null}
        <button
          className="mt-5 h-11 w-full rounded-xl bg-blue-500 text-sm font-semibold transition hover:bg-blue-400 disabled:opacity-50"
          disabled={!apiKey || submitting}
          type="submit"
        >
          {submitting ? "验证中…" : "验证并进入"}
        </button>
      </form>
    </main>
  );
}

function WorkspaceHome() {
  const [activeView, setActiveView] = useState<"workspace" | "settings">(
    "workspace",
  );
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
    <main className="h-[100dvh] overflow-hidden bg-[#050506] text-zinc-50">
      <div className="grid h-full min-h-0 grid-cols-[300px_1fr] max-lg:grid-cols-1 max-lg:grid-rows-[auto_1fr]">
        <AppSidebar
          actionError={workspace.actionError}
          activeView={activeView}
          onCreateSession={workspace.createSession}
          onDeleteSession={workspace.deleteSession}
          onRefresh={refreshAll}
          onSelectSession={workspace.selectSession}
          onViewChange={setActiveView}
          onTitleChange={workspace.setTitle}
          selectedSessionId={workspace.selectedSessionId}
          sessions={workspace.sessions}
          submitting={workspace.submitting}
          title={workspace.title}
        />

        <section className="agent-grid-bg flex min-h-0 min-w-0 flex-col overflow-hidden bg-[#05060a]">
          {activeView === "settings" ? (
            <header className="flex min-h-24 items-center justify-between border-b border-white/10 bg-[#05060a]/80 px-8 backdrop-blur-2xl max-sm:flex-col max-sm:items-start max-sm:gap-3 max-sm:px-4 max-sm:py-4">
              <div>
                <div className="mb-2 text-xs font-medium uppercase tracking-[0.2em] text-blue-400/80">
                  Control Center
                </div>
                <h1 className="text-3xl font-semibold tracking-normal text-zinc-50 max-sm:text-2xl">
                  设置
                </h1>
                <p className="mt-2 text-sm text-zinc-500">
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
              />
            ) : (
              <SettingsWorkspace
                onCreateIntegration={addSettingsIntegration}
                onDeleteIntegration={removeSettingsIntegration}
                onDeleteItem={removeSettingsItem}
                onRefresh={refreshSettings}
                onToggleItem={toggleSettingsItem}
                onToggleModule={toggleSettingsModule}
                settings={appSettings}
              />
            )}
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
