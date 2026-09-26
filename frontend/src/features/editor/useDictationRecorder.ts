import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  LOW_TIME_WARNING_MS,
  maxRecordingMs,
  pickRecorderMime,
  REQUESTED_BITS_PER_SECOND,
  RollingPeaks,
  SIZE_SAFETY_MARGIN,
  TIMESLICE_MS,
} from "./dictationFormat";

/**
 * One dictation session: microphone -> `MediaRecorder` -> chunks.
 *
 * This hook owns the browser side only — permission, container negotiation, the
 * duration cap, the live level meter and releasing the microphone. It knows
 * nothing about IndexedDB or uploading: chunks go to an injected `staging` sink
 * as they arrive, and `stop()` hands back what was recorded. Composition lives in
 * `useDictation`. See docs/features/editor.md, Voice notes.
 *
 * The recorder never records into a container it did not pick, never discards
 * speech to enforce a limit, and never leaves the microphone open: every track is
 * stopped on stop, on error and on unmount.
 */

export type DictationErrorKind =
  | "insecure-context"
  | "unsupported"
  | "permission-denied"
  | "no-microphone"
  | "failed";

export type DictationError = { kind: DictationErrorKind; message: string };

const MESSAGES: Record<DictationErrorKind, string> = {
  "insecure-context":
    "Voice notes need a secure connection. Open Journiv over HTTPS (or on localhost) to record.",
  unsupported: "This browser can’t record audio here.",
  "permission-denied":
    "Microphone access is blocked. Allow the microphone for this site in your browser settings, then try again.",
  "no-microphone": "No microphone was found on this device.",
  failed: "Recording couldn’t start. Try again.",
};

const dictationError = (kind: DictationErrorKind): DictationError => ({
  kind,
  message: MESSAGES[kind],
});

export type DictationAvailability =
  | { state: "available" }
  | {
      state: "unavailable";
      reason: "insecure-context" | "unsupported";
      message: string;
    };

/**
 * Whether this page can record at all, decided before the writer asks.
 *
 * `getUserMedia` needs a secure context, and plain HTTP is a real self-hosting
 * configuration (docs/features/pwa.md) — so this is a state to explain, not a
 * button to hide.
 */
export function dictationAvailability(): DictationAvailability {
  if (typeof window !== "undefined" && window.isSecureContext === false) {
    return {
      state: "unavailable",
      reason: "insecure-context",
      message: MESSAGES["insecure-context"],
    };
  }
  const supported =
    typeof navigator !== "undefined" &&
    typeof navigator.mediaDevices?.getUserMedia === "function" &&
    typeof MediaRecorder !== "undefined" &&
    pickRecorderMime((type) => MediaRecorder.isTypeSupported(type)) !== null;
  return supported
    ? { state: "available" }
    : {
        state: "unavailable",
        reason: "unsupported",
        message: MESSAGES.unsupported,
      };
}

function errorFromException(caught: unknown): DictationError {
  const name = caught instanceof DOMException ? caught.name : "";
  if (name === "NotAllowedError" || name === "SecurityError") {
    return dictationError("permission-denied");
  }
  if (name === "NotFoundError" || name === "OverconstrainedError") {
    return dictationError("no-microphone");
  }
  return dictationError("failed");
}

export type RecorderStatus = "idle" | "starting" | "recording" | "stopping";

/** Where chunks go as they arrive. Failing to persist must not stop recording. */
export type RecorderStaging = {
  begin(info: { mimeType: string; startedAt: string }): Promise<void>;
  append(index: number, chunk: Blob): Promise<void>;
};

export type RecordedAudio = {
  /** The container the recorder actually wrote, not the one that was asked for. */
  mimeType: string;
  startedAt: string;
  durationMs: number;
  chunkCount: number;
  /**
   * Chunks that never reached `staging` (there was none, or it failed), by
   * index. Together with what staging holds this is the whole recording.
   */
  unstaged: ReadonlyMap<number, Blob>;
  /** Whether every chunk was handed to a working staging sink. */
  staged: boolean;
  /** Why it ended, when the writer did not press Stop. */
  endedBecause?: "limit" | "interrupted";
};

