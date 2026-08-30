import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";
import { isNotFound } from "../../api/client/errors";
import type { QuillDelta } from "../../api/generated/types.gen";
import { momentMediaQuery, momentQuery } from "../../api/query/options";
import {
  draftContentEquals,
  draftMediaIds,
  rehydrateDraftDelta,
} from "./draftCanonical";
import { draftRepository, type EditorDraftV1 } from "./draftRepository";
import type { DraftIdentity } from "./useEntryDraft";

/**
 * Deciding what to open the editor with, BEFORE the editor opens.
 *
 * `QuillSurface` takes its document once, at mount, and deliberately cannot be
 * reseeded — reseeding would fight the undo history and the media pipeline. So
 * every question about a local draft is settled here, above the form: is there
 * one, is it different from the server, did the server move underneath it, and
 * can its attachments be resolved. The editor then mounts once, with an answer.
 *
 * The one thing this never does is decide FOR the user. A draft is offered,
 * never applied; a newer server version is warned about, never merged; and the
 * record is deleted only on an explicit Discard or a confirmed server save —
 * never because two timestamps happened to differ.
 */

export type DraftRecoveryState =
  /** Still reading the local record. */
  | { phase: "checking" }
  /** Reading the Moment's media, to resolve the attachments in the draft. */
  | { phase: "resolving"; draft: EditorDraftV1 }
  /**
   * The draft has attachments and the server cannot be reached to re-sign them.
   * The writing is safe and is offered as text; the editor stays closed rather
   * than open on a document that could save away the photos it cannot see.
   */
  | { phase: "unreachable-media"; draft: EditorDraftV1; retry: () => void }
  /** A draft worth offering, with a document ready to mount. */
  | {
      phase: "offer";
      draft: EditorDraftV1;
      content: QuillDelta;
      /** The entry changed elsewhere since this draft was written. */
      serverChanged: boolean;
      /** Attachments the Moment no longer has, dropped from `content`. */
      unresolvedMediaCount: number;
      /**
       * Media ids the draft referenced that the Moment still holds. The editor
       * counts these as attachments this session is responsible for, so that
       * cancelling a recovered draft keeps the photographs — the same thing it
       * does for a draft that was never reloaded.
       */
      resolvedMediaIds: string[];
      /**
       * The draft's server identity as the SERVER currently reports it, not as
       * the record remembers it.
       *
       * A draft records the Moment and Entry it belongs to, and Done finalises
       * through them — so a stale pair means a save that can never succeed. It
       * is null when the Moment is definitely gone (Done then makes a fresh
       * one), and it carries the Moment's real `entry` id, which is how a draft
       * Entry that was deleted underneath the record stops being addressed.
       *
       * Only a definite 404 clears it. A request that got no answer keeps the
       * recorded identity, because dropping it offline would orphan a Moment
       * nobody would ever finalise.
       */
      verifiedIdentity: DraftIdentity | null;
    }
  /** Nothing to recover: open on the server's content. */
  | { phase: "clear" };

export type UseDraftRecoveryOptions = {
  /** Null while the signed-in user is unknown, or before an identity exists. */
  key: string | null;
  /** The Moment that owns any attachments, when one exists. */
  momentId?: string;
  /** The server's document, once loaded. */
  serverContent?: QuillDelta;
  serverTitle?: string;
  serverJournalId?: string;
  /** `entry.updated_at`, for the changed-server check. */
  serverUpdatedAt?: string;
  /** False while the server load is still in flight or has failed. */
  serverLoaded: boolean;
  /** Skip entirely — the route cannot host a draft. */
  enabled?: boolean;
};

