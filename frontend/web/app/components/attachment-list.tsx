import { Download } from "lucide-react";

import { formatBytes, formatDateTime } from "../lib/format";
import { getDownloadUrl } from "../lib/file-api";
import type { SessionFileItem } from "../types";

type AttachmentListProps = {
  files: SessionFileItem[];
  onSelectFile?: (file: SessionFileItem) => void;
};

export function AttachmentList({ files, onSelectFile }: AttachmentListProps) {
  if (files.length === 0) {
    return null;
  }

  return (
    <div className="space-y-2">
      {files.map((file) => (
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
          <a
            className="shrink-0 rounded-md p-1 text-(--text-4) hover:bg-(--fill-2) hover:text-(--text-1)"
            href={getDownloadUrl(file.file)}
            title="下载文件"
          >
            <Download size={16} aria-hidden="true" />
          </a>
        </div>
      ))}
    </div>
  );
}
