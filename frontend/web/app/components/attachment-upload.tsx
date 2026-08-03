import { Paperclip } from "lucide-react";

type AttachmentUploadProps = {
  disabled: boolean;
  onUpload: (file: File) => void;
  uploading: boolean;
};

export function AttachmentUpload({
  disabled,
  onUpload,
  uploading,
}: AttachmentUploadProps) {
  return (
    <label
      className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-full border border-white/10 bg-white/[0.04] text-zinc-500 transition hover:border-blue-500/40 hover:text-zinc-100 disabled:cursor-not-allowed"
      title={uploading ? "附件上传中" : "上传附件"}
    >
      <Paperclip size={17} aria-hidden="true" />
      <input
        className="sr-only"
        disabled={disabled || uploading}
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) {
            onUpload(file);
          }
          event.target.value = "";
        }}
        type="file"
      />
    </label>
  );
}