export function useDraftRecovery({
  key,
  momentId,
  serverContent,
  serverTitle,
  serverJournalId,
  serverUpdatedAt,
  serverLoaded,
  enabled = true,
}: UseDraftRecoveryOptions) {
  /**
   * The answer, tagged with the key it answers for.
   *
   * Tagged rather than a separate `checked` flag, because the key arrives late:
   * it cannot be built until the signed-in user is known, and that lands in its
   * own render. A bare flag left over from the previous key reads as "already
   * checked" on exactly that render — the editor then opens on the server's
   * content before the draft has been read, and never asks.
   */
  const [answer, setAnswer] = useState<{
    key: string;
    record: EditorDraftV1 | null;
  } | null>(null);
  const checked = Boolean(key) && answer?.key === key;
  const record = checked ? (answer?.record ?? null) : null;
  useEffect(() => {
    if (!enabled || !key) return;

    /**
     * Read on every run, with no "already read this key" guard.
     *
     * A guard here deadlocks under StrictMode: React mounts, tears down and
     * remounts effects in development, so the first read is cancelled by the
     * cleanup and the second is skipped by the guard — leaving the answer
     * forever unset and the editor stuck on a skeleton. The deps are a boolean
     * and a string, so this runs on a real identity change and on a remount,
     * and nowhere else; a repeated read is idempotent and cheap.
     */
    let cancelled = false;
    void draftRepository
      .read(key)
      .catch(() => null)
      .then((found) => {
        if (cancelled) return;
        setAnswer({ key, record: found });
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, key]);

  const mediaIds = useMemo(
    () => (record ? draftMediaIds(record.contentDelta) : []),
    [record],
  );
  const needsMedia = mediaIds.length > 0;
  const mediaMomentId = record?.momentId ?? momentId;

  /**
   * The draft's own Moment, checked rather than assumed.
   *
   * For an entry already open on a Moment this is the query the page already
   * ran, so it is a cache hit and costs nothing. For a new entry whose draft
   * acquired a Moment — the first photo, or the first mood — it is one request
   * on the recovery path, and it is what stops Done finalising through a Moment
   * or Entry that no longer exists.
   */
  const recordedMomentId = record?.momentId ?? null;
  const draftMoment = useQuery({
    ...momentQuery(recordedMomentId ?? ""),
    enabled: enabled && Boolean(recordedMomentId),
    // Retry policy is deliberately the app's own. Skipping the retry on a 404
    // would save one request on a path that runs only when a draft is being
    // recovered, at the cost of this query behaving unlike every other one.
  });
  const momentGone = Boolean(recordedMomentId) && isNotFound(draftMoment.error);

  // Only ever fetched to re-sign a draft's attachments; a text-only draft never
  // touches the network at all. A Moment that is gone took its media with it,
  // so there is nothing left to ask about.
  const media = useQuery({
    ...momentMediaQuery(mediaMomentId ?? ""),
    enabled: enabled && needsMedia && Boolean(mediaMomentId) && !momentGone,
  });

  const discard = useCallback(async () => {
    if (!key) return;
    try {
      await draftRepository.delete(key);
    } catch {
      // A record that outlives its usefulness costs one prompt, which resolves
      // itself once the draft matches the server. Never block on it.
    }
    setAnswer({ key, record: null });
  }, [key]);

  const retryMedia = useCallback(() => void media.refetch(), [media]);

  const state = useMemo<DraftRecoveryState>(() => {
    if (!enabled || !key) return { phase: "clear" };
    if (!checked) return { phase: "checking" };
    if (!record) return { phase: "clear" };
    // Wait for the server's own copy before comparing against it; comparing
    // against nothing would offer a recovery for content already on screen.
    if (!serverLoaded && serverContent) return { phase: "checking" };

    // Settle what the server says about the draft's Moment before anything is
    // decided from the record's memory of it.
    if (recordedMomentId && !momentGone && draftMoment.isPending) {
      return { phase: "resolving", draft: record };
    }

    if (needsMedia && !momentGone) {
      if (!mediaMomentId) {
        // A draft with attachments always carries the Moment that owns them.
        // Without one they cannot be resolved, so treat it as unreachable
        // rather than guessing.
        return { phase: "unreachable-media", draft: record, retry: retryMedia };
      }
      if (media.isPending || media.isFetching) {
        return { phase: "resolving", draft: record };
      }
      if (media.isError || !media.data) {
        return { phase: "unreachable-media", draft: record, retry: retryMedia };
      }
    }

    // A Moment that is gone resolves nothing, so every attachment the draft
    // held is reported as lost rather than silently dropped.
    const signedUrlById = new Map(
      momentGone
        ? []
        : (media.data ?? []).map((item) => [item.id, item.signed_url]),
    );
    const { delta: content, unresolvedMediaCount } = rehydrateDraftDelta(
      record.contentDelta,
      signedUrlById,
    );

    // Nothing to offer when the draft says exactly what the server already
    // holds — the usual cause is a save that landed in another tab. Deleting it
    // here is not a timestamp decision: the two documents are identical.
    const sameContent = serverContent
      ? draftContentEquals(content, serverContent)
      : content.ops?.every(
          (op) => typeof op.insert === "string" && op.insert.trim() === "",
        ) === true;
    const sameTitle = (record.title ?? "") === (serverTitle ?? "");
    const sameJournal =
      !record.journalId || record.journalId === (serverJournalId ?? "");
    if (sameContent && sameTitle && sameJournal && unresolvedMediaCount === 0) {
      return { phase: "clear" };
    }

    return {
      phase: "offer",
      draft: record,
      content,
      resolvedMediaIds: mediaIds.filter((id) => signedUrlById.has(id)),
      verifiedIdentity:
        !recordedMomentId || momentGone
          ? null
          : {
              momentId: recordedMomentId,
              // The Moment's own answer wins over the record's. A draft Entry
              // deleted underneath this draft — a second tab cancelling the
              // same one — would otherwise be addressed by an update that can
              // only 404.
              entryId: draftMoment.data
                ? (draftMoment.data.entry?.id ?? null)
                : (record.entryId ?? null),
            },
      serverChanged: Boolean(
        record.baseUpdatedAt &&
          serverUpdatedAt &&
          record.baseUpdatedAt !== serverUpdatedAt,
      ),
      unresolvedMediaCount,
    };
  }, [
    checked,
    enabled,
    key,
    media.data,
    media.isError,
    media.isFetching,
    media.isPending,
    mediaIds,
    mediaMomentId,
    momentGone,
    draftMoment.data,
    draftMoment.isPending,
    recordedMomentId,
    needsMedia,
    record,
    retryMedia,
    serverContent,
    serverJournalId,
    serverLoaded,
    serverTitle,
    serverUpdatedAt,
  ]);

  /** Deletes a matching draft that will never be offered, so it cannot linger. */
  useEffect(() => {
    if (state.phase === "clear" && record) void discard();
  }, [discard, record, state.phase]);

  return { state, discard };
}
