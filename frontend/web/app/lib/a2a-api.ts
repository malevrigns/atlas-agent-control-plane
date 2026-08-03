import { requestApi } from "./api";
import type {
  A2aAgentCardData,
  A2aConceptsData,
  A2aRemoteAgentListData,
} from "../types";


export function fetchA2aConcepts(): Promise<A2aConceptsData> {
  return requestApi<A2aConceptsData>("/api/a2a/concepts");
}


export function fetchA2aAgentCard(): Promise<A2aAgentCardData> {
  return requestApi<A2aAgentCardData>("/api/a2a/agents/demo_researcher/card");
}


export function fetchA2aAgents(): Promise<A2aRemoteAgentListData> {
  return requestApi<A2aRemoteAgentListData>("/api/a2a/agents");
}
