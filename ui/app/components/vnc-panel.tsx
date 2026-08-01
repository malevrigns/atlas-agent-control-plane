"use client";

import { Monitor, RefreshCcw, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { LoadState, VncStatusData } from "../types";

type VncPanelProps = {
  onRefresh: () => void; // 重新读取 /sandbox-api/vnc/status。
  state: LoadState<VncStatusData>; // 来自 Sandbox API，包含 websockify 连接路径。
};

type VncConnectionState = "idle" | "connecting" | "connected" | "error";

type RfbInstance = EventTarget & {
  scaleViewport: boolean;
  resizeSession: boolean;
  viewOnly: boolean;
  disconnect: () => void;
};

type RfbConstructor = new (target: HTMLElement, url: string) => RfbInstance;


// ===================== 第1步：展示 Sandbox 浏览器远程桌面 =====================
export function VncPanel({ onRefresh, state }: VncPanelProps) {
  return (
    <div className="rounded-[24px] border border-white/10 bg-[#08090d] p-5 shadow-2xl shadow-black/50">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="mb-2 text-xs font-medium uppercase tracking-[0.18em] text-zinc-600">
            Remote Desktop
          </div>
          <h2 className="text-base font-semibold text-zinc-50">
            浏览器远程桌面
          </h2>
          <p className="mt-1 text-sm leading-5 text-zinc-500">
            查看 Sandbox 中有头浏览器的实时画面
          </p>
        </div>
        <button
          className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-white/10 bg-white/[0.04] text-zinc-400 hover:bg-white/10 hover:text-zinc-50"
          onClick={onRefresh}
          title="刷新 VNC 状态"
          type="button"
        >
          <RefreshCcw size={16} />
        </button>
      </div>

      {state.type === "loading" ? (
        <div className="mt-4 rounded-2xl border border-white/10 bg-white/[0.04] p-3 text-sm text-zinc-500">
          正在读取远程桌面状态...
        </div>
      ) : null}

      {state.type === "error" ? (
        <div className="mt-4 flex gap-2 rounded-2xl border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200">
          <XCircle className="mt-0.5 shrink-0" size={16} />
          <span>{state.message}</span>
        </div>
      ) : null}

      {state.type === "ready" ? <VncReadyView data={state.data} /> : null}
    </div>
  );
}


function VncReadyView({ data }: { data: VncStatusData }) {
  const screenRef = useRef<HTMLDivElement | null>(null);
  const rfbRef = useRef<RfbInstance | null>(null);
  const [connectionState, setConnectionState] =
    useState<VncConnectionState>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!data.enabled || !screenRef.current) {
      return;
    }

    let disposed = false;

    // 1. 根据当前页面协议拼出 noVNC WebSocket 地址。
    //    页面是 http 时使用 ws，页面是 https 时使用 wss。
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const websocketUrl = `${protocol}//${window.location.host}/${data.websocket_path}`;

    setConnectionState("connecting");
    setErrorMessage(null);

    async function connectRemoteDesktop() {
      try {
        // 2. noVNC 会在模块初始化时访问 window，所以必须放在浏览器端动态导入。
        const module = (await import("@novnc/novnc")) as {
          default: RfbConstructor;
        };
        if (disposed || !screenRef.current) {
          return;
        }

        // 3. 创建 noVNC RFB 实例。target 是一个普通 div，SDK 会把远程桌面画面渲染进去。
        const rfb = new module.default(screenRef.current, websocketUrl);
        rfb.scaleViewport = true;
        rfb.resizeSession = false;
        rfb.viewOnly = false;
        rfbRef.current = rfb;

        // 4. 监听连接状态，给用户明确反馈，而不是只显示黑框。
        rfb.addEventListener("connect", () => {
          setConnectionState("connected");
        });
        rfb.addEventListener("disconnect", (event) => {
          const detail = (event as CustomEvent<{ clean?: boolean }>).detail;
          if (detail?.clean) {
            setConnectionState("idle");
            return;
          }
          setConnectionState("error");
          setErrorMessage("远程桌面连接断开，请检查 Sandbox 和 Nginx 日志。");
        });
        rfb.addEventListener("securityfailure", () => {
          setConnectionState("error");
          setErrorMessage("远程桌面安全握手失败。");
        });
      } catch (error) {
        if (disposed) {
          return;
        }
        const message = error instanceof Error ? error.message : "unknown error";
        setConnectionState("error");
        setErrorMessage(`远程桌面组件加载失败：${message}`);
      }
    }

    connectRemoteDesktop();

    return () => {
      disposed = true;
      if (!rfbRef.current) {
        return;
      }
      rfbRef.current.disconnect();
      rfbRef.current = null;
    };
  }, [data.enabled, data.websocket_path]);

  if (!data.enabled) {
    return (
      <div className="mt-4 rounded-2xl border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-200">
        VNC 未启用：{data.message}
      </div>
    );
  }

  return (
    <div className="mt-4 grid gap-3">
      <div className="flex items-center gap-2 rounded-2xl border border-emerald-500/25 bg-emerald-500/10 p-3 text-sm text-emerald-200">
        <Monitor size={16} />
        <span>{getConnectionText(connectionState, data.message)}</span>
      </div>
      {errorMessage ? (
        <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-200">
          {errorMessage}
        </div>
      ) : null}
      <div className="h-[260px] overflow-hidden rounded-2xl border border-white/10 bg-black">
        <div className="h-full w-full" ref={screenRef} />
      </div>
      <dl className="grid gap-2 text-xs text-zinc-500">
        <div className="flex justify-between gap-3">
          <dt>显示器</dt>
          <dd className="font-medium text-zinc-200">{data.display}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt>Web 端口</dt>
          <dd className="font-medium text-zinc-200">{data.web_port}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt>WebSocket</dt>
          <dd className="truncate font-medium text-zinc-200">
            {data.websocket_path}
          </dd>
        </div>
      </dl>
    </div>
  );
}


function getConnectionText(state: VncConnectionState, fallback: string) {
  if (state === "connecting") {
    return "正在连接远程桌面...";
  }
  if (state === "connected") {
    return "远程桌面已连接";
  }
  if (state === "error") {
    return "远程桌面连接异常";
  }
  return fallback;
}
