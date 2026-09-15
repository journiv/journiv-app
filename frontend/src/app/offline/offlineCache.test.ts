import { QueryClient } from "@tanstack/react-query";
import type { PersistedClient } from "@tanstack/query-persist-client-core";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { queryKeys } from "../../api/query/keys";
import { closeOfflineDb, offlineKv } from "./db";
import {
  hydrateOfflineCache,
  isOfflineReadingEnabled,
  purgeOfflineCache,
  resetOfflineCacheForTests,
  setOfflineReadingEnabled,
  subscribeOfflineCache,
  teardownOfflineCache,
  truncate,
} from "./offlineCache";
import { MAX_PERSISTED_QUERIES } from "./persistedQueries";

const USER_ID = "user-1";
const STORAGE_KEY = `journiv.query-cache.${USER_ID}`;

async function deleteOfflineDb() {
  await closeOfflineDb();
  await new Promise<void>((resolve) => {
    const request = indexedDB.deleteDatabase("journiv-offline");
    request.onsuccess = () => resolve();
    request.onerror = () => resolve();
    request.onblocked = () => resolve();
  });
}

function dehydratedQuery(key: readonly unknown[], dataUpdatedAt: number) {
  return {
    queryHash: JSON.stringify(key),
    queryKey: key,
    state: {
      data: { ok: true },
      dataUpdateCount: 1,
      dataUpdatedAt,
      error: null,
      errorUpdateCount: 0,
      errorUpdatedAt: 0,
      fetchFailureCount: 0,
      fetchFailureReason: null,
      fetchMeta: null,
      isInvalidated: false,
      status: "success" as const,
      fetchStatus: "idle" as const,
    },
  };
}

