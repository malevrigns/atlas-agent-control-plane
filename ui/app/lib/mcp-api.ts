import { requestApi } from "./api";
import type { McpServerListData, McpToolListData } from "../types";


export function fetchMcpServers(): Promise<McpServerListData> {
  return requestApi<McpServerListData>("/api/mcp/servers");
}


export function fetchMcpTools(): Promise<McpToolListData> {
  return requestApi<McpToolListData>("/api/mcp/tools");
}

