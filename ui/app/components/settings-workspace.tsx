"use client";

import {
  CheckCircle2,
  Copy,
  Plus,
  RefreshCcw,
  Settings,
  Trash2,
  X,
  XCircle,
} from "lucide-react";
import { useState, type ReactNode } from "react";

import type {
  AppSettingsData,
  LoadState,
  SettingsIntegration,
  SettingsModule,
} from "../types";

type SettingsWorkspaceProps = {
  onCreateIntegration: (payload: {
    kind: string;
    name: string;
    description: string;
    endpoint: string;
  }) => void;
  onDeleteIntegration: (integrationId: string) => void;
  onDeleteItem: (moduleKey: string, itemName: string) => void;
  onRefresh: () => void;
  onToggleItem: (moduleKey: string, itemName: string, enabled: boolean) => void;
  onToggleModule: (moduleKey: string, enabled: boolean) => void;
  settings: LoadState<AppSettingsData>;
};

type IntegrationDraft = {
  kind: "llm" | "mcp" | "a2a";
  name: string;
  description: string;
  endpoint: string;
};


// ===================== 第1步：展示真实设置工作台 =====================
export function SettingsWorkspace({
  onCreateIntegration,
  onDeleteIntegration,
  onDeleteItem,
  onRefresh,
  onToggleItem,
  onToggleModule,
  settings,
}: SettingsWorkspaceProps) {
  return (
    <section className="mx-auto flex h-full min-h-[640px] w-full max-w-[1080px] flex-col overflow-hidden rounded-[28px] border border-white/10 bg-[#090a0f]/95 shadow-2xl shadow-black/40">
      <div className="flex shrink-0 items-start justify-between gap-4 border-b border-white/10 px-6 py-5">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-semibold text-zinc-50">
            <Settings size={19} aria-hidden="true" />
            AtlasAgent 设置
          </h2>
          <p className="mt-1 text-sm leading-6 text-zinc-500">
            管理模型、搜索、MCP、A2A、多 Agent 和 Sandbox 集成
          </p>
        </div>
        <button
          className="inline-flex h-10 w-10 items-center justify-center rounded-2xl border border-white/10 bg-white/[0.06] text-zinc-400 hover:bg-white/[0.1] hover:text-zinc-50"
          onClick={onRefresh}
          title="刷新设置"
          type="button"
        >
          <RefreshCcw size={16} aria-hidden="true" />
        </button>
      </div>

      {settings.type === "loading" ? (
        <div className="m-6 rounded-3xl border border-white/10 bg-white/[0.04] p-5 text-sm text-zinc-500">
          正在读取设置...
        </div>
      ) : null}

      {settings.type === "error" ? (
        <div className="m-6 rounded-3xl border border-rose-500/30 bg-rose-500/10 p-5 text-sm text-rose-200">
          {settings.message}
        </div>
      ) : null}

      {settings.type === "ready" ? (
        <SettingsReadyView
          data={settings.data}
          onCreateIntegration={onCreateIntegration}
          onDeleteIntegration={onDeleteIntegration}
          onDeleteItem={onDeleteItem}
          onToggleItem={onToggleItem}
          onToggleModule={onToggleModule}
        />
      ) : null}
    </section>
  );
}


