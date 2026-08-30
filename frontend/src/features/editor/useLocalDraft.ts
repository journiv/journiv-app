import { useCallback, useEffect, useRef, useState } from "react";
import type { QuillDelta } from "../../api/generated/types.gen";
import { canonicalizeDeltaForDraft } from "./draftCanonical";
import {
  DraftStorageError,
  draftRepository,
  type EditorDraftV1,
} from "./draftRepository";

/**
 * Keeping unsaved writing on this device.
 *
 * Journiv has no server autosave and this is not one. Done is still the only
 * thing that puts writing in a journal; this only means a reload, a crashed tab
 * or a phone that killed the page does not take the words with it.
 *
 * Two rules shape everything here:
 *
 * - **The server is never called from this path.** No `api.*`, no query
 *   invalidation, no fetch. A debounce that runs every 500ms while someone
 *   types must not become traffic.
 * - **Nothing fails silently.** Every outcome — written, failed, or a browser
 *   that will not store anything at all — reaches the screen with words a
 *   person can act on. A silent no-op under a "Saved locally" label would be
 *   worse than having no local drafts.
 */

/** Long enough not to write on every keystroke, short enough to bound the loss. */
export const DRAFT_DEBOUNCE_MS = 500;

export type DraftStatus =
  /** Nothing worth keeping yet. */
  | "idle"
  /** A write is in flight. */
  | "saving"
  /** A write completed. Only ever set after the transaction resolves. */
  | "saved"
  /** A write was attempted and did not happen. */
  | "failed"
  /** This browser will not store anything (private mode, blocked site data). */
  | "unavailable"
  /**
   * This entry holds durable content a draft cannot represent, so NOTHING is
   * stored for it. Refusing is the point: a lossy draft would drop that content
   * on recovery, and the next Done would then ask the backend to delete the
   * media it no longer sees.
   */
  | "unsupported";

export type LocalDraftIdentity = {
  userId: string;
  entryId?: string;
  momentId?: string;
  localDraftId?: string;
};

export type UseLocalDraftOptions = {
  /**
   * Where this draft is stored, or null when it cannot be known yet — the
   * signed-in user is still loading, say. A record that is not scoped to a user
   * is never written; no draft is better than an unscoped one.
   */
  key: string | null;
  identity: LocalDraftIdentity | null;
  journalId: string;
  title: string;
  /**
   * A non-"now" logged date the writer picked for a new entry. Kept so a reload
   * before the server Moment exists does not silently reset it. Omit for an
   * existing entry — the Moment is the source of truth there.
   */
  loggedAtUtc?: string;
  loggedTimezone?: string;
  /** `entry.updated_at` when the editor opened, for the changed-server check. */
  baseUpdatedAt?: string;
  /** Whether there is anything worth keeping. */
  dirty: boolean;
  /** The live document. Returns null when the editor is not ready. */
  getDocument: () => QuillDelta | null;
  /**
   * Fired once, after the first write actually lands. The editor uses it to put
   * the local draft id in the URL — which should not happen until there is
   * really something to come back to.
   */
  onFirstStore?: () => void;
};

type Snapshot =
  | { kind: "nothing" }
  /** Durable content this build cannot represent: refuse, do not store. */
  | { kind: "unsupported" }
  | { kind: "record"; record: EditorDraftV1 };

