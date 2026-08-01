import { requestApi } from "./api";
import type {
  HarnessCaseListData,
  HarnessReplayData,
  HarnessRunData,
} from "../types";

export function fetchHarnessCases(): Promise<HarnessCaseListData> {
  return requestApi<HarnessCaseListData>("/api/harness/cases");
}

export function runHarnessCase(caseId: string): Promise<HarnessRunData> {
  return requestApi<HarnessRunData>(`/api/harness/cases/${caseId}/run`, {
    method: "POST",
    body: JSON.stringify({ mode: "simulate" }),
  });
}

export function replayHarnessRun(runId: string): Promise<HarnessReplayData> {
  return requestApi<HarnessReplayData>(`/api/harness/runs/${runId}/replay`);
}