function SettingsReadyView({
  data,
  onCreateIntegration,
  onDeleteIntegration,
  onDeleteItem,
  onToggleItem,
  onToggleModule,
}: {
  data: AppSettingsData;
  onCreateIntegration: SettingsWorkspaceProps["onCreateIntegration"];
  onDeleteIntegration: SettingsWorkspaceProps["onDeleteIntegration"];
  onDeleteItem: SettingsWorkspaceProps["onDeleteItem"];
  onToggleItem: SettingsWorkspaceProps["onToggleItem"];
  onToggleModule: SettingsWorkspaceProps["onToggleModule"];
}) {
  const [activeKey, setActiveKey] = useState<SettingsModule["key"]>(
    data.modules[0]?.key ?? "llm",
  );
  const [editingModule, setEditingModule] = useState<SettingsModule | null>(
    null,
  );
  const activeModule =
    data.modules.find((module) => module.key === activeKey) ?? data.modules[0];
  const canConfigure = activeModule
    ? ["llm", "mcp", "a2a"].includes(activeModule.key)
    : false;

  return (
    <>
      <div className="grid min-h-0 flex-1 grid-cols-[220px_1fr] max-lg:grid-cols-1">
        <aside className="min-h-0 border-r border-white/10 p-4 max-lg:border-b max-lg:border-r-0">
          <SettingsOverview modules={data.modules} />
          <nav className="mt-4 grid gap-1">
            {data.modules.map((module) => (
              <button
                className={`flex items-center justify-between gap-3 rounded-2xl px-3 py-2.5 text-left text-sm transition ${
                  activeKey === module.key
                    ? "bg-blue-500 text-white"
                    : "text-zinc-500 hover:bg-white/[0.06] hover:text-zinc-100"
                }`}
                key={module.key}
                onClick={() => setActiveKey(module.key)}
                type="button"
              >
                <span>{module.name}</span>
                <span
                  className={`h-2 w-2 rounded-full ${
                    module.status === "ready" ? "bg-emerald-400" : "bg-amber-300"
                  }`}
                />
              </button>
            ))}
          </nav>
        </aside>

        <section className="min-h-0 overflow-y-auto p-5">
          {activeModule ? (
            <div className="grid gap-5">
              <SettingsModuleCard
                module={activeModule}
                canConfigure={canConfigure}
                onConfigure={() => {
                  if (canConfigure) setEditingModule(activeModule);
                }}
                onDeleteItem={onDeleteItem}
                onToggleItem={onToggleItem}
                onToggleModule={onToggleModule}
              />
              {canConfigure ? (
                <section className="grid grid-cols-[1fr_360px] gap-5 max-xl:grid-cols-1">
                  <IntegrationList
                    integrations={data.integrations.filter(
                      (integration) => integration.kind === activeModule.key,
                    )}
                    onDeleteIntegration={onDeleteIntegration}
                    title={`${activeModule.name} 运行时集成`}
                  />
                  <IntegrationForm
                    key={activeModule.key}
                    defaultKind={activeModule.key as IntegrationDraft["kind"]}
                    onCreateIntegration={onCreateIntegration}
                  />
                </section>
              ) : null}
            </div>
          ) : null}
        </section>
      </div>

      {editingModule ? (
        <ModuleConfigDialog
          module={editingModule}
          onClose={() => setEditingModule(null)}
          onCreateIntegration={onCreateIntegration}
          onDeleteItem={onDeleteItem}
          onToggleItem={onToggleItem}
        />
      ) : null}
    </>
  );
}


function SettingsOverview({ modules }: { modules: SettingsModule[] }) {
  const readyCount = modules.filter((module) => module.status === "ready").length;

  return (
    <div className="rounded-3xl border border-blue-500/25 bg-blue-500/10 p-4">
      <div className="text-xs font-semibold uppercase tracking-[0.22em] text-blue-300">
        Readiness
      </div>
      <div className="mt-3 text-2xl font-semibold text-zinc-50">
        {readyCount}/{modules.length}
      </div>
      <p className="mt-2 text-xs leading-5 text-zinc-400">
        配置是否具备真实任务执行条件
      </p>
    </div>
  );
}


