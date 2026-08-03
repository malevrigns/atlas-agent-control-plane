import { useEffect, useMemo } from "react";

import { useSessionStore } from "../stores/session-store";

export function useSessionWorkspace() {
  const store = useSessionStore();

  useEffect(() => {
    store.refreshSessions();
  }, []);

  useEffect(() => {
    if (store.selectedSessionId) {
      store.loadSessionDetail(store.selectedSessionId);
    }
  }, [store.selectedSessionId]);

  const sessionItems = store.sessions.type === "ready" ? store.sessions.data : [];
  const selectedSession = useMemo(
    () =>
      sessionItems.find((item) => item.id === store.selectedSessionId) ?? null,
    [sessionItems, store.selectedSessionId],
  );

  return {
    ...store,
    selectedSession,
    sessionItems,
  };
}
