import { requestApi } from "./api";
import type { ObservabilityCheckListData } from "../types";

export function fetchObservabilityChecks(): Promise<ObservabilityCheckListData> {
  return requestApi<ObservabilityCheckListData>("/api/observability/checks");
}
