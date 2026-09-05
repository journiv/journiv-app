import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { sessionStore } from "../auth/session";
import { api } from "./api";
import { ApiError, isConflict, isNotFound, retryTransient } from "./errors";
import { resetAuthRefreshForTests } from "./config";

describe("API errors keep the status", () => {
  beforeEach(() => {
    sessionStorage.clear();
    resetAuthRefreshForTests();
    // Node's `Request` rejects a relative URL, which the browser accepts. The
    // base is a test detail; the status plumbing is what is under test.
    vi.stubEnv("VITE_API_BASE_URL", "http://journiv.test");
    sessionStore.write({
      version: 1,
      accessToken: "access",
      refreshToken: "refresh",
    });
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  const respondWith = (status: number, body: unknown) =>
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        body === undefined
          ? new Response(null, { status })
          : Response.json(body, { status }),
      ),
    );

  it("carries a 404 through as a definite not-found", async () => {
    respondWith(404, { detail: "Moment not found" });
    const caught = await api.moment("missing").catch((error) => error);

    expect(caught).toBeInstanceOf(ApiError);
    expect((caught as ApiError).status).toBe(404);
    // FastAPI's `detail` becomes the message, so a raw throw still reads well.
    expect((caught as ApiError).message).toBe("Moment not found");
    expect(isNotFound(caught)).toBe(true);
  });

  it("recognises a conflict", async () => {
    respondWith(409, { detail: "This entry changed somewhere else" });
    const caught = await api
      .updateMoment("moment-1", {})
      .catch((error) => error);

    expect(isConflict(caught)).toBe(true);
    expect(isNotFound(caught)).toBe(false);
  });

  it("keeps the body for anything that wants more than the status", async () => {
    respondWith(422, { detail: [{ loc: ["body", "title"], msg: "too long" }] });
    const caught = (await api
      .updateMoment("moment-1", {})
      .catch((error) => error)) as ApiError;

    expect(caught.status).toBe(422);
    expect(caught.body).toEqual({
      detail: [{ loc: ["body", "title"], msg: "too long" }],
    });
  });

  it("never calls a request that got no answer a not-found", async () => {
    // The whole reason the status is plumbed through: acting on absence must
    // require having actually asked. An offline phone has not asked.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );
    const caught = await api.moment("moment-1").catch((error) => error);

    expect(caught).toBeInstanceOf(ApiError);
    expect((caught as ApiError).status).toBeUndefined();
    expect(isNotFound(caught)).toBe(false);
    expect(isConflict(caught)).toBe(false);
  });
});

describe("retryTransient", () => {
  it("retries a failure that never got an answer, up to two attempts", () => {
    const offline = new ApiError("Failed to fetch");
    expect(retryTransient(0, offline)).toBe(true);
    expect(retryTransient(1, offline)).toBe(true);
    expect(retryTransient(2, offline)).toBe(false);
  });

  it("retries a 5xx", () => {
    expect(retryTransient(0, new ApiError("boom", { status: 500 }))).toBe(true);
    expect(retryTransient(0, new ApiError("down", { status: 503 }))).toBe(true);
  });

  it("does not retry a 4xx — it is the server's answer", () => {
    for (const status of [400, 401, 403, 404, 409, 422, 429]) {
      expect(retryTransient(0, new ApiError("no", { status }))).toBe(false);
    }
  });
});
