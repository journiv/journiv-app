import { useEffect } from "react";
import type { MomentMediaState } from "../../components/journiv/useMomentMedia";
import { recordingRepository } from "./recordingRepository";

/**
 * Keeps a dictation anchor from outliving the recording it points at.
 *
 * The anchor (where in the entry a recording was made) is device-local and survives the
 * staged audio being cleaned up after upload; it must not survive the *server
 * media*. Nothing in the app deletes a dictation recording directly — a
 * recording leaves a Moment when its media is placed inline, removed from the
 * prose and the save orphan-collects it, or when it is deleted from another
 * device — so this works from the media list the caller already holds.
 *
 * It runs wherever that list is in hand (the editor, and the reader the writer
 * lands in after a save). An anchor whose media id is in the list is kept in
 * whatever status the item has; `pending` and `processing` items are in the
 * list. Only a *settled* list is trusted: never while loading, refetching, or
 * after an error. A Moment the server says has no media never loads a list at
 * all, so `mediaCount === 0` stands in for an empty one — that is the case of
 * the last recording having just been removed.
 *
 * Best effort and silent: with IndexedDB unavailable (private browsing, blocked
 * site data) there is nothing to prune and nothing to say.
 */
export function useAnchorPruning({
  momentId,
  mediaCount,
  media,
}: {
  momentId: string | undefined;
  /** The Moment's `media_count`, when the Moment has loaded. */
  mediaCount: number | undefined;
  media: Pick<
    MomentMediaState,
    "items" | "isSuccess" | "isFetching" | "fetchedAt"
  >;
}) {
  const { items, isSuccess, isFetching, fetchedAt } = media;
  useEffect(() => {
    if (!momentId) return;
    let present: ReadonlySet<string> | null = null;
    let listedAt = fetchedAt;
    if (isSuccess && !isFetching && items) {
      present = new Set(items.map((item) => item.id));
    } else if (mediaCount === 0) {
      present = new Set();
      listedAt = Date.now();
    }
    if (!present) return;
    void recordingRepository
      .pruneAnchors(momentId, present, listedAt)
      .catch(() => undefined);
  }, [momentId, mediaCount, items, isSuccess, isFetching, fetchedAt]);
}
