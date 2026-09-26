import type { QueryClient } from "@tanstack/react-query";
import {
  type RefObject,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { uuid } from "../../lib/uuid";
import { ANCHOR_CONTEXT_CHARS, type DictationAnchor } from "./dictationFormat";
import type { QuillSurfaceHandle } from "./QuillSurface";
import {
  blobToArrayBuffer,
  buildRecordingFile,
  type RecordingSession,
  recordingRepository,
} from "./recordingRepository";
import {
  type DictationUploaded,
  useDictationAttachment,
} from "./useDictationAttachment";
import {
  type RecordedAudio,
  type RecorderStaging,
  useDictationRecorder,
} from "./useDictationRecorder";

/**
 * Dictation, end to end: record at the caret, stage crash-safely, attach the
 * audio to the Moment.
 *
 *   capture anchor -> record (chunks staged as they arrive) -> stop ->
 *   assemble -> upload as a Moment attachment -> delete the staged copy
 *
 * The prose is never touched: a dictation recording is a Moment attachment shown
 * in the editor tray and the reader gallery, and Phase 1 inserts nothing into
 * the entry. The staged copy is deleted only after the upload succeeds, and an
 * unfinished one is offered back for recovery (docs/features/editor.md,
 * Voice notes).
 */
export type DictationPhase =
  | "idle"
  | "starting"
  | "recording"
  | "stopping"
  | "uploading";

type ActiveSession = {
  id: string;
  anchor: DictationAnchor;
  mimeType: string | null;
  startedAt: string | null;
};

export function useDictation({
  surfaceRef,
  ensureDraft,
  queryClient,
  userId,
  draftKey,
  maxFileSizeMb,
  onMediaAdded,
  onAttached,
}: {
  surfaceRef: RefObject<QuillSurfaceHandle | null>;
  ensureDraft: () => Promise<{ momentId: string } | null>;
  queryClient: QueryClient;
  userId: string | null;
  /** The editor's local-draft key: which entry a staged recording belongs to. */
  draftKey: string | null;
  maxFileSizeMb: number | null | undefined;
  /** A recording became a Moment attachment (tracked so Cancel keeps it). */
  onMediaAdded: (mediaId: string) => void;
  onAttached: () => void;
}) {
  const active = useRef<ActiveSession | null>(null);
  /** Whether the current recording is being kept safely as it is made. */
  const [crashSafe, setCrashSafe] = useState<boolean | null>(null);
  const [staged, setStaged] = useState<RecordingSession[]>([]);
  const [notice, setNotice] = useState("");
  const mounted = useRef(true);
  const scope = useRef({ userId, draftKey });
  scope.current = { userId, draftKey };

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const refreshStaged = useCallback(
    async (
      user: string | null = scope.current.userId,
      key: string | null = scope.current.draftKey,
    ) => {
      if (!user || !key) {
        if (mounted.current) setStaged([]);
        return;
      }
      try {
        const all = await recordingRepository.listUnfinished(user);
        if (mounted.current) {
          setStaged(all.filter((session) => session.draftKey === key));
        }
      } catch {
        // Storage unavailable: there is nothing to recover and nothing to say.
        if (mounted.current) setStaged([]);
      }
    },
    [],
  );

  const onUploaded = useCallback(
    async ({ media, momentId, item }: DictationUploaded) => {
      onMediaAdded(media.id);
      onAttached();
      const { userId: user, draftKey: key } = scope.current;
      // Keep where in the entry this was recorded, per media id. Device-local:
      // nothing about it reaches the server or the document. It outlives the
      // staged audio deleted below and ends with the media (useAnchorPruning).
      if (item.anchor && user && key) {
        try {
          await recordingRepository.saveAnchor({
            mediaId: media.id,
            userId: user,
            draftKey: key,
            momentId,
            anchor: item.anchor,
            capturedAt: new Date().toISOString(),
          });
        } catch {
          // The recording is safe on the server; only the record of where it
          // was made is lost. Nothing depends on it.
        }
      }
      // Only now, after the upload has succeeded, may the staged copy go.
      if (item.sessionId) {
        try {
          await recordingRepository.deleteSession(item.sessionId);
        } catch {
          // A leftover staged copy is offered for recovery; never data loss.
        }
      }
      await refreshStaged();
    },
    [onAttached, onMediaAdded, refreshStaged],
  );

  const attachment = useDictationAttachment({
    ensureDraft,
    queryClient,
    onUploaded,
  });
  const { attach } = attachment;

  const staging = useMemo<RecorderStaging>(
    () => ({
      begin: async ({ mimeType, startedAt }) => {
        const session = active.current;
        const { userId: user, draftKey: key } = scope.current;
        if (!session || !user || !key) {
          // No signed-in identity to key it on: record anyway, in memory.
          if (mounted.current) setCrashSafe(false);
          throw new Error("Nothing to stage this recording against");
        }
        session.mimeType = mimeType;
        session.startedAt = startedAt;
        try {
          await recordingRepository.createSession({
            id: session.id,
            userId: user,
            draftKey: key,
            mimeType,
            startedAt,
            updatedAt: startedAt,
            durationMs: 0,
            chunkCount: 0,
            status: "recording",
            anchor: session.anchor,
          });
          if (mounted.current) setCrashSafe(true);
        } catch (caught) {
          if (mounted.current) setCrashSafe(false);
          throw caught;
        }
      },
      append: async (index, chunk) => {
        const session = active.current;
        if (!session) throw new Error("No recording in progress");
        try {
          await recordingRepository.appendChunk(
            session.id,
            index,
            await blobToArrayBuffer(chunk),
          );
        } catch (caught) {
          if (mounted.current) setCrashSafe(false);
          throw caught;
        }
      },
    }),
    [],
  );

  /** A recording ended: assemble it and hand it to the upload. */
  const finalize = useCallback(
    async (audio: RecordedAudio) => {
      const session = active.current;
      active.current = null;
      if (!session) return;

      if (audio.chunkCount === 0) {
        // Nothing was captured. Leave no empty session behind.
        if (audio.staged) {
          await recordingRepository
            .deleteSession(session.id)
            .catch(() => undefined);
        }
        setNotice("Nothing was recorded.");
        return;
      }

      const header = {
        mimeType: audio.mimeType,
        startedAt: audio.startedAt,
      };
      let file: File | null = null;
      let sessionId: string | null = null;
      try {
        const stored = await recordingRepository.readSession(session.id);
        if (stored) {
          sessionId = stored.id;
          await recordingRepository.updateSession(stored.id, {
            status: "stopped",
            durationMs: Math.round(audio.durationMs),
            chunkCount: audio.chunkCount,
          });
          file = await recordingRepository.assemble(stored, audio.unstaged);
        }
      } catch {
        // Staging is unreadable; fall back to what is held in memory below.
      }
      if (!file && audio.unstaged.size === audio.chunkCount) {
        file = buildRecordingFile(header, [...audio.unstaged.entries()]);
      }
      if (!file) {
        setNotice(
          "The full voice note couldn’t be read. Try recovering the copy shown below.",
        );
        await refreshStaged();
        return;
      }
      if (audio.endedBecause === "limit") {
        setNotice(
          "Recording stopped at the largest size this server accepts. It’s being added to this moment.",
        );
      } else if (audio.endedBecause === "interrupted") {
        setNotice(
          "Recording was interrupted. What was captured is being added to this moment.",
        );
      }
      await attach(file, { sessionId, anchor: session.anchor });
      await refreshStaged();
    },
    [attach, refreshStaged],
  );

  const recorder = useDictationRecorder({
    maxFileSizeMb,
    staging,
    onEnded: (audio) => void finalize(audio),
  });
  const { start: startRecorder, stop: stopRecorder, isStarting } = recorder;

  const start = useCallback(async () => {
    // Already recording, or a start is waiting on the microphone: nothing to do,
    // and the live session's bookkeeping must not be replaced.
    if (active.current) return false;
    setNotice("");
    const surface = surfaceRef.current;
    // Captured before anything can steal focus, for the same reason
    // `useMediaAttachments` captures the caret early.
    const index = surface?.getSelectionIndex() ?? 0;
    const around = surface?.getTextAround(index, ANCHOR_CONTEXT_CHARS) ?? {
      before: "",
      after: "",
    };
    const mine: ActiveSession = {
      id: uuid(),
      anchor: { index, ...around },
      mimeType: null,
      startedAt: null,
    };
    active.current = mine;
    setCrashSafe(null);
    const started = await startRecorder();
    if (!started) {
      // Cancelled, refused or failed. A newer start may already own
      // `active.current`, so only clear it if it is still this one.
      if (active.current === mine) active.current = null;
      // A start that got as far as opening staging leaves an empty session
      // behind, which recovery would otherwise offer as an unfinished recording.
      if (mine.mimeType !== null) {
        await recordingRepository.deleteSession(mine.id).catch(() => undefined);
      }
    }
    return started;
  }, [startRecorder, surfaceRef]);

  const stop = useCallback(async () => {
    // During a start there is no recording: this cancels it, and its bookkeeping
    // goes now so the writer can press the microphone again straight away.
    const wasStarting = isStarting();
    const audio = await stopRecorder();
    if (wasStarting) {
      active.current = null;
      return;
    }
    if (audio) await finalize(audio);
  }, [finalize, isStarting, stopRecorder]);

  const discardRecording = useCallback(async () => {
    const session = active.current;
    active.current = null;
    await recorder.discard();
    // Only a session that reached staging has anything to delete; discarding a
    // start that was still waiting on the microphone must not create the database.
    if (session && session.mimeType !== null) {
      await recordingRepository
        .deleteSession(session.id)
        .catch(() => undefined);
    }
    setCrashSafe(null);
    await refreshStaged();
  }, [recorder, refreshStaged]);

  /** Brings back a recording that was staged but never uploaded. */
  const recover = useCallback(
    async (sessionId: string) => {
      const stored = await recordingRepository
        .readSession(sessionId)
        .catch(() => null);
      if (!stored) {
        await refreshStaged();
        return false;
      }
      const file = await recordingRepository.assemble(stored).catch(() => null);
      if (!file) {
        setNotice("That recording couldn’t be read back.");
        await refreshStaged();
        return false;
      }
      await recordingRepository
        .updateSession(sessionId, { status: "stopped" })
        .catch(() => undefined);
      await attach(file, { sessionId, anchor: stored.anchor });
      await refreshStaged();
      return true;
    },
    [attach, refreshStaged],
  );

  /** Deletes a staged recording for good. Callers confirm with the writer. */
  const discardStaged = useCallback(
    async (sessionId: string) => {
      await recordingRepository.deleteSession(sessionId).catch(() => undefined);
      await refreshStaged();
    },
    [refreshStaged],
  );

  /** A failed upload the writer has given up on: its staged copy goes too. */
  const discardFailed = useCallback(
    async (uploadId: string) => {
      const item = attachment.items.find(
        (entry) => entry.uploadId === uploadId,
      );
      attachment.dismiss(uploadId);
      if (item?.sessionId) {
        await recordingRepository
          .deleteSession(item.sessionId)
          .catch(() => undefined);
      }
      await refreshStaged();
    },
    [attachment, refreshStaged],
  );

  // What is offered for recovery is what is neither recording nor uploading now.
  useEffect(() => {
    void refreshStaged(userId, draftKey);
  }, [refreshStaged, draftKey, userId]);

  const busyIds = new Set(
    attachment.items.flatMap((item) =>
      item.sessionId ? [item.sessionId] : [],
    ),
  );
  const recoverable = staged.filter(
    (session) => session.id !== active.current?.id && !busyIds.has(session.id),
  );

  /**
   * The microphone is open and audio is being kept. Not true while a start is
   * still waiting on the permission prompt: nothing has been recorded yet, so
   * there is nothing to save, stop or lose.
   */
  const recording =
    recorder.status === "recording" || recorder.status === "stopping";
  /** A start is in flight (permission prompt open, staging opening). */
  const starting = recorder.status === "starting";

  /**
   * Deletes everything unfinished for this entry: a recording in progress, a
   * failed upload's staged copy, and unrecovered sessions. Used when the writer
   * cancels a NEW entry, whose draft key is never seen again, so anything staged
   * under it could otherwise never be recovered or cleaned up.
   */
  const discardAllUnfinished = useCallback(async () => {
    const { userId: user, draftKey: key } = scope.current;
    active.current = null;
    await recorder.discard();
    attachment.cancelAll();
    if (!user || !key) return;
    try {
      const all = await recordingRepository.listUnfinished(user);
      await Promise.all(
        all
          .filter((session) => session.draftKey === key)
          .map((session) => recordingRepository.deleteSession(session.id)),
      );
    } catch {
      // Nothing staged that we can reach.
    }
  }, [attachment, recorder]);

  const phase: DictationPhase =
    recorder.status !== "idle"
      ? recorder.status
      : attachment.pending > 0
        ? "uploading"
        : "idle";

  return {
    availability: recorder.availability,
    phase,
    recording,
    starting,
    discardAllUnfinished,
    error: recorder.error,
    clearError: recorder.clearError,
    notice,
    clearNotice: () => setNotice(""),
    live: recorder.live,
    crashSafe,
    start,
    stop,
    discard: discardRecording,
    uploads: attachment,
    discardFailed,
    recoverable,
    recover,
    discardStaged,
  };
}
