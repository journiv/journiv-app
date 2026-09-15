import { useEffect, useState } from "react";
import {
  activateWaitingServiceWorker,
  getUpdateState,
  subscribeToUpdateState,
} from "./registerServiceWorker";

/**
 * Reads registerServiceWorker.ts's module-level update state as a hook,
 * rather than mounting vite-plugin-pwa's `useRegisterSW` -- that would
 * register a second worker instance. See registerServiceWorker.ts.
 */
export function usePwaUpdate() {
  const [needRefresh, setNeedRefresh] = useState(
    () => getUpdateState().needRefresh,
  );

  useEffect(
    () =>
      subscribeToUpdateState(() => {
        setNeedRefresh(getUpdateState().needRefresh);
      }),
    [],
  );

  return {
    updateReady: needRefresh,
    // Never call this without explicit user confirmation -- it reloads the
    // page. See UpdateBar.tsx.
    applyUpdate: activateWaitingServiceWorker,
  };
}
