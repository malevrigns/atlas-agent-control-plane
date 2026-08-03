import { requestApi } from "./api";
import type {
  AppSettingsData,
  SettingsIntegration,
  SettingsModule,
} from "../types";

export function fetchAppSettings(): Promise<AppSettingsData> {
  return requestApi<AppSettingsData>("/api/config/app");
}

export function updateSettingsModule(
  moduleKey: string,
  payload: { enabled?: boolean; default_item?: string },
): Promise<SettingsModule> {
  return requestApi<SettingsModule>(`/api/config/modules/${moduleKey}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function createSettingsIntegration(payload: {
  kind: string;
  name: string;
  description: string;
  endpoint: string;
}): Promise<SettingsIntegration> {
  return requestApi<SettingsIntegration>("/api/config/integrations", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function deleteSettingsIntegration(
  integrationId: string,
): Promise<SettingsIntegration> {
  return requestApi<SettingsIntegration>(
    `/api/config/integrations/${encodeURIComponent(integrationId)}`,
    { method: "DELETE" },
  );
}

export function updateSettingsItem(
  moduleKey: string,
  itemName: string,
  payload: { enabled: boolean },
): Promise<SettingsModule> {
  return requestApi<SettingsModule>(
    `/api/config/modules/${moduleKey}/items/${encodeURIComponent(itemName)}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

export function deleteSettingsItem(
  moduleKey: string,
  itemName: string,
): Promise<SettingsModule> {
  return requestApi<SettingsModule>(
    `/api/config/modules/${moduleKey}/items/${encodeURIComponent(itemName)}`,
    { method: "DELETE" },
  );
}
