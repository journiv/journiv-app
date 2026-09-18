import { useEffect, useState } from "react";
import type { RestoreResult } from "../../api/auth/session";
import { attemptRefresh, sessionStore } from "../../api/auth/session";

/**
 * The app's boot-resolved mode (docs/features/pwa.md). Derived once from
 * `sessionStore.restore()`'s result and the session hint, then kept in sync
 * as the session resolves further -- never re-derived from
 * `navigator.onLine`.
 *
 * | restore() | mode |
 * | --- | --- |
 * | "restored" | normal |
 * | "unauthenticated" | unauthenticated |
 * | "offline" + a hint | offline-restricted |
 * | "offline", no hint | unauthenticated (LoginPage already fails closed
 * |                      honestly when instanceConfig can't load offline) |
 */
export type BootMode = "normal" | "unauthenticated" | "offline-restricted";

let currentMode: BootMode = "unauthenticated";
const listeners = new Set<(mode: BootMode) => void>();

function setBootMode(mode: BootMode) {
  if (mode === currentMode) return;
  currentMode = mode;
  for (const listener of listeners) listener(mode);
}

export function getBootMode(): BootMode {
  return currentMode;
}

export function subscribeBootMode(listener: (mode: BootMode) => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function deriveInitialBootMode(
  restoreResult: RestoreResult,
  hasHint: boolean,
): BootMode {
  if (restoreResult === "restored") return "normal";
  if (restoreResult === "unauthenticated") return "unauthenticated";
  return hasHint ? "offline-restricted" : "unauthenticated";
}

let syncStarted = false;

/**
 * Call once from main.tsx after the first `restore()` settles. Sets the
 * initial mode and then keeps it current as the session resolves further:
 * a background `attemptRefresh()` succeeding upgrades an offline-restricted
 * boot to normal in place, no reload (docs/features/pwa.md); a definite
 * 401/403, or an explicit sign-out, moves to unauthenticated the same way.
 */
export function initBootMode(restoreResult: RestoreResult) {
  // A live access token outranks restoreResult. When navigator.onLine is
  // false, restore() returns "offline" *provisionally* and leaves the refresh
  // running; on a LAN-reachable server that request can land while main.tsx
  // is still awaiting hydrateOfflineCache(). The token is then already set by
  // the time this runs, and trusting the stale "offline" would strand a fully
  // authenticated session behind OfflineBar for the rest of its life -- the
  // notify() that would have corrected it fired before anything subscribed.
  setBootMode(
    sessionStore.getAccessToken()
      ? "normal"
      : deriveInitialBootMode(restoreResult, sessionStore.readHint() !== null),
  );
  if (syncStarted) return;
  syncStarted = true;
  sessionStore.subscribe((accessToken) => {
    setBootMode(accessToken ? "normal" : "unauthenticated");
  });
  // The retry an `online` event triggers (docs/features/pwa.md,
  // useOnlineStatus.ts) -- opportunistic only. attemptRefresh() is
  // single-flight, so this can never race the boot attempt or a runtime 401
  // retry already in progress.
  if (typeof window !== "undefined") {
    window.addEventListener("online", () => {
      if (currentMode !== "normal") void attemptRefresh();
    });
  }
}

export function useBootMode(): BootMode {
  const [mode, setMode] = useState(getBootMode);
  useEffect(() => subscribeBootMode(setMode), []);
  return mode;
}

export function resetBootModeForTests() {
  currentMode = "unauthenticated";
  syncStarted = false;
  listeners.clear();
}
