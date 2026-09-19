import { createAsyncStoragePersister } from "@tanstack/query-async-storage-persister";
import {
  dehydrate,
  hydrate,
  QueryClient,
  type DehydratedState,
} from "@tanstack/react-query";
import {
  persistQueryClientRestore,
  persistQueryClientSubscribe,
} from "@tanstack/react-query-persist-client";
import type { PersistedClient } from "@tanstack/query-persist-client-core";
import { offlineKv } from "./db";
import {
  MAX_AGE_MS,
  MAX_PERSISTED_QUERIES,
  shouldPersistQuery,
} from "./persistedQueries";

/** Bumped when a persisted shape changes. Never the build hash -- that would
 *  wipe the offline cache on every deploy, precisely when offline capability
 *  matters most. */
const CACHE_SCHEMA_VERSION = "1";

/** A slow or blocked IndexedDB must degrade to an empty cache, never hold
 *  the boot splash open. */
const HYDRATE_TIMEOUT_MS = 2000;

const READING_TOGGLE_KEY = "journiv.offline-reading-enabled.v1";

function storageKeyFor(userId: string) {
  return `journiv.query-cache.${userId}`;
}

/** `shouldDehydrateQuery` is per-query; this is the only place that can
 *  enforce the 120-query cap across the whole persisted client. Exported
 *  for direct testing. */
export function truncate(client: PersistedClient): PersistedClient {
  const queries = [...client.clientState.queries]
    .sort((a, b) => (b.state.dataUpdatedAt ?? 0) - (a.state.dataUpdatedAt ?? 0))
    .slice(0, MAX_PERSISTED_QUERIES);
  return {
    ...client,
    clientState: { ...client.clientState, queries, mutations: [] },
  };
}

function persisterFor(userId: string, canWrite: () => boolean = () => true) {
  return createAsyncStoragePersister({
    storage: {
      ...offlineKv,
      setItem: async (key, value) => {
        if (canWrite()) await offlineKv.setItem(key, value);
      },
    },
    key: storageKeyFor(userId),
    serialize: (client) => JSON.stringify(truncate(client)),
  });
}

export function isOfflineReadingEnabled(): boolean {
  try {
    return localStorage.getItem(READING_TOGGLE_KEY) !== "false";
  } catch {
    return true;
  }
}

let activeClient: QueryClient | undefined;
let activeUserId: string | undefined;
let activeUnsubscribe: (() => void) | undefined;
let cacheLifecycle = 0;

function startPersisting() {
  if (activeUnsubscribe || !activeClient || !activeUserId) return;
  const lifecycle = cacheLifecycle;
  const userId = activeUserId;
  activeUnsubscribe = persistQueryClientSubscribe({
    queryClient: activeClient,
    persister: persisterFor(
      userId,
      () =>
        lifecycle === cacheLifecycle &&
        activeUserId === userId &&
        isOfflineReadingEnabled(),
    ),
    buster: CACHE_SCHEMA_VERSION,
    dehydrateOptions: {
      shouldDehydrateQuery: shouldPersistQuery,
      shouldDehydrateMutation: () => false,
    },
  });
}

function stopPersisting() {
  activeUnsubscribe?.();
  activeUnsubscribe = undefined;
}

/** Restores cached queries before first render. Resolves to nothing (an
 *  empty cache) when there is no user, offline reading is switched off, the
 *  store is unavailable, or restoration is still running after
 *  HYDRATE_TIMEOUT_MS -- callers must never await longer than that. */
