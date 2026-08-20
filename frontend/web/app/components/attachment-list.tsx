import { Download, Loader2, Trash2 } from "lucide-react";

import { formatBytes, formatDateTime } from "../lib/format";
import { getDownloadUrl } from "../lib/file-api";
import type { SessionFileItem } from "../types";

type AttachmentListProps = {
  files: SessionFileItem[];
  onSelectFile?: (file: SessionFileItem) => void;
  onDeleteFile?: (file: SessionFileItem) => void;
  deletingId?: string | null;
};

export function AttachmentList({
  files,
  onSelectFile,
  onDeleteFile,
  deletingId,
}: AttachmentListProps) {
  if (files.length === 0) {
    return null;
  }

  return (
    <div className="space-y-2">
      {files.map((file) => {
        const deleting = deletingId === file.id;
        return (
          <div
            className="flex items-center justify-between gap-3 rounded-2xl border border-(--line) bg-(--fill-1) px-3 py-2 text-sm transition hover:border-(--accent)/40"
            key={file.id}
          >
            <button
              className="min-w-0 flex-1 text-left"
              onClick={() => onSelectFile?.(file)}
              type="button"
            >
              <span className="block truncate font-medium text-(--text-2)">
                {file.file.original_name}
              </span>
              <span className="mt-1 block text-xs text-(--text-5)">
                {formatBytes(file.file.size)} · {formatDateTime(file.created_at)}
              </span>
            </button>
            <div className="flex shrink-0 items-center gap-1">
              <a
                className="rounded-md p-1 text-(--text-4) hover:bg-(--fill-2) hover:text-(--text-1)"
                href={getDownloadUrl(file.file)}
                title="下载文件"
              >
                <Download size={16} aria-hidden="true" />
              </a>
              {onDeleteFile ? (
                <button
                  aria-label="删除附件"
                  className="rounded-md p-1 text-(--text-4) hover:bg-(--fill-2) hover:text-rose-400 disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={deleting}
                  onClick={() => onDeleteFile(file)}
                  title="删除附件"
                  type="button"
                >
                  {deleting ? (
                    <Loader2 className="animate-spin" size={16} aria-hidden="true" />
                  ) : (
                    <Trash2 size={16} aria-hidden="true" />
                  )}
                </button>
              ) : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}
