import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { sessionStore } from "../auth/session";
import {
  apiBaseUrl,
  authenticatedFetch,
  resetAuthRefreshForTests,
} from "./config";

describe("credentialed API base URL", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("accepts HTTPS and loopback HTTP URLs", () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://journiv.example.com");
    expect(apiBaseUrl()).toBe("https://journiv.example.com");

    vi.stubEnv("VITE_API_BASE_URL", "http://127.0.0.1:8000");
    expect(apiBaseUrl()).toBe("http://127.0.0.1:8000");

    vi.stubEnv("VITE_API_BASE_URL", "http://127.0.0.2:8000");
    expect(apiBaseUrl()).toBe("http://127.0.0.2:8000");
  });

  it("rejects cross-origin LAN HTTP before credentials are configured", () => {
    vi.stubEnv("VITE_API_BASE_URL", "http://192.168.1.10:8000");

    expect(() => apiBaseUrl()).toThrow(
      "VITE_API_BASE_URL must use HTTPS for credentialed cross-origin requests",
    );
  });
});

describe("authenticatedFetch", () => {
  beforeEach(() => {
    sessionStorage.clear();
    resetAuthRefreshForTests();
    sessionStore.write({
      version: 1,
      accessToken: "expired-access",
    });
  });

  afterEach(() => vi.restoreAllMocks());

  it("uses one refresh request for concurrent 401 responses and retries both", async () => {
    let refreshCalls = 0;
    const fetchMock = vi.fn(
      async (request: RequestInfo | URL, init?: RequestInit) => {
        const candidate =
          request instanceof Request
            ? request
            : new Request(new URL(request.toString(), "http://journiv.test"));
        if (candidate.url.endsWith("/api/v1/auth/refresh")) {
          refreshCalls += 1;
          expect(init?.credentials).toBe("include");
          expect(init?.body).toBeUndefined();
          await Promise.resolve();
          return Response.json({ access_token: "renewed-access" });
        }
        const headers = new Headers(init?.headers ?? candidate.headers);
        return headers.get("Authorization") === "Bearer renewed-access"
          ? Response.json({ ok: true })
          : new Response(null, { status: 401 });
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    const [first, second] = await Promise.all([
      authenticatedFetch(
        new Request("http://journiv.test/api/v1/moments", {
          headers: { Authorization: "Bearer expired-access" },
        }),
      ),
      authenticatedFetch(
        new Request("http://journiv.test/api/v1/journals", {
          headers: { Authorization: "Bearer expired-access" },
        }),
      ),
    ]);

    expect([first.status, second.status]).toEqual([200, 200]);
    expect(refreshCalls).toBe(1);
    expect(sessionStore.read()?.accessToken).toBe("renewed-access");
  });

  it("clears the session when refresh is rejected", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (request: RequestInfo | URL) => {
        const url =
          request instanceof Request ? request.url : request.toString();
        return new Response(null, {
          status: url.endsWith("/api/v1/auth/refresh") ? 401 : 401,
        });
      }),
    );

    const response = await authenticatedFetch(
      new Request("http://journiv.test/api/v1/moments"),
    );

    expect(response.status).toBe(401);
    expect(sessionStore.read()).toBeNull();
  });
});
