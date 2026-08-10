import {
  ArrowClockwise,
  Brain,
  CaretDown,
  ChatCircleDots,
  PaperPlaneRight,
  Plus,
  Stop,
  Trash,
} from "@phosphor-icons/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { sessionsApi, streamSessionMessage } from "../api";
import { InlineNotice, ThemeSelect } from "../components";
import { MarkdownLite } from "../markdown";
import { useTypewriter } from "../use-typewriter";
import type {
  ApiState,
  ChatActivity,
  ChatMessage,
  ChatSession,
  SseRecord,
  Theme,
} from "../types";

interface ThinkingBlockProps {
  reasoning: string;
  streaming?: boolean;
}

/** 模型推理过程：流式时默认展开，完成后折叠可回看。 */
function ThinkingBlock({ reasoning, streaming = false }: ThinkingBlockProps) {
  const [expanded, setExpanded] = useState<boolean | null>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const open = expanded ?? streaming;

  useEffect(() => {
    const body = bodyRef.current;
    if (body && streaming) body.scrollTop = body.scrollHeight;
  }, [reasoning, streaming]);

  if (!reasoning) return null;
  return (
    <div className={`thinking-block ${streaming ? "streaming" : ""}`}>
      <button
        type="button"
        className="thinking-toggle"
        aria-expanded={open}
        onClick={() => setExpanded(!open)}
      >
        <Brain size={14} weight={streaming ? "fill" : "regular"} />
        <span>{streaming ? "正在思考…" : "推理过程"}</span>
        <em>{reasoning.length} 字</em>
        <CaretDown size={13} className={open ? "open" : ""} />
      </button>
      {open ? (
        <div className="thinking-body" ref={bodyRef}>
          <MarkdownLite content={reasoning} />
        </div>
      ) : null}
    </div>
  );
}

interface ChatViewProps {
  theme: Theme;
  setTheme: Dispatch<SetStateAction<Theme>>;
  onApiState: (state: ApiState) => void;
}

function formatSessionTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "";
  const now = new Date();
  const sameDay = date.toDateString() === now.toDateString();
  return sameDay
    ? date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })
    : date.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" });
}

function formatMessageTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? ""
    : date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

function sessionStatusLabel(status: string): string {
  if (status === "running") return "回答中";
  if (status === "failed") return "上次失败";
  if (status === "stopped") return "已停止";
  return "空闲";
}