export type LiveSnapshot = {
  elapsedMs: number;
  /** The remaining budget, or null when the instance limit is unknown. */
  remainingMs: number | null;
  lowTime: boolean;
  /** Recent input level, oldest first, each 0..1. */
  bars: readonly number[];
};

const IDLE_SNAPSHOT: LiveSnapshot = {
  elapsedMs: 0,
  remainingMs: null,
  lowTime: false,
  bars: [],
};

const TICK_MS = 250;
/** One level sample every 100 ms; 600 keeps the last minute. */
const LEVEL_SAMPLE_MS = 100;
const LEVEL_WINDOW = 600;
export const LIVE_BARS = 64;

export type DictationRecorderOptions = {
  /** `max_file_size_mb` from `GET /instance/config`; unknown leaves it uncapped. */
  maxFileSizeMb?: number | null;
  staging?: RecorderStaging;
  /** Called when a recording ends without Stop being pressed. */
  onEnded?: (audio: RecordedAudio) => void;
};

/**
 * One press of the record button, from the request for the microphone until the
 * recorder is running. It is cancellable at every step: the permission prompt
 * can stay open indefinitely and staging opens IndexedDB, and during that time
 * there is nothing to stop or discard — only a start to abandon.
 */
type StartAttempt = { cancelled: boolean };

type ActiveSession = {
  recorder: MediaRecorder;
  stream: MediaStream;
  startedAt: string;
  startedPerf: number;
  mimeType: string;
  limitMs: number | null;
  limitBytes: number | null;
  bytes: number;
  nextIndex: number;
  unstaged: Map<number, Blob>;
  inflight: Set<Promise<void>>;
  stagingBroken: boolean;
  everStaged: boolean;
  peaks: RollingPeaks;
  audio: { context: AudioContext; analyser: AnalyserNode } | null;
  timers: number[];
  ending: "user" | "limit" | "interrupted" | "discard" | null;
  finalized: boolean;
  settle: ((audio: RecordedAudio | null) => void) | null;
};

function releaseStream(stream: MediaStream) {
  for (const track of stream.getTracks()) track.stop();
}

