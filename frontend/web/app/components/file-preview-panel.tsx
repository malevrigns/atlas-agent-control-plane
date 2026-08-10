import {
  BadgeCheck,
  Braces,
  FileText,
  Maximize2,
  Quote,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";

import type { FilePreviewData, LoadState, SessionFileItem } from "../types";

type FilePreviewPanelProps = {
  onClose?: () => void;
  onPreview: (fileId: string) => void;
  preview: LoadState<FilePreviewData | null>;
  selectedFile: SessionFileItem | null;
};

export function FilePreviewPanel({
  onClose,
  onPreview,
  preview,
  selectedFile,
}: FilePreviewPanelProps) {
  const [expanded, setExpanded] = useState(false);

  if (!selectedFile) {
    return (
      <div className="rounded-2xl border border-(--line) bg-(--fill-1) p-4 text-sm text-(--text-4)">
        选择文件后可以查看文本预览
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-[24px] border border-(--line) bg-(--surface) shadow-2xl shadow-black/50">
      <div className="flex items-center justify-between gap-3 border-b border-(--line) bg-white/[0.025] px-4 py-3">
        <div className="min-w-0">
          <div className="mb-1 text-xs font-medium uppercase tracking-[0.18em] text-(--text-5)">
            File Preview
          </div>
          <h3 className="truncate text-sm font-semibold text-(--text-1)">
            {selectedFile.file.original_name}
          </h3>
          <p className="mt-1 text-xs text-(--text-4)">
            解析摘要、引用片段和原文预览会在这里展示
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          <button
            aria-label="加载文件预览"
            className="flex h-8 w-8 items-center justify-center rounded-xl border border-(--line) bg-(--fill-1) text-(--text-3) transition hover:bg-(--fill-2) hover:text-(--text-1)"
            onClick={() => onPreview(selectedFile.file.id)}
            title="查看预览"
            type="button"
          >
            <FileText size={16} aria-hidden="true" />
          </button>
          <button
            aria-label="展开文件预览"
            className="flex h-8 w-8 items-center justify-center rounded-xl border border-(--line) bg-(--fill-1) text-(--text-3) transition hover:bg-(--fill-2) hover:text-(--text-1) disabled:cursor-not-allowed disabled:opacity-40"
            disabled={preview.type !== "ready" || !preview.data}
            onClick={() => setExpanded(true)}
            title="展开预览"
            type="button"
          >
            <Maximize2 size={15} aria-hidden="true" />
          </button>
          {onClose ? (
            <button
              aria-label="关闭文件预览"
              className="flex h-8 w-8 items-center justify-center rounded-xl border border-(--line) bg-(--fill-1) text-(--text-3) transition hover:bg-(--fill-2) hover:text-(--text-1)"
              onClick={onClose}
              title="关闭预览"
              type="button"
            >
              <X size={15} aria-hidden="true" />
            </button>
          ) : null}
        </div>
      </div>

      <div className="max-h-[30rem] overflow-auto p-4">
        {preview.type === "loading" ? (
          <p className="text-sm text-(--text-4)">预览加载中</p>
        ) : preview.type === "error" ? (
          <p className="text-sm text-rose-300">{preview.message}</p>
        ) : preview.data ? (
          <FilePreviewContent preview={preview.data} compact />
        ) : (
          <p className="text-sm text-(--text-4)">点击右上角按钮加载预览</p>
        )}
      </div>

      {expanded && preview.type === "ready" && preview.data ? (
        <FilePreviewDialog
          name={selectedFile.file.original_name}
          onClose={() => setExpanded(false)}
          preview={preview.data}
        />
      ) : null}
    </div>
  );
}

function FilePreviewContent({
  compact = false,
  preview,
}: {
  compact?: boolean;
  preview: FilePreviewData;
}) {
  const metaItems = [
    ["类型", preview.file_type],
    ["语言", preview.language || "-"],
    ["行数", String(preview.line_count)],
  ];
  const contentMaxHeight = compact ? "max-h-56" : "max-h-[34rem]";

  return (
    <div className="grid gap-4">
      <div className="rounded-2xl border border-emerald-400/20 bg-emerald-400/[0.06] p-4">
        <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-emerald-300">
          <BadgeCheck size={14} aria-hidden="true" />
          Parse Summary
        </div>
        <p className="text-sm leading-6 text-(--text-1)">{preview.summary}</p>
        <p className="mt-2 text-xs leading-5 text-(--text-4)">
          {preview.parse_message}
        </p>
      </div>

      <dl className="grid grid-cols-3 gap-2 text-xs max-sm:grid-cols-1">
        {metaItems.map(([label, value]) => (
          <div
            className="rounded-2xl border border-(--line) bg-(--fill-1) p-3"
            key={label}
          >
            <dt className="mb-1 uppercase tracking-[0.16em] text-(--text-5)">
              {label}
            </dt>
            <dd className="truncate font-medium text-(--text-2)">{value}</dd>
          </div>
        ))}
      </dl>

      {preview.references.length > 0 ? (
        <div className="rounded-2xl border border-(--line) bg-(--fill-1) p-4">
          <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-(--text-4)">
            <Quote size={14} aria-hidden="true" />
            References
          </div>
          <div className="grid gap-3">
            {preview.references.map((reference, index) => (
              <article
                className="rounded-2xl border border-(--line) bg-(--field) p-3"
                key={`${reference.label}-${index}`}
              >
                <div className="mb-2 flex items-center justify-between gap-3">
                  <h4 className="truncate text-sm font-semibold text-(--text-1)">
                    {reference.label}
                  </h4>
                  {reference.start_line ? (
                    <span className="shrink-0 rounded-full border border-(--line) px-2 py-1 text-[11px] text-(--text-4)">
                      L{reference.start_line}
                      {reference.end_line && reference.end_line !== reference.start_line
                        ? `-L${reference.end_line}`
                        : ""}
                    </span>
                  ) : null}
                </div>
                <p className="line-clamp-3 whitespace-pre-wrap break-words text-xs leading-5 text-(--text-3)">
                  {reference.excerpt}
                </p>
              </article>
            ))}
          </div>
        </div>
      ) : null}

      <div className="rounded-2xl border border-(--line) bg-(--field)">
        <div className="flex items-center gap-2 border-b border-(--line) px-4 py-3 text-xs font-semibold uppercase tracking-[0.18em] text-(--text-4)">
          <Braces size={14} aria-hidden="true" />
          Content
        </div>
        <div className={`${contentMaxHeight} overflow-auto p-4`}>
          {preview.content ? (
            <pre className="whitespace-pre-wrap break-words text-xs leading-5 text-(--text-2)">
              {preview.content}
              {preview.truncated
                ? "\n\n预览已裁剪，可在文件服务中查看完整内容。"
                : ""}
            </pre>
          ) : (
            <p className="text-sm text-(--text-4)">该文件没有可展示的文本内容。</p>
          )}
        </div>
      </div>
    </div>
  );
}


function FilePreviewDialog({
  name,
  onClose,
  preview,
}: {
  name: string;
  onClose: () => void;
  preview: FilePreviewData;
}) {
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 bg-black/70 p-6 backdrop-blur-sm max-sm:p-3">
      <div
        aria-labelledby="file-preview-title"
        aria-modal="true"
        className="mx-auto flex h-full max-w-5xl flex-col overflow-hidden rounded-[28px] border border-(--line) bg-(--surface) shadow-2xl shadow-black"
        role="dialog"
      >
        <div className="flex items-center justify-between gap-3 border-b border-(--line) px-5 py-4">
          <div className="min-w-0">
            <h2
              className="truncate text-base font-semibold text-(--text-1)"
              id="file-preview-title"
            >
              {name}
            </h2>
            <p className="mt-1 text-xs text-(--text-4)">
              {preview.truncated ? "当前显示裁剪预览。" : "完整预览内容"}
            </p>
          </div>
          <button
            aria-label="关闭文件预览"
            className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-(--line) bg-(--fill-1) text-(--text-3) hover:bg-(--fill-2) hover:text-(--text-1)"
            onClick={onClose}
            title="关闭"
            type="button"
          >
            <X size={17} aria-hidden="true" />
          </button>
        </div>
        <div className="flex-1 overflow-auto bg-(--field) p-5">
          <FilePreviewContent preview={preview} />
        </div>
      </div>
    </div>
  );
}