export async function hydrateOfflineCache(
  queryClient: QueryClient,
  userId: string | undefined,
): Promise<void> {
  if (!userId || !isOfflineReadingEnabled()) return;
  const lifecycle = ++cacheLifecycle;
  const stagingClient = new QueryClient();
  try {
    const restoredState = await Promise.race<DehydratedState | undefined>([
      persistQueryClientRestore({
        queryClient: stagingClient,
        persister: persisterFor(userId),
        maxAge: MAX_AGE_MS,
        buster: CACHE_SCHEMA_VERSION,
      }).then(() =>
        dehydrate(stagingClient, {
          shouldDehydrateQuery: shouldPersistQuery,
          shouldDehydrateMutation: () => false,
        }),
      ),
      new Promise<undefined>((resolve) =>
        setTimeout(resolve, HYDRATE_TIMEOUT_MS),
      ),
    ]);
    if (
      restoredState &&
      lifecycle === cacheLifecycle &&
      isOfflineReadingEnabled()
    ) {
      hydrate(queryClient, restoredState);
    }
  } catch {
    // Degrade to an empty cache.
  }
}

/**
 * Treats the bounded offline snapshot as stale once a live session exists.
 * Hydration preserves `dataUpdatedAt`, so without this a recent pre-mutation
 * snapshot can sit inside the normal query freshness window and suppress the
 * online GET after a reload. Offline-restricted boots deliberately do not call
 * this: their cached data must remain readable without a reachable server.
 */
export function revalidatePersistedQueries(
  queryClient: QueryClient,
): Promise<void> {
  return queryClient.invalidateQueries({
    predicate: (query) => shouldPersistQuery(query),
  });
}

/** Starts ongoing persistence after render. Keep calling this exactly once
 *  per boot -- the offline-reading toggle re-enters via
 *  setOfflineReadingEnabled(), not a second call to this. */
export function subscribeOfflineCache(
  queryClient: QueryClient,
  userId: string | undefined,
): () => void {
  // Always replace the existing subscription. Boot subscribes with the hinted
  // user id, and adopt() subscribes again after sign-in; keeping the first
  // subscription would write the new user's queries under the previous user's
  // storage key. Bumping the lifecycle also invalidates any in-flight restore.
  stopPersisting();
  cacheLifecycle += 1;
  activeClient = queryClient;
  activeUserId = userId;
  if (userId && isOfflineReadingEnabled()) startPersisting();
  return () => {
    if (activeClient === queryClient && activeUserId === userId) {
      teardownOfflineCache();
    }
  };
}

/** Stops persistence and forgets the session identity. Called on sign-out and
 *  on a definite authentication rejection before cached data is purged. */
export function teardownOfflineCache() {
  stopPersisting();
  cacheLifecycle += 1;
  activeClient = undefined;
  activeUserId = undefined;
}

export async function purgeOfflineCache(
  userId: string | undefined,
): Promise<void> {
  // Before removeClient(), always: a subscription still running would flush
  // the in-memory query cache straight back into the slot we just deleted,
  // silently undoing the purge a sign-out or a definite 401 just performed.
  stopPersisting();
  if (!userId) return;
  await persisterFor(userId).removeClient();
}

/** Settings → Install & offline's "Offline reading" switch. Ships on by
 *  default (an owner decision, not an implementation default) -- this is
 *  disclosure plus an opt-out, not an opt-in privacy control. Turning it off
 *  purges the cache immediately and stops persisting. */
export async function setOfflineReadingEnabled(
  enabled: boolean,
): Promise<void> {
  const previous = isOfflineReadingEnabled();
  localStorage.setItem(READING_TOGGLE_KEY, String(enabled));
  cacheLifecycle += 1;
  if (enabled) {
    startPersisting();
    return;
  }
  stopPersisting();
  try {
    await purgeOfflineCache(activeUserId);
  } catch (cause) {
    try {
      localStorage.setItem(READING_TOGGLE_KEY, String(previous));
    } catch {
      // Preserve the original storage failure.
    }
    if (previous) startPersisting();
    throw cause;
  }
}

export function resetOfflineCacheForTests() {
  activeUnsubscribe?.();
  activeClient = undefined;
  activeUserId = undefined;
  activeUnsubscribe = undefined;
  cacheLifecycle = 0;
}