export function useDictationRecorder({
  maxFileSizeMb,
  staging,
  onEnded,
}: DictationRecorderOptions = {}) {
  const [status, setStatus] = useState<RecorderStatus>("idle");
  const [error, setError] = useState<DictationError | null>(null);
  const availability = useMemo(() => dictationAvailability(), []);

  const session = useRef<ActiveSession | null>(null);
  /** The start in flight, if any. Null once recording, or once it is cancelled. */
  const attempt = useRef<StartAttempt | null>(null);
  /**
   * Settles when the previous start has finished with the microphone. A cancelled
   * start whose permission prompt is still open must not overlap the next one.
   */
  const previousStart = useRef<Promise<void>>(Promise.resolve());
  const mounted = useRef(true);
  const onEndedRef = useRef(onEnded);
  onEndedRef.current = onEnded;
  const stagingRef = useRef(staging);
  stagingRef.current = staging;
  const maxMbRef = useRef(maxFileSizeMb);
  maxMbRef.current = maxFileSizeMb;

  // Live values go through an external store so a 10 Hz tick re-renders only the
  // recording bar that reads it — never the editor page, whose typing-cost
  // invariants forbid work per keystroke-scale event (docs/features/editor.md).
  const live = useMemo(() => {
    let snapshot = IDLE_SNAPSHOT;
    const listeners = new Set<() => void>();
    return {
      subscribe(listener: () => void) {
        listeners.add(listener);
        return () => listeners.delete(listener);
      },
      getSnapshot: () => snapshot,
      set(next: LiveSnapshot) {
        snapshot = next;
        for (const listener of listeners) listener();
      },
    };
  }, []);

  const teardown = useCallback(
    (active: ActiveSession) => {
      for (const timer of active.timers) window.clearInterval(timer);
      active.timers = [];
      releaseStream(active.stream);
      if (active.audio) {
        void active.audio.context.close().catch(() => undefined);
        active.audio = null;
      }
      if (session.current === active) session.current = null;
      live.set(IDLE_SNAPSHOT);
    },
    [live],
  );

  const finish = useCallback(
    async (active: ActiveSession): Promise<RecordedAudio> => {
      // Let every in-flight write land or fail before deciding what is unstaged.
      await Promise.allSettled([...active.inflight]);
      const durationMs = Math.max(0, performance.now() - active.startedPerf);
      const chunkCount = active.nextIndex;
      return {
        mimeType: active.mimeType,
        startedAt: active.startedAt,
        durationMs,
        chunkCount,
        unstaged: new Map(active.unstaged),
        staged: active.everStaged && !active.stagingBroken,
        ...(active.ending === "limit" || active.ending === "interrupted"
          ? { endedBecause: active.ending }
          : {}),
      };
    },
    [],
  );

  const complete = useCallback(
    async (active: ActiveSession) => {
      // Some implementations throw from stop() while also dispatching a stop
      // event. Only one path may hand the recording to its owner.
      if (active.finalized) return;
      active.finalized = true;
      const settle = active.settle;
      if (active.ending === "discard") {
        await Promise.allSettled([...active.inflight]);
        teardown(active);
        settle?.(null);
        return;
      }
      if (!active.ending) active.ending = "interrupted";
      const audio = await finish(active);
      teardown(active);
      if (mounted.current) setStatus("idle");
      if (settle) settle(audio);
      else onEndedRef.current?.(audio);
    },
    [finish, teardown],
  );

  /** Abandons a start that has not begun recording. False when none is in flight. */
  const cancelStart = useCallback((): boolean => {
    const current = attempt.current;
    if (!current) return false;
    current.cancelled = true;
    attempt.current = null;
    setStatus("idle");
    return true;
  }, []);

  const start = useCallback(async (): Promise<boolean> => {
    if (session.current || attempt.current || status !== "idle") return false;
    setError(null);
    if (availability.state === "unavailable") {
      setError(dictationError(availability.reason));
      return false;
    }
    const mine: StartAttempt = { cancelled: false };
    attempt.current = mine;
    const before = previousStart.current;
    let finished!: () => void;
    previousStart.current = new Promise<void>((resolve) => {
      finished = resolve;
    });
    setStatus("starting");
    try {
      // A cancelled start may still be waiting on its permission prompt.
      await before;
      return await beginRecording(mine);
    } finally {
      if (attempt.current === mine) attempt.current = null;
      finished();
    }

    async function beginRecording(me: StartAttempt): Promise<boolean> {
      // Stale once cancelled (the writer pressed Stop/Discard while starting) or
      // once the editor has gone. A stale start owns nothing but what it holds.
      const stale = () => me.cancelled || !mounted.current;
      if (stale()) return false;

      let stream: MediaStream;
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true },
        });
      } catch (caught) {
        if (stale()) return false;
        setError(errorFromException(caught));
        setStatus("idle");
        return false;
      }
      if (stale()) {
        releaseStream(stream);
        return false;
      }

      const requested = pickRecorderMime((type) =>
        MediaRecorder.isTypeSupported(type),
      );
      let recorder: MediaRecorder;
      try {
        if (!requested) throw new Error("no supported container");
        recorder = new MediaRecorder(stream, {
          mimeType: requested,
          audioBitsPerSecond: REQUESTED_BITS_PER_SECOND,
        });
      } catch {
        releaseStream(stream);
        if (stale()) return false;
        setError(dictationError("unsupported"));
        setStatus("idle");
        return false;
      }

      // What the recorder will actually write. It can differ from the request (a
      // different or more specific type), and the File built from it must carry
      // the real one or the server's sniff and the client's kind can disagree.
      const mimeType = recorder.mimeType || requested;
      const bitsPerSecond =
        recorder.audioBitsPerSecond || REQUESTED_BITS_PER_SECOND;
      const limitMs = maxRecordingMs(maxMbRef.current, bitsPerSecond);
      const limitBytes = maxMbRef.current
        ? Math.floor(maxMbRef.current * 1024 * 1024 * SIZE_SAFETY_MARGIN)
        : null;

      const startedAt = new Date().toISOString();
      const active: ActiveSession = {
        recorder,
        stream,
        startedAt,
        startedPerf: performance.now(),
        mimeType,
        limitMs,
        limitBytes,
        bytes: 0,
        nextIndex: 0,
        unstaged: new Map(),
        inflight: new Set(),
        stagingBroken: false,
        everStaged: false,
        peaks: new RollingPeaks(LEVEL_WINDOW),
        audio: null,
        timers: [],
        ending: null,
        finalized: false,
        settle: null,
      };
      // Staging is best effort: if it cannot begin, recording carries on in memory
      // and `staged` says so, so the UI never promises crash-safety it lacks.
      const sink = stagingRef.current;
      let stagingReady = false;
      if (sink) {
        try {
          await sink.begin({ mimeType, startedAt });
          stagingReady = true;
          active.everStaged = true;
        } catch {
          active.stagingBroken = true;
        }
      } else {
        active.stagingBroken = true;
      }

      // Nothing has been published yet, so a start cancelled while staging opened
      // (or an editor that went away) releases the microphone and stops here. Any
      // staged session it created is the caller's to delete.
      if (stale()) {
        releaseStream(stream);
        return false;
      }
      // From here to `recorder.start` there is no `await`, so nothing can cancel
      // the start half way: the session is published only once it cannot be.
      session.current = active;

      recorder.addEventListener("dataavailable", (event) => {
        const chunk = (event as BlobEvent).data;
        if (!chunk || chunk.size === 0) return;
        const index = active.nextIndex;
        active.nextIndex += 1;
        active.bytes += chunk.size;
        if (stagingReady && sink && !active.stagingBroken) {
          const write = sink
            .append(index, chunk)
            .catch(() => {
              // This chunk and any later one are held in memory instead.
              active.stagingBroken = true;
              active.unstaged.set(index, chunk);
            })
            .finally(() => active.inflight.delete(write));
          active.inflight.add(write);
        } else {
          active.unstaged.set(index, chunk);
        }
        if (
          active.limitBytes !== null &&
          active.bytes >= active.limitBytes &&
          !active.ending
        ) {
          endOnItsOwn("limit");
        }
      });

      recorder.addEventListener("error", () => {
        if (!active.ending) endOnItsOwn("interrupted");
      });

      recorder.addEventListener("stop", () => void complete(active));

      // A microphone that is unplugged, or taken by the OS (an incoming call on a
      // phone), ends the track without pressing Stop for the writer.
      for (const track of stream.getTracks()) {
        track.addEventListener("ended", () => {
          if (!active.ending && recorder.state !== "inactive") {
            endOnItsOwn("interrupted");
          }
        });
      }

      function endOnItsOwn(reason: "limit" | "interrupted") {
        if (active.ending || recorder.state === "inactive") return;
        active.ending = reason;
        if (mounted.current) setStatus("stopping");
        try {
          recorder.stop();
        } catch {
          void complete(active);
        }
      }

      // Elapsed time, the remaining budget and the level meter.
      startLevelMeter(active);
      active.timers.push(
        window.setInterval(() => {
          const elapsedMs = performance.now() - active.startedPerf;
          const remainingMs =
            active.limitMs === null
              ? null
              : Math.max(0, active.limitMs - elapsedMs);
          live.set({
            elapsedMs,
            remainingMs,
            lowTime: remainingMs !== null && remainingMs <= LOW_TIME_WARNING_MS,
            bars: active.peaks.bars(LIVE_BARS),
          });
          if (remainingMs !== null && remainingMs <= 0) endOnItsOwn("limit");
        }, TICK_MS),
      );

      try {
        recorder.start(TIMESLICE_MS);
      } catch {
        teardown(active);
        setError(dictationError("failed"));
        setStatus("idle");
        return false;
      }
      setStatus("recording");
      return true;
    }
  }, [availability, complete, live, status, teardown]);

  /**
   * Stops and resolves with what was recorded. Null when nothing is recording.
   * While a start is still in flight (a permission prompt is open, or staging is
   * opening) there is nothing to stop, so this abandons the start instead.
   */
  const stop = useCallback((): Promise<RecordedAudio | null> => {
    if (cancelStart()) return Promise.resolve(null);
    const active = session.current;
    if (!active || active.ending || active.recorder.state === "inactive") {
      return Promise.resolve(null);
    }
    active.ending = "user";
    setStatus("stopping");
    return new Promise((resolve) => {
      active.settle = resolve;
      try {
        active.recorder.stop();
      } catch {
        void complete(active);
      }
    });
  }, [cancelStart, complete]);

  /**
   * Throws the recording away. Callers confirm with the writer first. While a
   * start is still in flight there is no recording yet: the start is abandoned,
   * and it never goes on to record.
   */
  const discard = useCallback((): Promise<void> => {
    if (cancelStart()) return Promise.resolve();
    const active = session.current;
    if (!active) {
      setStatus("idle");
      return Promise.resolve();
    }
    if (active.finalized) return Promise.resolve();
    active.ending = "discard";
    return new Promise((resolve) => {
      active.settle = () => {
        if (mounted.current) setStatus("idle");
        resolve();
      };
      if (active.recorder.state === "inactive") {
        void complete(active);
        return;
      }
      try {
        active.recorder.stop();
      } catch {
        void complete(active);
      }
    });
  }, [cancelStart, complete]);

  /** Whether a start is in flight. Read from a ref, so it is never stale. */
  const isStarting = useCallback(() => attempt.current !== null, []);

  const clearError = useCallback(() => setError(null), []);

  // A live microphone indicator left on after the writer has gone is a serious
  // trust bug: release everything when the editor goes away.
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      const active = session.current;
      if (!active) return;
      active.ending = "discard";
      try {
        if (active.recorder.state !== "inactive") active.recorder.stop();
      } catch {
        // Nothing left to stop.
      }
      teardown(active);
    };
  }, [teardown]);

  return {
    availability,
    status,
    error,
    clearError,
    live,
    start,
    stop,
    discard,
    isStarting,
  };
}

/**
 * Feeds the rolling level window from an `AnalyserNode`. Purely cosmetic, so any
 * failure (no Web Audio, a suspended context) leaves recording untouched and the
 * bar simply shows no waveform.
 */
function startLevelMeter(active: ActiveSession) {
  try {
    const Context =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext })
        .webkitAudioContext;
    if (!Context) return;
    const context = new Context();
    const analyser = context.createAnalyser();
    analyser.fftSize = 512;
    context.createMediaStreamSource(active.stream).connect(analyser);
    active.audio = { context, analyser };
    const buffer = new Uint8Array(analyser.fftSize);
    active.timers.push(
      window.setInterval(() => {
        analyser.getByteTimeDomainData(buffer);
        let peak = 0;
        for (const value of buffer)
          peak = Math.max(peak, Math.abs(value - 128));
        active.peaks.push(peak / 128);
      }, LEVEL_SAMPLE_MS),
    );
  } catch {
    active.audio = null;
  }
}
