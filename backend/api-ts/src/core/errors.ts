export type ErrorType =
  | "validation_error"
  | "business_error"
  | "not_found"
  | "timeout"
  | "dependency_error"
  | "tool_error"
  | "internal_error";

export type ErrorSource =
  | "api"
  | "agent"
  | "dependency"
  | "tool"
  | "llm"
  | "sandbox"
  | "mcp"
  | "a2a";

export class AppError extends Error {
  readonly code: number;
  readonly statusCode: number;
  readonly errorType: ErrorType;
  readonly source: ErrorSource;
  readonly suggestion: string | null;
  readonly details: Record<string, unknown>;

  constructor(
    message: string,
    options: {
      code?: number;
      statusCode?: number;
      errorType?: ErrorType;
      source?: ErrorSource;
      suggestion?: string | null;
      details?: Record<string, unknown>;
    } = {},
  ) {
    super(message);
    this.name = "AppError";
    this.code = options.code ?? options.statusCode ?? 400;
    this.statusCode = options.statusCode ?? options.code ?? 400;
    this.errorType = options.errorType ?? inferErrorType(this.statusCode);
    this.source = options.source ?? "api";
    this.suggestion = options.suggestion ?? suggestionFor(this.errorType);
    this.details = options.details ?? {};
  }
}

function inferErrorType(statusCode: number): ErrorType {
  if (statusCode === 404) {
    return "not_found";
  }
  if (statusCode === 422) {
    return "validation_error";
  }
  if (statusCode >= 500) {
    return "internal_error";
  }
  return "business_error";
}

export function suggestionFor(errorType: ErrorType): string {
  switch (errorType) {
    case "validation_error":
      return "请检查请求体、路径参数和查询参数是否符合接口要求。";
    case "not_found":
      return "请确认资源 ID 是否存在，或刷新列表后重试。";
    case "timeout":
      return "请稍后重试；若持续超时，检查上游模型或沙箱是否可达。";
    case "internal_error":
      return "请复制 request_id 查看后端日志，或稍后重试。";
    default:
      return "请根据错误说明调整请求后重试。";
  }
}

export type ApiErrorBody = {
  type: string;
  source: string;
  user_message: string;
  suggestion: string;
  request_id: string | null;
  details: Record<string, unknown> | null;
};

export type ApiEnvelope<T> = {
  code: number;
  message: string;
  data: T | null;
  error: ApiErrorBody | null;
};

export function ok<T>(data: T, message = "success"): ApiEnvelope<T> {
  return { code: 200, message, data, error: null };
}

export function fail(
  error: AppError,
  requestId: string | null,
): ApiEnvelope<null> {
  return {
    code: error.code,
    message: error.message,
    data: null,
    error: {
      type: error.errorType,
      source: error.source,
      user_message: error.message,
      suggestion: error.suggestion ?? suggestionFor(error.errorType),
      request_id: requestId,
      details: Object.keys(error.details).length ? error.details : null,
    },
  };
}
