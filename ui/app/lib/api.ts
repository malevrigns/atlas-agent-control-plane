import type { ApiErrorData, ApiResponse } from "../types";

export class ApiRequestError extends Error {
  apiError: ApiErrorData | null;
  code: number;
  status: number;

  constructor(message: string, code: number, status: number, apiError: ApiErrorData | null) {
    super(message);
    this.name = "ApiRequestError";
    this.apiError = apiError;
    this.code = code;
    this.status = status;
  }
}

export async function requestApi<T>(
  url: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const payload = (await response.json()) as ApiResponse<T>;
  if (!response.ok || payload.code >= 400) {
    const message = payload.error?.user_message || payload.message || `HTTP ${response.status}`;
    throw new ApiRequestError(message, payload.code, response.status, payload.error ?? null);
  }
  if (payload.data === null) {
    throw new Error("empty response");
  }
  return payload.data;
}
