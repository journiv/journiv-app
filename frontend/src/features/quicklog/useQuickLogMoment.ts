import { useCallback, useRef, useState } from "react";
import { api } from "../../api/client/api";

/**
 * Server identity for a moment being captured in the Quick Log sheet.
 *
 * Quick Log follows the same "server identity first" rule as the editor
 * (docs/features/editor.md): mood, people, tags, location and media writes all
 * need a `moment_id`, so the first of them creates the row. Unlike the editor
 * this moment has **no entry** — it is a note / mood / media-only Moment
 * (docs/domain/moments.md) — so there is no draft Entry and nothing is hidden
 * from the Timeline; an abandoned capture is deleted outright on discard.
 *
 * `momentId` is accepted so a later "edit an existing lightweight moment in
 * Quick Log" mode can reuse this hook, but v1 never passes it
 * (docs/features/quicklog.md "Known gaps").
 */
export function useQuickLogMoment({
  momentId,
  loggedAtUtc,
  loggedTimezone,
}: {
  momentId?: string;
  loggedAtUtc: string;
  loggedTimezone: string;
}) {
  const existing = momentId ?? null;
  const [createdId, setCreatedId] = useState<string | null>(existing);
  const createdRef = useRef<string | null>(existing);
  const inFlight = useRef<Promise<string> | null>(null);
  // Set when discard runs before an in-flight create resolves: the create's
  // continuation then cleans up instead of publishing the id.
  const discardKeepMedia = useRef<boolean | null>(null);

  const cleanup = useCallback(async (id: string, keepMedia: boolean) => {
    // Media the user actually attached is kept — the row survives as a
    // media-only Moment, which the reader already renders. Deleting photographs
    // someone just took would be the wrong default (same rule as the editor's
    // Cancel, docs/features/editor.md).
    if (keepMedia) return;
    try {
      await api.deleteMoment(id);
    } catch {
      // A failed cleanup leaves a thin Moment. Never block the user's
      // navigation on it.
    }
  }, []);

  const ensure = useCallback(async (): Promise<string> => {
    if (existing) return existing;
    if (createdRef.current) return createdRef.current;
    if (inFlight.current) return inFlight.current;

    const work = (async () => {
      const moment = await api.createMoment({
        logged_at_utc: loggedAtUtc,
        logged_timezone: loggedTimezone,
      });
      createdRef.current = moment.id;
      const keepMedia = discardKeepMedia.current;
      if (keepMedia !== null) {
        discardKeepMedia.current = null;
        createdRef.current = null;
        await cleanup(moment.id, keepMedia);
        return moment.id;
      }
      setCreatedId(moment.id);
      return moment.id;
    })();

    inFlight.current = work;
    try {
      return await work;
    } finally {
      inFlight.current = null;
    }
  }, [existing, loggedAtUtc, loggedTimezone, cleanup]);

  /** Dismiss cleanup. `keepMedia` keeps the row as a media-only Moment. */
  const discard = useCallback(
    async (keepMedia: boolean) => {
      if (existing) return;
      const id = createdRef.current;
      if (!id) {
        if (inFlight.current) discardKeepMedia.current = keepMedia;
        return;
      }
      createdRef.current = null;
      setCreatedId(null);
      await cleanup(id, keepMedia);
    },
    [existing, cleanup],
  );

  /** Stop owning the moment — used after a committed save or an editor handoff. */
  const adopt = useCallback(() => {
    createdRef.current = null;
    setCreatedId(null);
  }, []);

  return { momentId: createdId, ensure, discard, adopt };
}
