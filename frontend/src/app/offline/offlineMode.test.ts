import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { resetSessionForTests, sessionStore } from "../../api/auth/session";
import {
  getBootMode,
  initBootMode,
  resetBootModeForTests,
} from "./offlineMode";

/**
 * The real offline-restricted precondition: a *previous* page load left the
 * hint in localStorage and this one has no access token yet. `adopt()` is not
 * a substitute -- it also sets the in-memory token, which is the one state
 * that proves the session is live and rules offline-restricted out.
 */
function hintFromAPreviousSession(userId = "user-1") {
  localStorage.setItem(
    "journiv.session-hint.v1",
    JSON.stringify({
      version: 1,
      userId,
      signedInAt: new Date().toISOString(),
    }),
  );
}

describe("offlineMode", () => {
  beforeEach(() => {
    localStorage.clear();
    resetSessionForTests();
    resetBootModeForTests();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("restored -> normal", () => {
    initBootMode("restored");
    expect(getBootMode()).toBe("normal");
  });

  it("unauthenticated -> unauthenticated", () => {
    initBootMode("unauthenticated");
    expect(getBootMode()).toBe("unauthenticated");
  });

  it("offline with a hint -> offline-restricted", () => {
    // A prior sign-in wrote the hint; a network failure while offline never
    // clears it (docs/features/pwa.md).
    hintFromAPreviousSession();
    initBootMode("offline");
    expect(getBootMode()).toBe("offline-restricted");
  });

  it("offline with no hint -> unauthenticated (LoginPage fails closed honestly)", () => {
    initBootMode("offline");
    expect(getBootMode()).toBe("unauthenticated");
  });

  it("a later restore success upgrades offline-restricted to normal in place", () => {
    hintFromAPreviousSession();
    initBootMode("offline");
    expect(getBootMode()).toBe("offline-restricted");

    sessionStore.adopt({ accessToken: "b", userId: "user-1" });
    expect(getBootMode()).toBe("normal");
  });

  it("a refresh that landed before initBootMode wins over a stale 'offline'", () => {
    // The LAN case the owner called out: navigator.onLine is false, restore()
    // returns "offline" provisionally and leaves the refresh running, and the
    // server answers while main.tsx is still awaiting hydrateOfflineCache().
    // The token is set before anything has subscribed, so the notify() that
    // would have corrected the mode is already gone -- trusting the stale
    // result would strand an authenticated session behind OfflineBar.
    sessionStore.adopt({ accessToken: "live", userId: "user-1" });
    initBootMode("offline");
    expect(getBootMode()).toBe("normal");
  });

  it("a later definite 401 moves offline-restricted to unauthenticated", () => {
    hintFromAPreviousSession();
    initBootMode("offline");
    expect(getBootMode()).toBe("offline-restricted");

    sessionStore.clear();
    expect(getBootMode()).toBe("unauthenticated");
  });
});
