import { useQuery } from "@tanstack/react-query";
import { api } from "../../../api/client/api";
import { queryKeys } from "../../../api/query/keys";

/**
 * People Immich's face index matches to this moment's Immich media and that are
 * sync-enabled but not yet on the moment. `POST /moments/{id}/people/
 * suggestions/immich` is a read — it never writes — so it is a query.
 *
 * `enabled` is the caller's gate: only fire when the instance has Immich AND
 * the moment actually holds Immich-origin media, so a non-Immich entry never
 * makes the (Immich-round-tripping) face call. `retry: false` because a 400
 * (not connected) is an answer, not a blip, and the strip just stays hidden.
 */
export function useImmichPeopleSuggestions(
  momentId: string | undefined,
  enabled: boolean,
) {
  return useQuery({
    queryKey: momentId
      ? queryKeys.immichPeopleSuggestions(momentId)
      : ["moment", "__none__", "immich-people-suggestions"],
    queryFn: () => api.immichPeopleSuggestions(momentId as string),
    enabled: enabled && Boolean(momentId),
    staleTime: 60_000,
    retry: false,
  });
}
