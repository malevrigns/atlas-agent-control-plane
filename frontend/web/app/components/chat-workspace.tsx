import { AttachmentList } from "./attachment-list";
import { AttachmentUpload } from "./attachment-upload";
import { ChatInput } from "./chat-input";
import { ContextPanel } from "./context-panel";
import { ConversationTimeline } from "./conversation-timeline";
import { FilePreviewPanel } from "./file-preview-panel";
import { SessionControlBar } from "./session-control-bar";
import { ToolPreviewPanel } from "./tool-preview-panel";
import { useState } from "react";
import type {
  AgentPlan,
  AgentTaskItem,
  ChatMessage,
  FilePreviewData,
  LoadState,
  SessionContextData,
  SessionEventItem,
  SessionFileItem,
  SessionItem,
  VncStatusData,
} from "../types";

type ChatWorkspaceProps = {
  attachments: SessionFileItem[];
  draft: string;
  clearingUnread: boolean;
  events: LoadState<SessionEventItem[]>;
  context: LoadState<SessionContextData | null>;
  files: LoadState<SessionFileItem[]>;
  filePreview: LoadState<FilePreviewData | null>;
  liveAnswer: string;
  liveThinking: string;
  messages: LoadState<ChatMessage[]>;
  onClearUnread: () => void;
  onRefreshContext: () => void;
  onRefreshVnc: () => void;
  onDraftChange: (value: string) => void;
  onPreviewFile: (fileId: string) => void;
  onSend: () => void;
  onSelectFile: (file: SessionFileItem | null) => void;
  onStop: () => void;
  onUploadFile: (file: File) => void;
  selectedFile: SessionFileItem | null;
  vnc: LoadState<VncStatusData>;
  selectedSession: SessionItem | null;
  plan: AgentPlan | null;
  task: AgentTaskItem | null;
  planning: boolean;
  executingPlan: boolean;
  sending: boolean;
  stopping: boolean;
  uploadingFile: boolean;
};

export function ChatWorkspace({
  attachments,
  clearingUnread,
  context,
  draft,
  events,
  files,
  filePreview,
  liveAnswer,
  liveThinking,
  messages,
  onClearUnread,
  onRefreshContext,
  onRefreshVnc,
  onDraftChange,
  onPreviewFile,
  onSend,
  onSelectFile,
  onStop,
  onUploadFile,
  selectedFile,
  vnc,
  selectedSession,
  plan,
  task,
  planning,
  executingPlan,
  sending,
  stopping,
  uploadingFile,
}: ChatWorkspaceProps) {
  const [selectedToolEventId, setSelectedToolEventId] = useState<string | null>(
    null,
  );
  const [showContextPreview, setShowContextPreview] = useState(false);
  const hasToolPreview = selectedToolEventId !== null;
  const hasFilePreview =
    !showContextPreview && selectedToolEventId === null && selectedFile !== null;
  const hasPreview = hasToolPreview || hasFilePreview || showContextPreview;

  function openFilePreview(file: SessionFileItem) {
    setShowContextPreview(false);
    setSelectedToolEventId(null);
    onSelectFile(file);
    onPreviewFile(file.file.id);
  }

  return (
    <section className="relative flex h-full min-h-0 gap-0 overflow-hidden bg-transparent">
      <div className="chat-grid-overlay pointer-events-none absolute inset-0" />
      <div className="chat-backdrop pointer-events-none absolute inset-0" />
      <div
        className={`relative z-10 flex min-h-0 flex-1 flex-col overflow-hidden ${
          hasPreview ? "" : "mx-auto w-full max-w-[780px]"
        }`}
      >
        <SessionControlBar
          clearingUnread={clearingUnread}
          onClearUnread={onClearUnread}
          onOpenContext={() => {
            setSelectedToolEventId(null);
            onSelectFile(null);
            setShowContextPreview(true);
            onRefreshContext();
          }}
          onStop={onStop}
          selectedSession={selectedSession}
          stopping={stopping}
        />
        <ConversationTimeline
          events={events}
          liveAnswer={liveAnswer}
          liveThinking={liveThinking}
          messages={messages}
          onSelectToolEvent={(eventId) => {
            setShowContextPreview(false);
            onSelectFile(null);
            setSelectedToolEventId(eventId);
          }}
          executing={executingPlan}
          plan={plan}
          planning={planning}
          selectedToolEventId={selectedToolEventId}
          task={task}
        />
        <div className="mt-auto shrink-0 bg-(--page)/85 px-8 py-4 backdrop-blur-2xl max-md:px-4 max-sm:py-2">
          <div className="mx-auto mb-3 h-px w-[220px] bg-gradient-to-r from-transparent via-blue-500/30 to-transparent max-sm:mb-2" />
          <div className="mx-auto max-w-5xl">
            <div className="mb-2 flex flex-wrap items-center justify-start gap-2">
              <div className="flex items-center gap-3">
                <AttachmentUpload
                  disabled={!selectedSession}
                  onUpload={onUploadFile}
                  uploading={uploadingFile}
                />
                <AttachmentList files={attachments} onSelectFile={openFilePreview} />
              </div>
            </div>
          </div>
          <ChatInput
            disabled={!selectedSession}
            draft={draft}
            onDraftChange={onDraftChange}
            onSend={onSend}
            sending={sending || planning || executingPlan}
          />
        </div>
      </div>

      {hasToolPreview ? (
        <aside
          aria-label="当前工具详情工作区"
          className="relative z-20 h-full w-[600px] shrink-0 border-l border-(--line) bg-(--surface)/95 py-2 pr-2 shadow-2xl shadow-black/40 max-xl:absolute max-xl:inset-x-3 max-xl:bottom-3 max-xl:h-[70dvh] max-xl:w-auto max-xl:rounded-3xl max-xl:border max-xl:p-2"
        >
          <ToolPreviewPanel
            events={events}
            onClose={() => setSelectedToolEventId(null)}
            onRefreshVnc={onRefreshVnc}
            selectedToolEventId={selectedToolEventId}
            vnc={vnc}
          />
        </aside>
      ) : null}
      {hasFilePreview ? (
        <aside
          aria-label="文件预览工作区"
          className="relative z-20 h-full w-[600px] shrink-0 border-l border-(--line) bg-(--surface)/95 py-2 pr-2 shadow-2xl shadow-black/40 max-xl:absolute max-xl:inset-x-3 max-xl:bottom-3 max-xl:h-[70dvh] max-xl:w-auto max-xl:rounded-3xl max-xl:border max-xl:p-2"
        >
          <FilePreviewPanel
            onClose={() => onSelectFile(null)}
            onPreview={onPreviewFile}
            preview={filePreview}
            selectedFile={selectedFile}
          />
        </aside>
      ) : null}
      {showContextPreview ? (
        <aside
          aria-label="上下文工作区"
          className="relative z-20 h-full w-[600px] shrink-0 border-l border-(--line) bg-(--surface)/95 py-2 pr-2 shadow-2xl shadow-black/40 max-xl:absolute max-xl:inset-x-3 max-xl:bottom-3 max-xl:h-[76dvh] max-xl:w-auto max-xl:rounded-3xl max-xl:border max-xl:p-2"
        >
          <ContextPanel
            context={context}
            disabled={!selectedSession}
            onClose={() => setShowContextPreview(false)}
            onRefresh={onRefreshContext}
          />
        </aside>
      ) : null}
    </section>
  );
}
