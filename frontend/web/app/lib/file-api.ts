import { ApiRequestError, requestApi } from "./api";
import type { ApiResponse, FilePreviewData, UploadedFile } from "../types";

export async function uploadFile(file: File): Promise<UploadedFile> {
  const formData = new FormData();
  formData.append("upload", file);

  const response = await fetch("/api/files", {
    method: "POST",
    body: formData,
  });
  const payload = (await response.json()) as ApiResponse<UploadedFile>;
  if (!response.ok || payload.code >= 400) {
    const message = payload.error?.user_message || payload.message || `HTTP ${response.status}`;
    throw new ApiRequestError(message, payload.code, response.status, payload.error ?? null);
  }
  if (!payload.data) {
    throw new Error("empty response");
  }
  return payload.data;
}

export function getDownloadUrl(file: UploadedFile): string {
  return file.download_url;
}

export function fetchFilePreview(fileId: string): Promise<FilePreviewData> {
  return requestApi<FilePreviewData>(`/api/files/${fileId}/preview`);
}
