import { useCallback, useRef, useState } from "react";
import { api } from "../../api/client/api";
import type { MomentResponse } from "../../api/generated/types.gen";

export type DraftIdentity = { momentId: string; entryId: string | null };

/**
 * Server identity for an Entry that is still being written.
 *
 * Media upload requires a `moment_id`, and `EntryDraftCreate` requires one too,
 * so a brand-new Entry has no server identity until we make one. This mirrors
 * the Flutter client (`entry_form_notifier._ensureDraftMomentExists` ->
 * `_createDraftEntry`), with one deliberate difference: Flutter creates the
 * draft when the form opens, so merely tapping "New entry" and backing out
 * leaves a row. Journiv-web creates it on first real intent — the first media
 * attachment — because without autosave an empty draft buys nothing.
 *
 * A draft Entry is `is_draft = true`, and `moment_service._apply_draft_filter`
 * excludes those Moments from the Timeline, so an abandoned draft is invisible
 * rather than clutter. `GET /entries/drafts` can still recover it.
 */
export function useEntryDraft({
  moment,
  loggedAtUtc,
  loggedTimezone,
  initialIdentity,
}: {
  moment?: MomentResponse;
  loggedAtUtc: string;
  loggedTimezone: string;
  /**
   * A draft Moment an EARLIER session created and a recovered local draft
   * brought back. It is adopted as if this session had made it: `ensure()`
   * returns it instead of creating a second Moment — which would leave the
   * recovered document pointing at media owned by a Moment nobody finalises —
   * and Cancel still cleans it up, because it is still an unfinished draft that
   * only this editor knows about.
   *
   * Ignored entirely when `moment` is set. Recovery cannot tell a draft Moment
   * from a saved one, so this hook draws that line and refuses to own anything
   * the editor did not open blank.
   */
  initialIdentity?: DraftIdentity | null;
}) {
  // Identity created by THIS editing session. An existing Moment is not a
  // draft we own, and must never be cleaned up on cancel.
  //
  // That is why `initialIdentity` is refused outright when `moment` is set. A
  // local draft records the Moment it belongs to, so recovering one for an
  // entry that is already saved hands back the reader's own Moment id — and
  // adopting it would make Cancel delete a real journal entry.
  const owned = moment ? null : (initialIdentity ?? null);
  const [created, setCreated] = useState<DraftIdentity | null>(owned);
  const inFlight = useRef<Promise<DraftIdentity> | null>(null);
  const createdRef = useRef<DraftIdentity | null>(owned);
  const discardRequested = useRef<boolean | null>(null);

  const cleanup = useCallback(
    async (identity: DraftIdentity, keepMedia: boolean) => {
      try {
        if (keepMedia) {
          if (identity.entryId) await api.deleteEntry(identity.entryId);
        } else {
          await api.deleteMoment(identity.momentId);
        }
      } catch {
        // A failed cleanup leaves an invisible draft, recoverable through
        // /entries/drafts. Never block the user's navigation on it.
      }
    },
    [],
  );

  const ensure = useCallback(
    async (journalId: string): Promise<DraftIdentity> => {
      if (moment)
        return { momentId: moment.id, entryId: moment.entry?.id ?? null };
      if (createdRef.current) return createdRef.current;
      // Single-flight: selecting several files at once must not race into
      // several Moments.
      if (inFlight.current) return inFlight.current;

      const work = (async () => {
        const draftMoment = await api.createMoment({
          logged_at_utc: loggedAtUtc,
          logged_timezone: loggedTimezone,
        });
        let entryId: string | null = null;
        try {
          const draftEntry = await api.createDraftEntry({
            journal_id: journalId,
            moment_id: draftMoment.id,
            content_delta: null,
            title: null,
          });
          entryId = draftEntry.id;
        } catch {
          // The Moment alone is enough to own media. Losing the draft Entry
          // only costs recoverability, so do not fail the attachment.
          entryId = null;
        }
        const identity: DraftIdentity = { momentId: draftMoment.id, entryId };
        createdRef.current = identity;
        const keepMedia = discardRequested.current;
        if (keepMedia !== null) {
          discardRequested.current = null;
          createdRef.current = null;
          await cleanup(identity, keepMedia);
          return identity;
        }
        setCreated(identity);
        return identity;
      })();

      inFlight.current = work;
      try {
        return await work;
      } finally {
        inFlight.current = null;
      }
    },
    [cleanup, moment, loggedAtUtc, loggedTimezone],
  );

  /**
   * Cancel cleanup. Media the user actually attached is kept: it becomes a
   * media-only Moment, which the reader already renders. Deleting photographs
   * someone just took would be the wrong default.
   */
  const discard = useCallback(
    async (keepMedia: boolean) => {
      // Second line of defence for the same invariant: whatever else happens,
      // a session that opened on an existing Moment deletes nothing.
      if (moment) return;
      const identity = createdRef.current;
      if (!identity) {
        if (inFlight.current) discardRequested.current = keepMedia;
        return;
      }
      createdRef.current = null;
      setCreated(null);
      await cleanup(identity, keepMedia);
    },
    [cleanup, moment],
  );

  /** Forget the draft without touching the server — used after a successful save. */
  const adopt = useCallback(() => {
    createdRef.current = null;
    setCreated(null);
  }, []);

  return { draft: created, ensure, discard, adopt };
}
