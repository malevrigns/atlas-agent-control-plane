import { requestApi } from "./api";
import type { ProductAcceptanceChecklistData } from "../types";


export function fetchProductAcceptanceChecks(): Promise<ProductAcceptanceChecklistData> {
  return requestApi<ProductAcceptanceChecklistData>("/api/acceptance/checks");
}