describe("offlineCache", () => {
  beforeEach(async () => {
    localStorage.clear();
    resetOfflineCacheForTests();
    await deleteOfflineDb();
  });

  afterEach(async () => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    resetOfflineCacheForTests();
    await deleteOfflineDb();
  });

  describe("truncate", () => {
    it("sorts newest-first and caps at MAX_PERSISTED_QUERIES", () => {
      const queries = Array.from(
        { length: MAX_PERSISTED_QUERIES + 10 },
        (_, i) => dehydratedQuery(["moment", `m${i}`], i),
      );
      const client: PersistedClient = {
        timestamp: Date.now(),
        buster: "1",
        clientState: { queries, mutations: [] },
      };

      const result = truncate(client);

      expect(result.clientState.queries).toHaveLength(MAX_PERSISTED_QUERIES);
      // Newest (highest dataUpdatedAt) survive.
      expect(result.clientState.queries[0]?.state.dataUpdatedAt).toBe(
        queries.length - 1,
      );
      expect(
        result.clientState.queries[MAX_PERSISTED_QUERIES - 1]?.state
          .dataUpdatedAt,
      ).toBe(queries.length - MAX_PERSISTED_QUERIES);
      expect(result.clientState.mutations).toEqual([]);
    });
  });

  describe("isOfflineReadingEnabled", () => {
    it("defaults to on", () => {
      expect(isOfflineReadingEnabled()).toBe(true);
    });

    it("is off only after an explicit opt-out", async () => {
      await setOfflineReadingEnabled(false);
      expect(isOfflineReadingEnabled()).toBe(false);
      await setOfflineReadingEnabled(true);
      expect(isOfflineReadingEnabled()).toBe(true);
    });
  });

  describe("hydrateOfflineCache", () => {
    it("resolves with no userId and touches nothing", async () => {
      await expect(
        hydrateOfflineCache(new QueryClient(), undefined),
      ).resolves.toBeUndefined();
    });

    it("resolves without restoring when offline reading is off", async () => {
      await setOfflineReadingEnabled(false);
      await offlineKv.setItem(
        STORAGE_KEY,
        JSON.stringify({
          timestamp: Date.now(),
          buster: "1",
          clientState: {
            queries: [dehydratedQuery(queryKeys.journals, Date.now())],
            mutations: [],
          },
        } satisfies PersistedClient),
      );

      const queryClient = new QueryClient();
      await hydrateOfflineCache(queryClient, USER_ID);

      expect(queryClient.getQueryData(queryKeys.journals)).toBeUndefined();
    });

    it("restores previously persisted data for that user", async () => {
      await offlineKv.setItem(
        STORAGE_KEY,
        JSON.stringify({
          timestamp: Date.now(),
          buster: "1",
          clientState: {
            queries: [
              dehydratedQuery(queryKeys.journals, Date.now()),
              dehydratedQuery(["export", "jobs"], Date.now()),
            ],
            mutations: [],
          },
        } satisfies PersistedClient),
      );

      const queryClient = new QueryClient();
      await hydrateOfflineCache(queryClient, USER_ID);

      expect(queryClient.getQueryData(queryKeys.journals)).toEqual({
        ok: true,
      });
      expect(queryClient.getQueryData(["export", "jobs"])).toBeUndefined();
    });

    it("does not mutate the live client when storage resolves after the timeout", async () => {
      vi.useFakeTimers();
      let resolveRead: (value: string | null) => void = () => {};
      vi.spyOn(offlineKv, "getItem").mockReturnValue(
        new Promise((resolve) => {
          resolveRead = resolve;
        }),
      );
      const queryClient = new QueryClient();
      const hydration = hydrateOfflineCache(queryClient, USER_ID);

      await vi.advanceTimersByTimeAsync(2000);
      await hydration;
      resolveRead(
        JSON.stringify({
          timestamp: Date.now(),
          buster: "1",
          clientState: {
            queries: [dehydratedQuery(queryKeys.journals, Date.now())],
            mutations: [],
          },
        } satisfies PersistedClient),
      );
      await Promise.resolve();
      await Promise.resolve();

      expect(queryClient.getQueryData(queryKeys.journals)).toBeUndefined();
    });
  });

  describe("purgeOfflineCache", () => {
    it("removes the stored blob for that user", async () => {
      await offlineKv.setItem(STORAGE_KEY, "{}");
      await purgeOfflineCache(USER_ID);
      expect(await offlineKv.getItem(STORAGE_KEY)).toBeNull();
    });

    it("is a no-op with no userId", async () => {
      await expect(purgeOfflineCache(undefined)).resolves.toBeUndefined();
    });
  });

  describe("setOfflineReadingEnabled(false)", () => {
    it("purges the active user's cache", async () => {
      await offlineKv.setItem(STORAGE_KEY, "{}");
      subscribeOfflineCache(new QueryClient(), USER_ID);

      await setOfflineReadingEnabled(false);

      expect(await offlineKv.getItem(STORAGE_KEY)).toBeNull();
    });
  });

  describe("switching accounts in one page load", () => {
    it("persists the second user's queries under the second user's key", async () => {
      // Signing out does not reload the page: AppSidebar calls signOut() and
      // the session subscriber navigates to /login in-SPA. Boot already
      // subscribed with the hint's userId, then adopt() subscribes again for
      // whoever signs in next. Both subscriptions are for the same
      // QueryClient, so the second must replace the first -- otherwise the
      // new user's entries are written into the previous user's slot, where
      // that user's next boot would hydrate them.
      const queryClient = new QueryClient();
      subscribeOfflineCache(queryClient, "user-A");
      subscribeOfflineCache(queryClient, "user-B");

      queryClient.setQueryData(queryKeys.journals, [{ id: "b-only" }]);

      await vi.waitFor(
        async () => {
          const raw = await offlineKv.getItem("journiv.query-cache.user-B");
          expect(raw).toContain("b-only");
        },
        { timeout: 3000, interval: 100 },
      );

      const leaked = await offlineKv.getItem("journiv.query-cache.user-A");
      expect(leaked ?? "").not.toContain("b-only");
    }, 5000);
  });

  describe("purge while a subscription is live", () => {
    it("does not let the running subscription write the cache straight back", async () => {
      const queryClient = new QueryClient();
      subscribeOfflineCache(queryClient, USER_ID);
      queryClient.setQueryData(queryKeys.journals, [{ id: "j1" }]);
      await vi.waitFor(
        async () => {
          expect(await offlineKv.getItem(STORAGE_KEY)).toContain("j1");
        },
        { timeout: 3000, interval: 100 },
      );

      // What signOut()/a definite 401 do via registerOfflineCachePurge.
      await purgeOfflineCache(USER_ID);
      // AppShell clears the query cache on the same sign-out. That is a cache
      // event, so a subscription still running would flush a fresh snapshot
      // into the slot the purge just deleted -- recreating it right after the
      // user asked for it to go.
      queryClient.clear();
      // Long enough for a still-live throttled persister to flush again.
      await new Promise((resolve) => setTimeout(resolve, 1500));

      expect(await offlineKv.getItem(STORAGE_KEY)).toBeNull();
    }, 8000);
  });

  describe("subscribe -> restore round trip", () => {
    it("a query subscribeOfflineCache saves is readable by hydrateOfflineCache in a fresh client", async () => {
      const writer = new QueryClient();
      subscribeOfflineCache(writer, USER_ID);
      writer.setQueryData(queryKeys.journals, [{ id: "j1" }]);

      // The persister throttles writes (default 1s) and saves an initial
      // (empty) snapshot immediately on subscribe, before the throttled
      // save carrying the new data lands -- this is the one test allowed
      // to wait on it, polling for the actual content rather than merely
      // "a value exists", to catch exactly what a fabricated
      // PersistedClient blob (the other tests above) cannot: a `buster`
      // mismatch between the subscribe path and the restore path, which
      // would silently discard every real write as "busted".
      await vi.waitFor(
        async () => {
          const raw = await offlineKv.getItem(STORAGE_KEY);
          expect(raw).toContain("j1");
        },
        { timeout: 3000, interval: 100 },
      );

      const reader = new QueryClient();
      await hydrateOfflineCache(reader, USER_ID);

      expect(reader.getQueryData(queryKeys.journals)).toEqual([{ id: "j1" }]);
    }, 5000);

    it("rebinds persistence when the signed-in user changes", async () => {
      const writer = new QueryClient();
      subscribeOfflineCache(writer, USER_ID);
      subscribeOfflineCache(writer, "user-2");
      writer.setQueryData(queryKeys.journals, [{ id: "user-2-journal" }]);

      await vi.waitFor(
        async () => {
          const raw = await offlineKv.getItem("journiv.query-cache.user-2");
          expect(raw).toContain("user-2-journal");
        },
        { timeout: 3000, interval: 100 },
      );
    }, 5000);

    it("never persists paused mutations", async () => {
      const writer = new QueryClient();
      subscribeOfflineCache(writer, USER_ID);
      writer.getMutationCache().build(
        writer,
        { mutationKey: ["save-entry"] },
        {
          context: undefined,
          data: undefined,
          error: null,
          failureCount: 0,
          failureReason: null,
          isPaused: true,
          status: "pending",
          submittedAt: Date.now(),
          variables: { privateText: "do not persist" },
        },
      );

      await vi.waitFor(
        async () => {
          const raw = await offlineKv.getItem(STORAGE_KEY);
          expect(raw).not.toBeNull();
          const persisted = JSON.parse(raw ?? "null") as PersistedClient;
          expect(persisted.clientState.mutations).toEqual([]);
        },
        { timeout: 3000, interval: 100 },
      );
    }, 5000);

    it("cancels throttled persistence during session teardown", async () => {
      const writer = new QueryClient();
      subscribeOfflineCache(writer, USER_ID);
      writer.setQueryData(queryKeys.journals, [{ id: "before-sign-out" }]);
      await vi.waitFor(
        async () => {
          expect(await offlineKv.getItem(STORAGE_KEY)).toContain(
            "before-sign-out",
          );
        },
        { timeout: 2500, interval: 100 },
      );
      writer.setQueryData(queryKeys.journals, [{ id: "pending-write" }]);
      teardownOfflineCache();
      await purgeOfflineCache(USER_ID);

      await new Promise((resolve) => setTimeout(resolve, 1100));
      expect(await offlineKv.getItem(STORAGE_KEY)).toBeNull();
    }, 5000);
  });
});