export function ChatView({ theme, setTheme, onApiState }: ChatViewProps) {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [offline, setOffline] = useState(false);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [activity, setActivity] = useState<ChatActivity | null>(null);
  const [liveAnswer, setLiveAnswer] = useState("");
  const [liveThinking, setLiveThinking] = useState("");
  const [reasoningMap, setReasoningMap] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState("");
  const [noticeTone, setNoticeTone] = useState<"info" | "danger">("info");

  const composerRef = useRef<HTMLTextAreaElement>(null);
  const timelineRef = useRef<HTMLDivElement>(null);
  const cancelStreamRef = useRef<(() => void) | null>(null);
  const composingRef = useRef(false);
  const selectedIdRef = useRef<string | null>(null);
  selectedIdRef.current = selectedId;

  const selected = useMemo(
    () => sessions.find((session) => session.id === selectedId) || null,
    [sessions, selectedId],
  );

  const report = useCallback((message: string, tone: "info" | "danger" = "info") => {
    setNotice(message);
    setNoticeTone(tone);
  }, []);

  const refreshSessions = useCallback(async () => {
    try {
      const data = await sessionsApi.list();
      setSessions(data.items);
      setOffline(false);
      onApiState("connected");
      setSelectedId((current) => {
        if (current && data.items.some((session) => session.id === current)) return current;
        return data.items[0]?.id ?? null;
      });
    } catch (error) {
      setOffline(true);
      onApiState("offline");
      report(error instanceof Error ? error.message : "无法连接控制平面", "danger");
    }
  }, [onApiState, report]);

  const loadMessages = useCallback(async (sessionId: string) => {
    setLoadingMessages(true);
    try {
      const data = await sessionsApi.messages(sessionId);
      if (selectedIdRef.current === sessionId) {
        setMessages(data.items);
        setOffline(false);
      }
      void sessionsApi.markRead(sessionId).catch(() => undefined);
    } catch (error) {
      if (selectedIdRef.current === sessionId) {
        setMessages([]);
        report(error instanceof Error ? error.message : "读取消息失败", "danger");
      }
    } finally {
      if (selectedIdRef.current === sessionId) setLoadingMessages(false);
    }

    // 事件时间线里的 task_done 携带每轮回答的推理过程，
    // 刷新或切换会话后仍能展开查看。
    try {
      const events = await sessionsApi.events(sessionId);
      if (selectedIdRef.current !== sessionId) return;
      const map: Record<string, string> = {};
      for (const event of events.items) {
        if (event.type !== "task_done") continue;
        const messageId = String(event.payload.message_id ?? "");
        const reasoning = String(event.payload.reasoning ?? "");
        if (messageId && reasoning) map[messageId] = reasoning;
      }
      setReasoningMap(map);
    } catch {
      // 事件读取失败只影响推理过程回看，不影响对话本身。
    }
  }, [report]);

  useEffect(() => {
    void refreshSessions();
  }, [refreshSessions]);

  useEffect(() => {
    setMessages([]);
    setLiveAnswer("");
    setLiveThinking("");
    setReasoningMap({});
    setActivity(null);
    if (selectedId) void loadMessages(selectedId);
  }, [selectedId, loadMessages]);

  // 卸载视图时终止仍在进行的流。
  useEffect(() => () => cancelStreamRef.current?.(), []);

  // ChatGPT 式滚动：切会话跳到底部；发出追问时把该消息锚定到视口顶部，
  // 回答在下方生长；流式期间不自动跟滚，用户停在哪就是哪。
  const anchoredMessageRef = useRef<string | null>(null);
  const anchoredSessionRef = useRef<string | null>(null);
  // 锚定后垫在时间线尾部的空白，保证"提问顶到视口顶部"物理上可达。
  const [anchorSpacer, setAnchorSpacer] = useState(false);
  // 思考流打字机节流：按稳定速度放出，避免大段思考瞬间刷屏。
  const pacedThinking = useTypewriter(liveThinking);
  useEffect(() => {
    const timeline = timelineRef.current;
    if (!timeline) return;
    const lastUserId =
      [...messages].reverse().find((message) => message.role === "user")?.id ?? null;
    if (anchoredSessionRef.current !== selectedId) {
      // 切会话时列表先被清空再异步加载，等消息真正到位后再定位到底部。
      if (messages.length === 0) return;
      anchoredSessionRef.current = selectedId;
      anchoredMessageRef.current = lastUserId;
      setAnchorSpacer(false);
      timeline.scrollTo({ top: timeline.scrollHeight, behavior: "instant" as ScrollBehavior });
      return;
    }
    if (lastUserId && anchoredMessageRef.current !== lastUserId) {
      anchoredMessageRef.current = lastUserId;
      setAnchorSpacer(true);
      // setTimeout 而非 rAF：隐藏窗口的 rAF 会被冻结；50ms 等 spacer 渲染。
      window.setTimeout(() => {
        const element = timeline.querySelector(`[data-mid="${lastUserId}"]`);
        element?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 50);
    }
  }, [messages, selectedId]);

  function appendMessageFromEvent(record: SseRecord) {
    const payload = (record.data.payload ?? {}) as Record<string, unknown>;
    const messageId = String(payload.message_id ?? "");
    const role = String(payload.role ?? "");
    const content = String(payload.content ?? "");
    if (!messageId || !content || !["user", "assistant", "system"].includes(role)) return;
    const message: ChatMessage = {
      id: messageId,
      session_id: String(record.data.session_id ?? ""),
      role: role as ChatMessage["role"],
      content,
      created_at: String(record.data.created_at ?? new Date().toISOString()),
    };
    if (role === "assistant") {
      setLiveAnswer("");
      setActivity(null);
      // 把仍在缓冲的思考过程先挂到刚落库的消息上，
      // task_done 事件到达后会用服务端版本覆盖。
      setLiveThinking((current) => {
        if (current) {
          setReasoningMap((map) => ({ ...map, [message.id]: current }));
        }
        return "";
      });
    }
    setMessages((current) =>
      current.some((item) => item.id === message.id) ? current : [...current, message],
    );
  }

  function handleStreamRecord(record: SseRecord) {
    const payload = (record.data.payload ?? {}) as Record<string, unknown>;
    switch (record.event) {
      case "message_created":
        appendMessageFromEvent(record);
        return;
      case "plan_created": {
        // 规划完成：收起规划阶段的思考流（已存入 plan_created 事件）。
        setLiveThinking("");
        const steps = Array.isArray(payload.steps) ? payload.steps.length : 0;
        setActivity({
          kind: "planning",
          text: steps
            ? `已生成执行计划（${steps} 个步骤），开始执行…`
            : "已生成执行计划，开始执行…",
        });
        return;
      }
      case "step_started":
        setActivity({
          kind: "step",
          text: `步骤 ${String(payload.index ?? "")}：${String(payload.title ?? "执行中")}`,
        });
        return;
      case "tool_called":
        setActivity({
          kind: "tool",
          text: `调用工具 ${String(payload.tool_name ?? "")}…`,
        });
        return;
      case "answer_started":
        setActivity({ kind: "answering", text: "正在书写回答…" });
        return;
      case "thinking_delta": {
        const delta = String(record.data.delta ?? "");
        if (delta) {
          setActivity(null);
          setLiveThinking((current) => current + delta);
        }
        return;
      }
      case "answer_delta": {
        const delta = String(record.data.delta ?? "");
        if (delta) {
          setActivity(null);
          setLiveAnswer((current) => current + delta);
        }
        return;
      }
      case "task_done": {
        setActivity(null);
        const messageId = String(payload.message_id ?? "");
        const reasoning = String(payload.reasoning ?? "");
        if (messageId && reasoning) {
          setReasoningMap((map) => ({ ...map, [messageId]: reasoning }));
        }
        return;
      }
      case "task_error": {
        const userMessage = String(payload.user_message ?? payload.message ?? "任务执行失败");
        const suggestion = String(payload.suggestion ?? "");
        setActivity(null);
        setLiveAnswer("");
        report(suggestion ? `${userMessage}（建议：${suggestion}）` : userMessage, "danger");
        return;
      }
      case "session_status": {
        const sessionId = String(record.data.id ?? "");
        const status = String(record.data.status ?? "");
        if (sessionId && status) {
          setSessions((current) =>
            current.map((session) =>
              session.id === sessionId ? { ...session, status } : session,
            ),
          );
        }
        return;
      }
      default:
        return;
    }
  }

  async function createSession(title: string): Promise<ChatSession | null> {
    try {
      const created = await sessionsApi.create(title);
      setSessions((current) => [created, ...current]);
      setSelectedId(created.id);
      setOffline(false);
      onApiState("connected");
      return created;
    } catch (error) {
      setOffline(true);
      onApiState("offline");
      report(error instanceof Error ? error.message : "创建会话失败", "danger");
      return null;
    }
  }

  async function removeSession(session: ChatSession) {
    try {
      await sessionsApi.remove(session.id);
      report(`会话「${session.title}」已删除。`);
      await refreshSessions();
    } catch (error) {
      report(error instanceof Error ? error.message : "删除会话失败", "danger");
    }
  }

  async function sendMessage() {
    const content = draft.trim();
    if (!content || sending) return;

    // 没有会话时先创建：标题取首条消息的前 24 个字符。
    let sessionId = selectedId;
    if (!sessionId) {
      const created = await createSession(content.slice(0, 24));
      if (!created) return;
      sessionId = created.id;
    }

    setNotice("");
    setSending(true);
    setDraft("");
    setActivity({ kind: "answering", text: "正在连接…" });

    const targetSessionId = sessionId;
    cancelStreamRef.current = streamSessionMessage(targetSessionId, content, {
      onRecord: (record) => {
        if (selectedIdRef.current === targetSessionId) handleStreamRecord(record);
      },
      onEnd: () => {
        cancelStreamRef.current = null;
        setSending(false);
        setActivity(null);
        setLiveAnswer("");
        setLiveThinking("");
        // 以服务端为准刷新一次，保证消息与会话状态一致。
        if (selectedIdRef.current === targetSessionId) void loadMessages(targetSessionId);
        void refreshSessions();
      },
      onError: (message) => {
        cancelStreamRef.current = null;
        setSending(false);
        setActivity(null);
        setLiveAnswer("");
        setLiveThinking("");
        report(message, "danger");
        if (selectedIdRef.current === targetSessionId) void loadMessages(targetSessionId);
      },
    });
  }

  function stopStreaming() {
    cancelStreamRef.current?.();
    cancelStreamRef.current = null;
    setSending(false);
    setActivity(null);
    setLiveThinking("");
    report("已停止接收本轮回答。");
  }

  const emptyTimeline =
    !loadingMessages && messages.length === 0 && !liveAnswer && !liveThinking && !activity;

  return (
    <>
      <aside className="task-sidebar" aria-label="会话列表">
        <div className="sidebar-title-row">
          <h2>对话</h2>
          <div>
            <button
              className="icon-button"
              type="button"
              aria-label="新建会话"
              onClick={() => void createSession("新的对话")}
            >
              <Plus size={20} />
            </button>
            <button
              className="icon-button"
              type="button"
              aria-label="刷新会话列表"
              onClick={() => void refreshSessions()}
            >
              <ArrowClockwise size={18} />
            </button>
          </div>
        </div>
        <div className="session-list" role="list">
          {sessions.length === 0 ? (
            <p className="empty-hint">
              {offline
                ? "未连接控制平面。请先启动后端服务，再点击刷新。"
                : "还没有会话。输入第一条消息即可开始对话。"}
            </p>
          ) : (
            sessions.map((session) => (
              <div
                key={session.id}
                className={`session-item ${session.id === selectedId ? "selected" : ""}`}
              >
                <button
                  className="session-select"
                  type="button"
                  onClick={() => setSelectedId(session.id)}
                >
                  <strong>{session.title}</strong>
                  <small>
                    {sessionStatusLabel(session.status)}
                    {session.unread_count > 0 ? ` · ${session.unread_count} 条未读` : ""}
                    {" · "}
                    {formatSessionTime(session.updated_at)}
                  </small>
                </button>
                <button
                  className="icon-button session-delete"
                  type="button"
                  aria-label={`删除会话 ${session.title}`}
                  onClick={() => void removeSession(session)}
                >
                  <Trash size={16} />
                </button>
              </div>
            ))
          )}
        </div>
        <div className="sidebar-footer">
          <span className={`connection-hint ${offline ? "offline" : "online"}`}>
            {offline ? "离线：等待后端可用" : "已连接控制平面"}
          </span>
        </div>
      </aside>

      <section className="chat-workspace" aria-label="对话工作区">
        <header className="task-header">
          <div className="task-heading">
            <h1>{selected?.title || "开始新的对话"}</h1>
            <div className="task-meta">
              {selected ? (
                <>
                  <span className="live-status">
                    <span className="status-pulse" />
                    {sessionStatusLabel(selected.status)}
                  </span>
                  <span>会话 {selected.id.slice(0, 8)}</span>
                </>
              ) : (
                <span>发送消息会自动创建会话</span>
              )}
            </div>
          </div>
          <div className="header-actions">
            <ThemeSelect theme={theme} onChange={setTheme} />
          </div>
        </header>

        <InlineNotice notice={notice} tone={noticeTone} />

        <div className="chat-timeline" ref={timelineRef} aria-live="polite">
          {emptyTimeline ? (
            <div className="chat-empty">
              <ChatCircleDots size={44} weight="duotone" />
              <h2>向 AtlasAgent 提问</h2>
              <p>
                普通问题会直接得到模型回答；包含搜索、网页、文件、命令等意图的消息，
                会进入计划执行流水线并展示每一步进度。
              </p>
            </div>
          ) : null}
          {loadingMessages ? <p className="empty-hint">正在载入消息…</p> : null}
          {messages.map((message) => (
            <article key={message.id} className={`chat-bubble ${message.role}`} data-mid={message.id}>
              <header>
                <strong>{message.role === "user" ? "你" : "AtlasAgent"}</strong>
                <time>{formatMessageTime(message.created_at)}</time>
              </header>
              {message.role === "assistant" ? (
                <>
                  {reasoningMap[message.id] ? (
                    <ThinkingBlock reasoning={reasoningMap[message.id]} />
                  ) : null}
                  <MarkdownLite content={message.content} />
                </>
              ) : (
                <p className="plain-text">{message.content}</p>
              )}
            </article>
          ))}
          {liveThinking || liveAnswer ? (
            <article className="chat-bubble assistant streaming">
              <header>
                <strong>AtlasAgent</strong>
                <time>{liveAnswer ? "正在回答" : "正在思考"}</time>
              </header>
              {pacedThinking ? (
                <ThinkingBlock reasoning={pacedThinking} streaming={!liveAnswer} />
              ) : null}
              {liveAnswer ? <MarkdownLite content={liveAnswer} /> : null}
            </article>
          ) : null}
          {activity ? (
            <div className={`chat-activity ${activity.kind}`}>
              <ArrowClockwise size={15} className="spin" />
              <span>{activity.text}</span>
            </div>
          ) : null}
          {anchorSpacer ? <div aria-hidden className="anchor-spacer" /> : null}
        </div>

        <div className="composer-wrap">
          <div className="composer chat-composer">
            <textarea
              ref={composerRef}
              value={draft}
              rows={Math.min(6, Math.max(1, draft.split("\n").length))}
              onChange={(event) => setDraft(event.target.value)}
              onCompositionStart={() => {
                composingRef.current = true;
              }}
              onCompositionEnd={() => {
                composingRef.current = false;
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey && !composingRef.current) {
                  event.preventDefault();
                  void sendMessage();
                }
              }}
              placeholder="输入问题，Enter 发送，Shift+Enter 换行"
              aria-label="向 AtlasAgent 发送消息"
              disabled={sending}
            />
            {sending ? (
              <button
                className="send-button stop"
                type="button"
                onClick={stopStreaming}
                aria-label="停止本轮回答"
              >
                <Stop size={19} weight="fill" />
              </button>
            ) : (
              <button
                className="send-button"
                type="button"
                onClick={() => void sendMessage()}
                disabled={!draft.trim()}
                aria-label="发送消息"
              >
                <PaperPlaneRight size={19} weight="fill" />
              </button>
            )}
          </div>
        </div>
      </section>
    </>
  );
}
