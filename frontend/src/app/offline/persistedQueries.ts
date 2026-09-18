import { queryKeys } from "../../api/query/keys";

/** A persisted query older than this is dropped rather than shown as if
 *  current. */
export const MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;

/** `shouldDehydrateQuery` is per-query and cannot enforce a global cap --
 *  offlineCache.ts's custom `serialize` is the only place that can. */
export const MAX_PERSISTED_QUERIES = 120;

/**
 * Allowlist, never denylist (docs/features/pwa.md): a query persists only
 * when its key is explicitly named here. Everything else -- `["export", …]`
 * (signed download URLs), `["import", …]`, `["admin", …]`,
 * `["integrations", …]` (provider connection state), `["prompts","library",…]`
 * (unbounded filter permutations), any filtered `["moments", {...}]` -- is
 * excluded by construction, not by an exception rule.
 */
const STATIC_ALLOWLIST = new Set(
  [
    queryKeys.me,
    queryKeys.userSettings,
    queryKeys.instanceConfig,
    queryKeys.journals,
    queryKeys.tags,
    queryKeys.people,
    queryKeys.moods,
    queryKeys.activities,
    queryKeys.goals,
    // The unfiltered timeline only -- the landing surface.
    queryKeys.moments({}),
  ].map((key) => JSON.stringify(key)),
);

function isAllowlistedKey(queryKey: readonly unknown[]): boolean {
  if (STATIC_ALLOWLIST.has(JSON.stringify(queryKey))) return true;
  // ["moment", id] -- entries the user actually opened. Exactly two
  // elements, both required: ["moment", id, "media"] (momentMedia) is
  // deliberately NOT allowlisted. Its only offline content would be a list
  // of already-expired signed URLs -- long-lived storage of a short-lived
  // capability, bought for nothing.
  return (
    queryKey.length === 2 &&
    queryKey[0] === "moment" &&
    typeof queryKey[1] === "string"
  );
}

/** Minimal shape this needs from a TanStack Query `Query` -- avoids pulling
 *  in its full generic signature for a three-field check. */
export type PersistableQuery = {
  queryKey: readonly unknown[];
  state: {
    status: string;
    data: unknown;
    dataUpdatedAt: number;
  };
};

export function shouldPersistQuery(query: PersistableQuery): boolean {
  if (query.state.status !== "success" || query.state.data === undefined)
    return false;
  if (!isAllowlistedKey(query.queryKey)) return false;
  if (Date.now() - query.state.dataUpdatedAt > MAX_AGE_MS) return false;
  return true;
}
