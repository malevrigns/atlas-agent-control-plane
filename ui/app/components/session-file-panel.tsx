import { Download, Eye } from "lucide-react";

import { FilePreviewPanel } from "./file-preview-panel";
import { formatBytes, formatDateTime } from "../lib/format";
import { getDownloadUrl } from "../lib/file-api";
import type {
  FilePreviewData,
  LoadState,
  SessionFileItem,
} from "../types";

type SessionFilePanelProps = {
  files: LoadState<SessionFileItem[]>;
  onPreview: (fileId: string) => void;
  onSelectFile: (file: SessionFileItem) => void;
  preview: LoadState<FilePreviewData | null>;
  selectedFile: SessionFileItem | null;
};

export function SessionFilePanel({
  files,
  onPreview,
  onSelectFile,
  preview,
  selectedFile,
}: SessionFilePanelProps) {
  return (
    <section className="space-y-4 rounded-md border border-slate-200 bg-slate-50 p-4">
      <div>
        <h2 className="text-base font-semibold text-slate-950">会话文件</h2>
        <p className="mt-1 text-sm text-slate-500">
          当前会话上传过的附件会保存在这里
        </p>
      </div>

      {files.type === "loading" ? (
        <p className="rounded-md bg-white px-3 py-2 text-sm text-slate-500">
          文件加载中
        </p>
      ) : files.type === "error" ? (
        <p className="rounded-md bg-white px-3 py-2 text-sm text-rose-600">
          {files.message}
        </p>
      ) : files.data.length === 0 ? (
        <p className="rounded-md bg-white px-3 py-2 text-sm text-slate-500">
          当前会话还没有文件
        </p>
      ) : (
        <div className="space-y-2">
          {files.data.map((item) => {
            const active = selectedFile?.id === item.id;
            return (
              <div
                className={`rounded-md border bg-white px-3 py-2 text-sm transition ${
                  active ? "border-slate-400" : "border-slate-200"
                }`}
                key={item.id}
              >
                <button
                  className="flex w-full min-w-0 items-start justify-between gap-3 text-left"
                  onClick={() => onSelectFile(item)}
                  type="button"
                >
                  <span className="min-w-0">
                    <span className="block truncate font-medium text-slate-800">
                      {item.file.original_name}
                    </span>
                    <span className="mt-1 block text-xs text-slate-500">
                      {formatBytes(item.file.size)} · {formatDateTime(item.created_at)}
                    </span>
                  </span>
                  <Eye className="mt-0.5 shrink-0 text-slate-500" size={16} aria-hidden="true" />
                </button>
                <a
                  className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-slate-600 hover:text-slate-950"
                  href={getDownloadUrl(item.file)}
                >
                  <Download size={13} aria-hidden="true" />
                  下载文件
                </a>
              </div>
            );
          })}
        </div>
      )}

      <FilePreviewPanel
        onPreview={onPreview}
        preview={preview}
        selectedFile={selectedFile}
      />
    </section>
  );
}
