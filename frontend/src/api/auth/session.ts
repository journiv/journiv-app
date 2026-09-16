import { apiBaseUrl } from "../client/baseUrl";

/**
 * The durable session model (docs/features/authentication.md):
 *
 * - The access token (15 min) lives only in a module-level variable. It is
 *   never written to any storage, so it dies with the page.
 * - The refresh token (7 days) lives only in the `journiv_refresh` HttpOnly
 *   cookie the backend sets; this page can never read it.
 * - `hint` is a non-credential breadcrumb in localStorage that lets the app
 *   boot into the shell (or offline-restricted mode) without flashing
 *   /login while the cookie-based restore is in flight.
 */
export type SessionHint = { version: 1; userId: string; signedInAt: string };

export type RestoreResult =
  | "restored"
  | "unauthenticated"
  | "offline"
  | "superseded";

type SessionListener = (accessToken: string | null) => void;

const HINT_KEY = "journiv.session-hint.v1";
const TOMBSTONE_KEY = "journiv.logout-pending.v1";
/** Superseded by the in-memory token + HttpOnly cookie model; dropped on
 *  first load so a tab left open from before this change can't keep a
 *  stale refresh token sitting in sessionStorage. */
const LEGACY_SESSION_KEY = "journiv.session.v1";
const RESTORE_TIMEOUT_MS = 5000;

let accessToken: string | null = null;
let sessionGeneration = 0;
const listeners = new Set<SessionListener>();

function notify() {
  for (const listener of listeners) listener(accessToken);
}

try {
  sessionStorage.removeItem(LEGACY_SESSION_KEY);
} catch {
  // Private browsing / storage disabled — nothing to clean up.
}

function readHint(): SessionHint | null {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(HINT_KEY) ?? "null");
    if (!value || typeof value !== "object") return null;
    const hint = value as SessionHint;
    return hint.version === 1 &&
      typeof hint.userId === "string" &&
      hint.userId.length > 0 &&
      typeof hint.signedInAt === "string"
      ? hint
      : null;
  } catch {
    return null;
  }
}

function writeHint(hint: SessionHint) {
  try {
    localStorage.setItem(HINT_KEY, JSON.stringify(hint));
  } catch {
    // Best-effort: losing the hint only costs a flash of /login on next boot.
  }
}

function clearHint() {
  try {
    localStorage.removeItem(HINT_KEY);
  } catch {
    // Best-effort.
  }
}

function hasTombstone(): boolean {
  try {
    return localStorage.getItem(TOMBSTONE_KEY) !== null;
  } catch {
    return false;
  }
}

function writeTombstone() {
  try {
    localStorage.setItem(TOMBSTONE_KEY, "1");
  } catch {
    // Best-effort: worst case a later offline logout can't be retried.
  }
}

function clearTombstone() {
  try {
    localStorage.removeItem(TOMBSTONE_KEY);
  } catch {
    // Best-effort.
  }
}

/** Fire-and-forget: the endpoint tolerates no credentials at all (1-B6), so
 *  this costs nothing to attempt and nothing to lose if it fails. */
function retryPendingLogout() {
  void fetch(`${apiBaseUrl()}/api/v1/auth/logout`, {
    method: "POST",
    credentials: "include",
  })
    .then((response) => {
      if (response.ok) clearTombstone();
    })
    .catch(() => {
      // Leave the tombstone for the next launch to retry.
    });
}

let offlineCachePurge: (() => void) | undefined;
/** Phase 5 registers the offline query-cache purge here so session.ts does
 *  not need to depend on the offline cache module. */
export function registerOfflineCachePurge(purge: () => void) {
  offlineCachePurge = purge;
}

let refreshInFlight: Promise<RestoreResult> | undefined;

/**
 * Single-flight refresh: a background boot attempt, an `online` retry, and
 * a runtime 401 retry all resolve to the same in-flight request instead of
 * racing each other against `/auth/refresh`.
 */
export function attemptRefresh(): Promise<RestoreResult> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = performRefresh().finally(() => {
    refreshInFlight = undefined;
  });
  return refreshInFlight;
}

async function performRefresh(): Promise<RestoreResult> {
  const generation = sessionGeneration;
  const superseded = () => generation !== sessionGeneration;
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}/api/v1/auth/refresh`, {
      method: "POST",
      credentials: "include",
      signal: AbortSignal.timeout(RESTORE_TIMEOUT_MS),
    });
  } catch {
    if (superseded()) return "superseded";
    // Network error or timeout: the server's reachability is unknown, not
    // "no" — never clear the hint here (docs/architecture/frontend.md,
    // src/api/client/errors.ts).
    return "offline";
  }

  if (superseded()) return "superseded";
  if (response.status === 401 || response.status === 403) {
    clear();
    offlineCachePurge?.();
    return "unauthenticated";
  }
  if (!response.ok) return "offline";

  let body: { access_token?: string };
  try {
    body = (await response.json()) as { access_token?: string };
  } catch {
    if (superseded()) return "superseded";
    return "offline";
  }
  if (superseded()) return "superseded";
  if (!body.access_token) return "offline";

  accessToken = body.access_token;
  notify();
  return "restored";
}

async function restore(): Promise<RestoreResult> {
  if (hasTombstone()) {
    retryPendingLogout();
    return "unauthenticated";
  }
  if (navigator.onLine) return attemptRefresh();
  // Kick off the request but do not block first render on it; a later
  // resolution still runs (single-flight) and upgrades the session in
  // place via the listener notification in performRefresh().
  void attemptRefresh();
  return "offline";
}

function adopt({
  accessToken: token,
  userId,
}: {
  accessToken: string;
  userId: string;
}) {
  sessionGeneration += 1;
  accessToken = token;
  writeHint({ version: 1, userId, signedInAt: new Date().toISOString() });
  clearTombstone();
  notify();
}

function clear() {
  sessionGeneration += 1;
  accessToken = null;
  clearHint();
  notify();
}

/** Test-only: session.ts holds module-level singletons (the in-memory token,
 *  the single-flight refresh, subscribers) that must not leak between tests. */
export function resetSessionForTests() {
  sessionGeneration += 1;
  accessToken = null;
  refreshInFlight = undefined;
  offlineCachePurge = undefined;
  listeners.clear();
}

/** `LoginResponse.user` is typed as a loose dict server-side (shared with the
 *  /legacy/ Flutter client), so callers narrow `id` here rather than casting
 *  at every call site. */
export function userIdFromAuthResponse(user: {
  [key: string]: unknown;
}): string {
  const id = user.id;
  if (typeof id !== "string" || !id) {
    throw new Error("Auth response is missing a user id");
  }
  return id;
}

export const sessionStore = {
  getAccessToken: (): string | null => accessToken,
  readHint,
  adopt,
  restore,
  clear,
  subscribe: (listener: SessionListener) => {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  },
};

/**
 * Logs out through the API, tombstone first (docs/features/authentication.md,
 * "Logging out when the cookie cannot be deleted"). Every sign-out path in
 * the app must go through this so the tombstone and cache purge can never be
 * forgotten by a call site that just did `sessionStore.clear()`.
 */
export async function signOut(): Promise<void> {
  const token = accessToken;
  writeTombstone();
  clear();
  offlineCachePurge?.();
  try {
    const response = await fetch(`${apiBaseUrl()}/api/v1/auth/logout`, {
      method: "POST",
      credentials: "include",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (response.ok) clearTombstone();
  } catch {
    // Leave the tombstone; a later boot or `online` event retries it.
  }
}
