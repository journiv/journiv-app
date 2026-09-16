import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  attemptRefresh,
  resetSessionForTests,
  sessionStore,
  signOut,
} from "./session";

function stubOnline(online: boolean) {
  vi.stubGlobal("navigator", { ...navigator, onLine: online });
}

describe("sessionStore", () => {
  beforeEach(() => {
    localStorage.clear();
    resetSessionForTests();
    vi.stubEnv("VITE_API_BASE_URL", "https://journiv.test");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("adopt() sets the in-memory token and a credential-free hint", () => {
    sessionStore.adopt({ accessToken: "access-1", userId: "user-1" });
    expect(sessionStore.getAccessToken()).toBe("access-1");
    const hint = sessionStore.readHint();
    expect(hint?.userId).toBe("user-1");
    expect(hint?.version).toBe(1);
    // No credential anywhere in storage.
    expect(localStorage.getItem("journiv.session-hint.v1")).not.toContain(
      "access-1",
    );
  });

  it("never writes a token to localStorage or sessionStorage", () => {
    sessionStore.adopt({ accessToken: "super-secret-token", userId: "u1" });
    for (let i = 0; i < localStorage.length; i += 1) {
      const key = localStorage.key(i);
      expect(localStorage.getItem(key ?? "")).not.toContain(
        "super-secret-token",
      );
    }
    for (let i = 0; i < sessionStorage.length; i += 1) {
      const key = sessionStorage.key(i);
      expect(sessionStorage.getItem(key ?? "")).not.toContain(
        "super-secret-token",
      );
    }
  });

  it("clear() drops the token and the hint", () => {
    sessionStore.adopt({ accessToken: "access-1", userId: "user-1" });
    sessionStore.clear();
    expect(sessionStore.getAccessToken()).toBeNull();
    expect(sessionStore.readHint()).toBeNull();
  });

  it("restore() succeeds against a reachable server", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ access_token: "new-access" })),
    );
    stubOnline(true);

    const result = await sessionStore.restore();

    expect(result).toBe("restored");
    expect(sessionStore.getAccessToken()).toBe("new-access");
  });

  it("restore() clears the hint on a definite 401", async () => {
    sessionStore.adopt({ accessToken: "stale", userId: "user-1" });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(null, { status: 401 })),
    );
    stubOnline(true);

    const result = await sessionStore.restore();

    expect(result).toBe("unauthenticated");
    expect(sessionStore.getAccessToken()).toBeNull();
    expect(sessionStore.readHint()).toBeNull();
  });

  it("restore() preserves the hint and reports offline on a network failure", async () => {
    sessionStore.adopt({ accessToken: "stale", userId: "user-1" });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );
    stubOnline(true);

    const result = await sessionStore.restore();

    expect(result).toBe("offline");
    expect(sessionStore.readHint()).not.toBeNull();
  });

  it("restore() with navigator.onLine false resolves offline immediately but still issues the request, upgrading in place on success", async () => {
    sessionStore.adopt({ accessToken: "stale", userId: "user-1" });
    let resolveFetch: (value: Response) => void = () => {};
    const fetchMock = vi.fn(
      () =>
        new Promise<Response>((resolve) => {
          resolveFetch = resolve;
        }),
    );
    vi.stubGlobal("fetch", fetchMock);
    stubOnline(false);

    const resultPromise = sessionStore.restore();
    // Resolves without waiting for the network at all.
    expect(
      await Promise.race([resultPromise, Promise.resolve("pending")]),
    ).toBe("offline");
    expect(fetchMock).toHaveBeenCalledTimes(1);

    resolveFetch(Response.json({ access_token: "renewed" }));
    await vi.waitFor(() => {
      expect(sessionStore.getAccessToken()).toBe("renewed");
    });
  });

  it("restore() returns unauthenticated with no network request while the logout tombstone exists", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL) =>
      Response.json({}),
    );
    vi.stubGlobal("fetch", fetchMock);
    localStorage.setItem("journiv.logout-pending.v1", "1");

    const result = await sessionStore.restore();

    expect(result).toBe("unauthenticated");
    // The one fetch that does happen is the best-effort logout retry, not a
    // refresh attempt.
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toContain("/auth/logout");
  });

  it("attemptRefresh() is single-flight: concurrent callers issue one request", async () => {
    let calls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        calls += 1;
        await Promise.resolve();
        return Response.json({ access_token: "shared-refresh" });
      }),
    );

    const [a, b] = await Promise.all([attemptRefresh(), attemptRefresh()]);

    expect(calls).toBe(1);
    expect(a).toBe("restored");
    expect(b).toBe("restored");
  });

  it("does not restore a session when logout completes during refresh", async () => {
    sessionStore.adopt({ accessToken: "old-access", userId: "old-user" });
    let resolveRefresh: (response: Response) => void = () => {};
    vi.stubGlobal(
      "fetch",
      vi.fn((request: RequestInfo | URL) => {
        const url = request.toString();
        if (url.endsWith("/api/v1/auth/refresh")) {
          return new Promise<Response>((resolve) => {
            resolveRefresh = resolve;
          });
        }
        return Promise.resolve(Response.json({ message: "ok" }));
      }),
    );

    const refresh = attemptRefresh();
    await signOut();
    resolveRefresh(Response.json({ access_token: "stale-access" }));

    expect(await refresh).toBe("superseded");
    expect(sessionStore.getAccessToken()).toBeNull();
  });

  it("does not clear a newly adopted account when an older refresh is rejected", async () => {
    sessionStore.adopt({ accessToken: "old-access", userId: "old-user" });
    let resolveRefresh: (response: Response) => void = () => {};
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            resolveRefresh = resolve;
          }),
      ),
    );

    const refresh = attemptRefresh();
    sessionStore.adopt({ accessToken: "new-access", userId: "new-user" });
    resolveRefresh(new Response(null, { status: 401 }));

    expect(await refresh).toBe("superseded");
    expect(sessionStore.getAccessToken()).toBe("new-access");
    expect(sessionStore.readHint()?.userId).toBe("new-user");
  });

  it("signOut() writes the tombstone before the network call and removes it on success", async () => {
    sessionStore.adopt({ accessToken: "access-1", userId: "user-1" });
    let tombstonePresentDuringCall = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        tombstonePresentDuringCall =
          localStorage.getItem("journiv.logout-pending.v1") !== null;
        return Response.json({ message: "ok" });
      }),
    );

    await signOut();

    expect(tombstonePresentDuringCall).toBe(true);
    expect(localStorage.getItem("journiv.logout-pending.v1")).toBeNull();
    expect(sessionStore.getAccessToken()).toBeNull();
  });

  it("signOut() leaves the tombstone in place when the network call fails", async () => {
    sessionStore.adopt({ accessToken: "access-1", userId: "user-1" });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );

    await signOut();

    expect(localStorage.getItem("journiv.logout-pending.v1")).not.toBeNull();
    expect(sessionStore.getAccessToken()).toBeNull();
  });

  it("adopt() removes a tombstone left by a prior failed sign-out", async () => {
    localStorage.setItem("journiv.logout-pending.v1", "1");
    sessionStore.adopt({ accessToken: "access-1", userId: "user-1" });
    expect(localStorage.getItem("journiv.logout-pending.v1")).toBeNull();
  });
});
