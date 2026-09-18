import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { resetSessionForTests, sessionStore } from "../../api/auth/session";
import {
  getBootMode,
  initBootMode,
  resetBootModeForTests,
} from "./offlineMode";

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
    sessionStore.adopt({ accessToken: "a", userId: "user-1" });
    initBootMode("offline");
    expect(getBootMode()).toBe("offline-restricted");
  });

  it("offline with no hint -> unauthenticated (LoginPage fails closed honestly)", () => {
    initBootMode("offline");
    expect(getBootMode()).toBe("unauthenticated");
  });

  it("a later restore success upgrades offline-restricted to normal in place", () => {
    sessionStore.adopt({ accessToken: "a", userId: "user-1" });
    initBootMode("offline");
    expect(getBootMode()).toBe("offline-restricted");

    sessionStore.adopt({ accessToken: "b", userId: "user-1" });
    expect(getBootMode()).toBe("normal");
  });

  it("a later definite 401 moves offline-restricted to unauthenticated", () => {
    sessionStore.adopt({ accessToken: "a", userId: "user-1" });
    initBootMode("offline");
    expect(getBootMode()).toBe("offline-restricted");

    sessionStore.clear();
    expect(getBootMode()).toBe("unauthenticated");
  });
});
