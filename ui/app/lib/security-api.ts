import { requestApi } from "./api";
import type { SecurityCheckListData } from "../types";


export function fetchSecurityChecks(): Promise<SecurityCheckListData> {
  return requestApi<SecurityCheckListData>("/api/security/checks");
}