export function useLocalDraft({
  key,
  identity,
  journalId,
  title,
  loggedAtUtc,
  loggedTimezone,
  baseUpdatedAt,
  dirty,
  getDocument,
  onFirstStore,
}: UseLocalDraftOptions) {
  const [status, setStatus] = useState<DraftStatus>("idle");
  /**
   * In-flight uploads left out of the last stored draft. Not damage — a draft
   * cannot hold bytes still in transit — but the writer has to be told, because
   * recovering will not bring the file back and it must be attached again.
   */
  const [omittedTransientUploads, setOmittedTransientUploads] = useState(0);

  const timer = useRef<number | null>(null);
  const mounted = useRef(true);
  /**
   * Whether a record for this key has landed this session. A ref, not state:
   * it must survive re-renders without causing one, and it is the latch behind
   * `onFirstStore`.
   */
  const stored = useRef(false);
  /**
   * Set by `remove()`. A confirmed save and an explicit discard both delete the
   * record and then leave the editor — and leaving runs the teardown flush.
   * Without this latch that flush can write the record straight back, and a
   * draft that returns from the dead is offered again on the next visit. Any
   * later edit re-arms it, because that edit is worth keeping.
   */
  const retired = useRef(false);
  // Everything a write needs, read at write time rather than captured when the
  // write was scheduled — otherwise a flush would persist a stale document.
  const latest = useRef({
    key,
    identity,
    journalId,
    title,
    loggedAtUtc,
    loggedTimezone,
    baseUpdatedAt,
    dirty,
    getDocument,
    onFirstStore,
  });
  latest.current = {
    key,
    identity,
    journalId,
    title,
    loggedAtUtc,
    loggedTimezone,
    baseUpdatedAt,
    dirty,
    getDocument,
    onFirstStore,
  };

  const cancelPending = useCallback(() => {
    if (timer.current !== null) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }
  }, []);

  /** The record to store right now, or why there is not one. */
  const snapshot = useCallback((): Snapshot => {
    const current = latest.current;
    if (!current.key || !current.identity || !current.dirty)
      return { kind: "nothing" };

    let document: QuillDelta | null = null;
    try {
      document = current.getDocument();
    } catch {
      // The surface is mid-teardown or holding something it will not hand over.
      // A draft is a safety net, not a reason to throw into a lifecycle event.
      return { kind: "nothing" };
    }
    if (!document) return { kind: "nothing" };

    const {
      delta,
      omittedTransientUploads: omitted,
      unsupportedEmbeds,
    } = canonicalizeDeltaForDraft(document);

    // The invariant: `Saved locally` may only be shown when every piece of
    // durable content Journiv supports is actually in the draft. Here it is
    // not, so nothing is written — and in particular an earlier, complete draft
    // is left exactly where it is rather than overwritten by a lossy one.
    if (unsupportedEmbeds > 0) return { kind: "unsupported" };

    const record: EditorDraftV1 = {
      key: current.key,
      userId: current.identity.userId,
      ...(current.identity.entryId
        ? { entryId: current.identity.entryId }
        : {}),
      ...(current.identity.momentId
        ? { momentId: current.identity.momentId }
        : {}),
      ...(current.identity.localDraftId
        ? { localDraftId: current.identity.localDraftId }
        : {}),
      ...(current.journalId ? { journalId: current.journalId } : {}),
      title: current.title,
      ...(current.loggedAtUtc ? { loggedAtUtc: current.loggedAtUtc } : {}),
      ...(current.loggedTimezone
        ? { loggedTimezone: current.loggedTimezone }
        : {}),
      contentDelta: delta,
      ...(current.baseUpdatedAt
        ? { baseUpdatedAt: current.baseUpdatedAt }
        : {}),
      modifiedAt: new Date().toISOString(),
      dirty: true,
      ...(omitted ? { omittedTransientUploads: omitted } : {}),
    };
    return { kind: "record", record };
  }, []);

  const write = useCallback(async () => {
    if (retired.current) return;
    const next = snapshot();
    if (next.kind === "nothing") return;
    if (next.kind === "unsupported") {
      if (mounted.current) setStatus("unsupported");
      return;
    }
    const { record } = next;
    if (mounted.current) setStatus("saving");
    try {
      await draftRepository.write(record);
      if (mounted.current) {
        setStatus("saved");
        setOmittedTransientUploads(record.omittedTransientUploads ?? 0);
      }
      // Announced once, and only for a write that actually landed — the editor
      // puts the draft id in the URL from this, and there should be nothing in
      // the URL to come back to until there is really something stored.
      if (!stored.current) {
        stored.current = true;
        latest.current.onFirstStore?.();
      }
    } catch (error) {
      if (!mounted.current) return;
      setStatus(
        error instanceof DraftStorageError && error.unavailable
          ? "unavailable"
          : "failed",
      );
    }
  }, [snapshot]);

  /** Write now. Used by every lifecycle flush point. */
  const flush = useCallback(() => {
    cancelPending();
    void write();
  }, [cancelPending, write]);

  /** Write in a moment, unless something else changes first. */
  const schedule = useCallback(() => {
    retired.current = false;
    cancelPending();
    timer.current = window.setTimeout(() => {
      timer.current = null;
      void write();
    }, DRAFT_DEBOUNCE_MS);
  }, [cancelPending, write]);

  /**
   * Forget the local copy.
   *
   * Only two things may call this: a CONFIRMED server save, and the user
   * explicitly discarding. Never a failure, never a timestamp comparison.
   */
  const remove = useCallback(async () => {
    cancelPending();
    retired.current = true;
    const target = latest.current.key;
    if (!target) return;
    try {
      await draftRepository.delete(target);
      stored.current = false;
      if (mounted.current) {
        setStatus("idle");
        setOmittedTransientUploads(0);
      }
    } catch {
      // A record that outlives its entry costs one recovery prompt that
      // resolves itself: the recovery check deletes a draft matching the
      // server. Never block the user's navigation on this.
    }
  }, [cancelPending]);

  useEffect(() => {
    mounted.current = true;
    /**
     * `visibilitychange` is the one that lands. `pagehide` fires too late on
     * mobile for an async IndexedDB transaction to be certain of completing —
     * so this is best effort, and the 500ms debounce is what actually bounds
     * how much writing is at risk. Do not claim otherwise on screen.
     */
    const onVisibility = () => {
      if (document.visibilityState === "hidden") flush();
    };
    const onPageHide = () => flush();

    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pagehide", onPageHide);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pagehide", onPageHide);
      // Teardown is a flush point: leaving the editor by any route — including
      // an in-app navigation that never fires a page lifecycle event — must not
      // drop the last few hundred milliseconds of typing.
      cancelPending();
      void write();
      mounted.current = false;
    };
  }, [cancelPending, flush, write]);

  return { status, omittedTransientUploads, schedule, flush, remove };
}

export type LocalDraftState = ReturnType<typeof useLocalDraft>;
