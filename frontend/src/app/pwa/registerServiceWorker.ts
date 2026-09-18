import { registerSW } from "virtual:pwa-register";

/**
 * Thin wrapper around vite-plugin-pwa's vanilla `virtual:pwa-register`,
 * called once from main.tsx after retireRootFlutterWorker() resolves and
 * after first render -- a registration racing the boot session restore
 * would slow down the launch the user sees.
 *
 * `usePwaUpdate.ts` (the update-bar UI) reads this module's state instead of
 * vite-plugin-pwa's React `useRegisterSW` hook, so there is exactly one
 * registration: calling both would register the worker twice.
 */

type UpdateListener = () => void;

const listeners = new Set<UpdateListener>();
let needRefresh = false;
let offlineReady = false;
let reloadAndActivate: ((reloadPage?: boolean) => Promise<void>) | undefined;
let registered = false;

function notify() {
  for (const listener of listeners) listener();
}

export function registerServiceWorker() {
  if (registered) return;
  registered = true;
  if (!("serviceWorker" in navigator)) return;

  reloadAndActivate = registerSW({
    immediate: true,
    onNeedRefresh() {
      needRefresh = true;
      notify();
    },
    onOfflineReady() {
      offlineReady = true;
      notify();
    },
  });
}

export function getUpdateState() {
  return { needRefresh, offlineReady };
}

export function subscribeToUpdateState(listener: UpdateListener) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Never call this without explicit user confirmation -- see usePwaUpdate.ts. */
export async function activateWaitingServiceWorker(): Promise<void> {
  if (!reloadAndActivate) return;
  await reloadAndActivate(true);
}

export function resetServiceWorkerRegistrationForTests() {
  registered = false;
  needRefresh = false;
  offlineReady = false;
  reloadAndActivate = undefined;
  listeners.clear();
}
