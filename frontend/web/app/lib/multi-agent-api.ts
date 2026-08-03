import { requestApi } from "./api";
import type { MultiAgentRoleListData } from "../types";


export function fetchMultiAgentRoles(): Promise<MultiAgentRoleListData> {
  return requestApi<MultiAgentRoleListData>("/api/multi-agent/roles");
}
