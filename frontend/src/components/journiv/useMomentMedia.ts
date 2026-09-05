import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import type { MomentMediaResponse } from "../../api/generated/types.gen";
import { momentMediaQuery } from "../../api/query/options";

/**
 * Full media for one Moment, with signed-URL expiry recovery.
 *
 * Expiry handling is explicit and does not rely on the query's staleTime:
 * `refetch()` always goes to the network, so a document that has been open past
 * the signature lifetime re-signs rather than rendering dead URLs.
 *
 * Shared by the Reader gallery and the Editor's attached-media surface
 * (docs/features/reader.md, docs/features/editor.md). It knows nothing about
 * either surface — only the moment-media endpoint and how its URLs expire.
 */
export function useMomentMedia(momentId: string, enabled: boolean) {
  const query = useQuery({ ...momentMediaQuery(momentId), enabled });
  const { data, isFetching, refetch } = query;

  // One re-sign attempt per expired state. A re-sign response can itself carry
  // expired URLs (for example, if a proxy serves an old response), so keying
  // this to dataUpdatedAt would retry forever as each response gets a new time.
  const reSignAttempted = useRef(false);
  const reSignMomentId = useRef<string | null>(null);
  useEffect(() => {
    // Hook consumers can switch between Moments without remounting. Reset
    // before checking expiry so each Moment gets one automatic re-sign attempt.
    if (reSignMomentId.current !== momentId) {
      reSignMomentId.current = momentId;
      reSignAttempted.current = false;
    }
    if (!data?.length || isFetching) return;
    const expired = data.some(
      (item) =>
        typeof item.signed_url_expires_at === "number" &&
        item.signed_url_expires_at * 1000 <= Date.now(),
    );
    if (!expired) {
      reSignAttempted.current = false;
      return;
    }
    if (reSignAttempted.current) return;
    reSignAttempted.current = true;
    void refetch();
  }, [data, isFetching, momentId, refetch]);

  // A URL can also expire between the response and the image load. The first
  // failure per item forces a fresh signature; a second is treated as broken.
  const retried = useRef(new Set<string>());
  const [broken, setBroken] = useState<Record<string, true>>({});
  const reportLoadFailure = useCallback(
    (id: string) => {
      if (retried.current.has(id)) {
        setBroken((current) => ({ ...current, [id]: true }));
        return;
      }
      retried.current.add(id);
      void refetch();
    },
    [refetch],
  );

  const retryAll = useCallback(() => {
    retried.current.clear();
    setBroken({});
    reSignAttempted.current = false;
    void refetch();
  }, [refetch]);

  const byId = new Map<string, MomentMediaResponse>(
    (data ?? []).map((item) => [item.id, item]),
  );

  return {
    items: data,
    byId,
    isLoading: query.isLoading,
    isError: query.isError,
    isFetching,
    broken,
    reportLoadFailure,
    retryAll,
  };
}

export type MomentMediaState = ReturnType<typeof useMomentMedia>;
