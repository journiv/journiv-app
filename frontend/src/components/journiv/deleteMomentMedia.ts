import type { QueryClient } from "@tanstack/react-query";
import { api } from "../../api/client/api";
import { isNotFound } from "../../api/client/errors";
import { queryKeys } from "../../api/query/keys";

export async function deleteMomentMedia(
  queryClient: QueryClient,
  momentId: string,
  mediaId: string,
) {
  try {
    await api.deleteMedia(mediaId);
  } catch (caught) {
    // A 404 means another surface already deleted the item. A retry can never
    // succeed, so refresh the caches as if this delete went through.
    if (!isNotFound(caught)) throw caught;
  }
  // The caller reports success only once the Moment and its media list show
  // the clip gone, so a confirmation never closes on a surface that still
  // offers it. A failed refetch fails the delete; the retry meets the 404
  // above and refetches again. The lists, calendars and media libraries only
  // carry per-moment counts and thumbnails; nothing waits on them.
  void queryClient.invalidateQueries({ queryKey: queryKeys.allMoments });
  void queryClient.invalidateQueries({
    queryKey: queryKeys.allMomentCalendars,
  });
  void queryClient.invalidateQueries({ queryKey: queryKeys.allMediaLibraries });
  await Promise.all([
    queryClient.invalidateQueries(
      { queryKey: queryKeys.moment(momentId), exact: true },
      { throwOnError: true },
    ),
    queryClient.invalidateQueries(
      { queryKey: queryKeys.momentMedia(momentId) },
      { throwOnError: true },
    ),
  ]);
}