// ===================== 第2步：展示单个模块配置 =====================
function SettingsModuleCard({
  canConfigure,
  module,
  onConfigure,
  onDeleteItem,
  onToggleItem,
  onToggleModule,
}: {
  canConfigure: boolean;
  module: SettingsModule;
  onConfigure: () => void;
  onDeleteItem: SettingsWorkspaceProps["onDeleteItem"];
  onToggleItem: SettingsWorkspaceProps["onToggleItem"];
  onToggleModule: SettingsWorkspaceProps["onToggleModule"];
}) {
  return (
    <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-5 shadow-2xl shadow-black/20">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-base font-semibold text-zinc-50">
              {module.name}
            </h3>
            <StatusPill enabled={module.status === "ready"} />
          </div>
          <p className="mt-1 text-sm leading-6 text-zinc-500">
            {module.description}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {canConfigure ? (
            <button
              className="rounded-xl border border-white/10 bg-white/[0.06] px-3 py-2 text-sm font-medium text-zinc-300 transition hover:border-blue-500/40 hover:text-white"
              onClick={onConfigure}
              type="button"
            >
              配置
            </button>
          ) : null}
          <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-zinc-500">
            <input
              checked={module.enabled}
              className="h-4 w-4 accent-blue-500"
              onChange={(event) =>
                onToggleModule(module.key, event.target.checked)
              }
              type="checkbox"
            />
            启用
          </label>
        </div>
      </div>

      <div className="mt-4 grid gap-3 rounded-2xl border border-white/10 bg-black/30 p-3 text-sm">
        <StatusField label="当前状态" value={module.status_message || "暂无状态说明"} />
        <StatusField label="默认项" value={module.default_item ?? "未设置"} />
        <StatusField label="配置来源" value={module.source || "未声明"} />
        <VerifyCommand command={module.verify_command} />
      </div>

      <div className="mt-4 grid gap-2">
        {module.items.map((item) => (
          <div
            className="rounded-2xl border border-white/10 bg-black/30 px-3 py-3"
            key={`${module.key}-${item.name}`}
          >
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-zinc-100">
                  {item.name}
                </div>
                <p className="mt-1 line-clamp-2 text-xs leading-5 text-zinc-500">
                  {item.description || "暂无说明"}
                </p>
              </div>
              <StatusPill enabled={item.enabled} />
            </div>
            {Object.keys(item.metadata).length > 0 ? (
              <MetadataGrid metadata={item.metadata} />
            ) : null}
            {module.key === "mcp" || module.key === "a2a" ? (
              <div className="mt-3 flex justify-end gap-2">
                <button
                  className="rounded-xl border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs font-medium text-zinc-400 transition hover:text-white"
                  onClick={() => onToggleItem(module.key, item.name, !item.enabled)}
                  type="button"
                >
                  {item.enabled ? "禁用" : "启用"}
                </button>
                <button
                  className="rounded-xl border border-rose-500/20 bg-rose-500/10 px-3 py-1.5 text-xs font-medium text-rose-200 transition hover:bg-rose-500/20"
                  onClick={() => onDeleteItem(module.key, item.name)}
                  type="button"
                >
                  删除
                </button>
              </div>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}


function ModuleConfigDialog({
  module,
  onClose,
  onCreateIntegration,
  onDeleteItem,
  onToggleItem,
}: {
  module: SettingsModule;
  onClose: () => void;
  onCreateIntegration: SettingsWorkspaceProps["onCreateIntegration"];
  onDeleteItem: SettingsWorkspaceProps["onDeleteItem"];
  onToggleItem: SettingsWorkspaceProps["onToggleItem"];
}) {
  const defaultName = module.default_item ?? module.items[0]?.name ?? module.key;
  const [name, setName] = useState(defaultName);
  const [endpoint, setEndpoint] = useState(module.items[0]?.description ?? "");
  const [description, setDescription] = useState(
    module.key === "llm" ? "" : module.status_message,
  );

  function submitRuntimeIntegration() {
    onCreateIntegration({
      kind: module.key,
      name: name.trim() || defaultName,
      endpoint: endpoint.trim(),
      description: description.trim() || module.description,
    });
    onClose();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4 py-6 backdrop-blur-xl"
      role="dialog"
      aria-modal="true"
    >
      <div className="flex max-h-[86dvh] w-full max-w-[820px] flex-col overflow-hidden rounded-[28px] border border-white/10 bg-[#090a0f] shadow-2xl shadow-black">
        <div className="flex shrink-0 items-start justify-between gap-4 border-b border-white/10 px-6 py-5">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.22em] text-blue-300">
              Configure
            </div>
            <h3 className="mt-2 text-xl font-semibold text-zinc-50">
              {module.name}
            </h3>
            <p className="mt-1 text-sm leading-6 text-zinc-500">
              {module.description}
            </p>
          </div>
          <button
            className="flex h-10 w-10 items-center justify-center rounded-2xl border border-white/10 bg-white/[0.05] text-zinc-500 transition hover:bg-white/[0.1] hover:text-white"
            onClick={onClose}
            title="关闭"
            type="button"
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
          <div className="grid gap-4">
            <div className="rounded-2xl border border-white/10 bg-black/30 p-4">
              <StatusField label="当前状态" value={module.status_message} />
              <div className="mt-3">
                <StatusField label="配置来源" value={module.source || "未声明"} />
              </div>
              <div className="mt-3">
                <VerifyCommand command={module.verify_command} />
              </div>
            </div>

            {module.key === "mcp" ? (
              <McpConfigForm
                description={description}
                endpoint={endpoint}
                name={name}
                onDescriptionChange={setDescription}
                onEndpointChange={setEndpoint}
                onNameChange={setName}
              />
            ) : module.key === "a2a" ? (
              <A2aConfigForm
                description={description}
                endpoint={endpoint}
                name={name}
                onDescriptionChange={setDescription}
                onEndpointChange={setEndpoint}
                onNameChange={setName}
              />
            ) : module.key === "llm" ? (
              <LlmConfigForm
                description={description}
                endpoint={endpoint}
                name={name}
                onDescriptionChange={setDescription}
                onEndpointChange={setEndpoint}
                onNameChange={setName}
              />
            ) : (
              <GenericConfigForm
                description={description}
                endpoint={endpoint}
                name={name}
                onDescriptionChange={setDescription}
                onEndpointChange={setEndpoint}
                onNameChange={setName}
              />
            )}

            <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
              <div className="text-sm font-semibold text-zinc-100">
                已加载配置项
              </div>
              <div className="mt-3 grid gap-2">
                {module.items.map((item) => (
                  <div
                    className="rounded-xl border border-white/10 bg-black/30 p-3"
                    key={`${module.key}-dialog-${item.name}`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="truncate text-sm font-medium text-zinc-100">
                          {item.name}
                        </div>
                        <p className="mt-1 text-xs leading-5 text-zinc-500">
                          {item.description || "暂无说明"}
                        </p>
                      </div>
                      <StatusPill enabled={item.enabled} />
                    </div>
                    {Object.keys(item.metadata).length > 0 ? (
                      <MetadataGrid metadata={item.metadata} />
                    ) : null}
                    {module.key === "mcp" || module.key === "a2a" ? (
                      <div className="mt-3 flex justify-end gap-2">
                        <button
                          className="rounded-xl border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs font-medium text-zinc-400 transition hover:text-white"
                          onClick={() => {
                            onToggleItem(module.key, item.name, !item.enabled);
                            onClose();
                          }}
                          type="button"
                        >
                          {item.enabled ? "禁用" : "启用"}
                        </button>
                        <button
                          className="rounded-xl border border-rose-500/20 bg-rose-500/10 px-3 py-1.5 text-xs font-medium text-rose-200 transition hover:bg-rose-500/20"
                          onClick={() => {
                            onDeleteItem(module.key, item.name);
                            onClose();
                          }}
                          type="button"
                        >
                          删除
                        </button>
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="flex shrink-0 justify-end gap-3 border-t border-white/10 px-6 py-4">
          <button
            className="rounded-xl border border-white/10 bg-white/[0.04] px-4 py-2 text-sm font-medium text-zinc-400 transition hover:bg-white/[0.08] hover:text-white"
            onClick={onClose}
            type="button"
          >
            取消
          </button>
          <button
            className="rounded-xl bg-blue-500 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-400"
            onClick={submitRuntimeIntegration}
            type="button"
          >
            保存配置意图
          </button>
        </div>
      </div>
    </div>
  );
}


function ConfigField({
  children,
  label,
}: {
  children: ReactNode;
  label: string;
}) {
  return (
    <label className="block text-xs font-medium text-zinc-500">
      {label}
      {children}
    </label>
  );
}


function ConfigInput({
  onChange,
  placeholder,
  type = "text",
  value,
}: {
  onChange: (value: string) => void;
  placeholder: string;
  type?: string;
  value: string;
}) {
  return (
    <input
      className="mt-1 h-11 w-full rounded-xl border border-white/10 bg-black/40 px-3 text-sm text-zinc-100 outline-none placeholder:text-zinc-700 focus:border-blue-500/60"
      onChange={(event) => onChange(event.target.value)}
      placeholder={placeholder}
      type={type}
      value={value}
    />
  );
}


function ConfigTextarea({
  onChange,
  placeholder,
  value,
}: {
  onChange: (value: string) => void;
  placeholder: string;
  value: string;
}) {
  return (
    <textarea
      className="mt-1 min-h-32 w-full resize-none rounded-xl border border-white/10 bg-black/40 px-3 py-2 font-mono text-xs leading-5 text-zinc-100 outline-none placeholder:text-zinc-700 focus:border-blue-500/60"
      onChange={(event) => onChange(event.target.value)}
      placeholder={placeholder}
      value={value}
    />
  );
}


type ModuleFormProps = {
  description: string;
  endpoint: string;
  name: string;
  onDescriptionChange: (value: string) => void;
  onEndpointChange: (value: string) => void;
  onNameChange: (value: string) => void;
};


function LlmConfigForm({
  description,
  endpoint,
  name,
  onDescriptionChange,
  onEndpointChange,
  onNameChange,
}: ModuleFormProps) {
  return (
    <div className="grid gap-3 rounded-2xl border border-white/10 bg-white/[0.03] p-4">
      <ConfigField label="模型提供商">
        <ConfigInput onChange={onNameChange} placeholder="openai_compatible" value={name} />
      </ConfigField>
      <ConfigField label="Base URL">
        <ConfigInput
          onChange={onEndpointChange}
          placeholder="https://api.deepseek.com/v1"
          type="url"
          value={endpoint}
        />
      </ConfigField>
      <ConfigField label="API Key 环境变量名">
        <ConfigInput
          onChange={onDescriptionChange}
          placeholder="LLM_API_KEY"
          value={description}
        />
      </ConfigField>
      <p className="text-xs leading-5 text-zinc-600">
        这里只保存环境变量名，真实密钥必须通过容器 Secret、KMS 或 Vault 注入，API 不会保存或回显密钥。
      </p>
    </div>
  );
}


function McpConfigForm({
  description,
  endpoint,
  name,
  onDescriptionChange,
  onEndpointChange,
  onNameChange,
}: ModuleFormProps) {
  return (
    <div className="grid gap-3 rounded-2xl border border-white/10 bg-white/[0.03] p-4">
      <ConfigField label="MCP Server 名称">
        <ConfigInput onChange={onNameChange} placeholder="qiniu" value={name} />
      </ConfigField>
      <ConfigField label="MCP JSON 配置">
        <ConfigTextarea
          onChange={onDescriptionChange}
          placeholder={`{
  "mcpServers": {
    "qiniu": {
      "command": "uvx",
      "args": ["qiniu-mcp-server"],
      "env": {
        "QINIU_ACCESS_KEY": "YOUR_ACCESS_KEY"
      }
    }
  }
}`}
          value={description}
        />
      </ConfigField>
      <ConfigField label="可选 Endpoint">
        <ConfigInput
          onChange={onEndpointChange}
          placeholder="stdio / sse / streamable_http 地址"
          value={endpoint}
        />
      </ConfigField>
    </div>
  );
}


function A2aConfigForm({
  description,
  endpoint,
  name,
  onDescriptionChange,
  onEndpointChange,
  onNameChange,
}: ModuleFormProps) {
  return (
    <div className="grid gap-3 rounded-2xl border border-white/10 bg-white/[0.03] p-4">
      <ConfigField label="远程 Agent 名称">
        <ConfigInput onChange={onNameChange} placeholder="researcher" value={name} />
      </ConfigField>
      <ConfigField label="远程 Agent 地址">
        <ConfigInput
          onChange={onEndpointChange}
          placeholder="https://example.com/a2a-agent"
          type="url"
          value={endpoint}
        />
      </ConfigField>
      <ConfigField label="能力说明">
        <ConfigInput
          onChange={onDescriptionChange}
          placeholder="负责搜索、研究或审查任务"
          value={description}
        />
      </ConfigField>
    </div>
  );
}


function GenericConfigForm({
  description,
  endpoint,
  name,
  onDescriptionChange,
  onEndpointChange,
  onNameChange,
}: ModuleFormProps) {
  return (
    <div className="grid gap-3 rounded-2xl border border-white/10 bg-white/[0.03] p-4">
      <ConfigField label="配置名称">
        <ConfigInput onChange={onNameChange} placeholder="配置名称" value={name} />
      </ConfigField>
      <ConfigField label="地址或来源">
        <ConfigInput onChange={onEndpointChange} placeholder=".env / URL" value={endpoint} />
      </ConfigField>
      <ConfigField label="说明">
        <ConfigInput
          onChange={onDescriptionChange}
          placeholder="说明这个配置的用途"
          value={description}
        />
      </ConfigField>
    </div>
  );
}


function StatusField({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[72px_1fr] gap-3 text-xs">
      <span className="text-zinc-600">{label}</span>
      <span className="min-w-0 break-words font-medium text-zinc-300">
        {value}
      </span>
    </div>
  );
}


function VerifyCommand({ command }: { command: string }) {
  if (!command) {
    return <StatusField label="验证命令" value="未提供" />;
  }

  return (
    <div className="grid grid-cols-[72px_1fr] gap-3 text-xs">
      <span className="text-zinc-600">验证命令</span>
      <button
        className="flex min-w-0 items-center justify-between gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-left font-mono text-[11px] text-zinc-300 transition hover:border-blue-500/40 hover:text-zinc-50"
        onClick={() => navigator.clipboard?.writeText(command)}
        title="复制验证命令"
        type="button"
      >
        <span className="min-w-0 truncate">{command}</span>
        <Copy size={13} aria-hidden="true" />
      </button>
    </div>
  );
}


function MetadataGrid({ metadata }: { metadata: Record<string, unknown> }) {
  return (
    <dl className="mt-3 grid gap-2 rounded-xl border border-white/10 bg-white/[0.03] p-3">
      {Object.entries(metadata).map(([key, value]) => (
        <div className="grid grid-cols-[112px_1fr] gap-3 text-xs" key={key}>
          <dt className="truncate uppercase tracking-[0.14em] text-zinc-600">
            {key}
          </dt>
          <dd className="min-w-0 break-words font-medium text-zinc-300">
            {formatMetadataValue(value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}


function formatMetadataValue(value: unknown) {
  if (typeof value === "boolean") {
    return value ? "是" : "否";
  }
  if (value === null || value === undefined || value === "") {
    return "未设置";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}


function StatusPill({ enabled }: { enabled: boolean }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-1 text-xs ${
        enabled
          ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
          : "border-amber-500/30 bg-amber-500/10 text-amber-300"
      }`}
    >
      {enabled ? <CheckCircle2 size={13} /> : <XCircle size={13} />}
      {enabled ? "可用" : "待配置"}
    </span>
  );
}


// ===================== 第3步：展示和删除运行时集成记录 =====================
function IntegrationList({
  integrations,
  onDeleteIntegration,
  title = "运行时集成",
}: {
  integrations: SettingsIntegration[];
  onDeleteIntegration: SettingsWorkspaceProps["onDeleteIntegration"];
  title?: string;
}) {
  return (
    <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-5">
      <h3 className="text-base font-semibold text-zinc-50">{title}</h3>
      <p className="mt-1 text-sm leading-6 text-zinc-500">
        记录来自持久化运行时配置；删除会同步更新 YAML，重启后不会恢复
      </p>

      <div className="mt-4 grid gap-2">
        {integrations.length === 0 ? (
          <div className="rounded-2xl border border-white/10 bg-black/30 px-3 py-3 text-sm text-zinc-500">
            还没有新增运行时集成
          </div>
        ) : null}

        {integrations.map((integration) => (
          <div
            className="flex items-start justify-between gap-3 rounded-2xl border border-white/10 bg-black/30 px-3 py-3"
            key={integration.id}
          >
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="rounded-full border border-white/10 bg-white/[0.06] px-2 py-1 text-xs font-medium text-zinc-500">
                  {integration.kind}
                </span>
                <span className="truncate text-sm font-semibold text-zinc-100">
                  {integration.name}
                </span>
              </div>
              <p className="mt-2 text-xs leading-5 text-zinc-500">
                {integration.description || "暂无说明"}
              </p>
              {integration.endpoint ? (
                <p className="mt-1 truncate text-xs text-blue-300">
                  {integration.endpoint}
                </p>
              ) : null}
            </div>
            <button
              className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-xl text-zinc-500 hover:bg-white/10 hover:text-rose-300"
              onClick={() => onDeleteIntegration(integration.id)}
              title="删除集成"
              type="button"
            >
              <Trash2 size={15} aria-hidden="true" />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}


// ===================== 第4步：新增运行时集成记录 =====================
function IntegrationForm({
  defaultKind = "mcp",
  onCreateIntegration,
}: {
  defaultKind?: IntegrationDraft["kind"];
  onCreateIntegration: SettingsWorkspaceProps["onCreateIntegration"];
}) {
  const [draft, setDraft] = useState<IntegrationDraft>({
    kind: defaultKind,
    name: "",
    description: "",
    endpoint: "",
  });

  return (
    <form
      className="rounded-3xl border border-white/10 bg-white/[0.04] p-5"
      onSubmit={(event) => {
        event.preventDefault();
        onCreateIntegration(draft);
        setDraft({ kind: defaultKind, name: "", description: "", endpoint: "" });
      }}
    >
      <h3 className="text-base font-semibold text-zinc-50">新增集成</h3>
      <p className="mt-1 text-sm leading-6 text-zinc-500">
        保存后会写入持久化运行时配置，并受运维 allowlist 约束
      </p>

      <label className="mt-4 block text-xs font-medium text-zinc-500">
        类型
        <select
          className="mt-1 h-10 w-full rounded-xl border border-white/10 bg-black/40 px-3 text-sm text-zinc-100 outline-none focus:border-blue-500/60"
          onChange={(event) =>
            setDraft((current) => ({
              ...current,
              kind: event.target.value as IntegrationDraft["kind"],
            }))
          }
          value={draft.kind}
        >
          <option value="llm">LLM</option>
          <option value="mcp">MCP</option>
          <option value="a2a">A2A</option>
        </select>
      </label>

      <label className="mt-3 block text-xs font-medium text-zinc-500">
        名称
        <input
          className="mt-1 h-10 w-full rounded-xl border border-white/10 bg-black/40 px-3 text-sm text-zinc-100 outline-none placeholder:text-zinc-700 focus:border-blue-500/60"
          maxLength={120}
          onChange={(event) =>
            setDraft((current) => ({ ...current, name: event.target.value }))
          }
          placeholder="例如 custom_mcp"
          value={draft.name}
        />
      </label>

      <label className="mt-3 block text-xs font-medium text-zinc-500">
        地址
        <input
          className="mt-1 h-10 w-full rounded-xl border border-white/10 bg-black/40 px-3 text-sm text-zinc-100 outline-none placeholder:text-zinc-700 focus:border-blue-500/60"
          maxLength={500}
          onChange={(event) =>
            setDraft((current) => ({ ...current, endpoint: event.target.value }))
          }
          placeholder="https://example.com"
          value={draft.endpoint}
        />
      </label>

      <label className="mt-3 block text-xs font-medium text-zinc-500">
        说明
        <textarea
          className="mt-1 min-h-24 w-full resize-none rounded-xl border border-white/10 bg-black/40 px-3 py-2 text-sm text-zinc-100 outline-none placeholder:text-zinc-700 focus:border-blue-500/60"
          maxLength={500}
          onChange={(event) =>
            setDraft((current) => ({
              ...current,
              description: event.target.value,
            }))
          }
          placeholder="说明这个集成准备做什么"
          value={draft.description}
        />
      </label>

      <button
        className="mt-4 inline-flex h-10 w-full items-center justify-center gap-2 rounded-xl bg-blue-500 px-4 text-sm font-medium text-white transition hover:bg-blue-400 disabled:cursor-not-allowed disabled:bg-zinc-800 disabled:text-zinc-600"
        disabled={!draft.name.trim()}
        type="submit"
      >
        <Plus size={16} aria-hidden="true" />
        新增
      </button>
    </form>
  );
}
