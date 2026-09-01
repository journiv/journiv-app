import { api } from "../../api/client/api";

/** How long to keep asking whether the worker has finished a file. */
export const PROCESS_POLL_INTERVAL_MS = 1500;
/**
 * Longer than the backend's own retry budget for a not-yet-visible upload row
 * (~2 min of capped backoff before it records a hard failure), so the poll can
 * observe that outcome instead of giving up first and reporting a false success.
 */
export const PROCESS_POLL_TIMEOUT_MS = 180_000;

/** The server reported it could not process the file. */
export const PROCESSING_FAILED_MESSAGE =
  "This file couldn’t be processed. Retry, or remove it from the entry.";
/** Upload landed, but processing never finished within the poll window. */
export const PROCESSING_STALLED_MESSAGE =
  "This file is still being processed. Keep writing — reload the entry later to check, or retry now.";

export type ProcessingOutcome =
  | { state: "done" }
  | { state: "failed"; message: string };

/**
 * Polls `GET /moments/{id}/media` until `mediaId` reaches a terminal
 * `upload_status`, then calls `onOutcome` exactly once.
 *
 * - Stops at `completed` (done) or `failed` (surfaced with a retry).
 * - Pauses while the tab is hidden.
 * - A failed poll is retried, never treated as a failed file.
 * - If the window elapses with no terminal state the file is reported
 *   **failed**, not quietly done — a stuck file must reach the writer.
 *
 * Framework-free so the device-upload hook and the Immich-import hook share one
 * implementation. Scheduled timer ids are parked in `timers` for the caller to
 * clear on unmount.
 */
export function pollMediaProcessing({
  momentId,
  mediaId,
  isActive,
  timers,
  onOutcome,
  now = Date.now,
}: {
  momentId: string;
  mediaId: string;
  /** False once the owning component has unmounted. */
  isActive: () => boolean;
  timers: Set<number>;
  onOutcome: (outcome: ProcessingOutcome) => void;
  now?: () => number;
}): void {
  const startedAt = now();
  const scheduleTick = () => {
    const timer = window.setTimeout(() => {
      timers.delete(timer);
      void tick();
    }, PROCESS_POLL_INTERVAL_MS);
    timers.add(timer);
  };
  const tick = async () => {
    if (!isActive()) return;
    if (document.visibilityState === "hidden") {
      scheduleTick();
      return;
    }
    try {
      const items = await api.momentMedia(momentId);
      const status = items.find(
        (candidate) => candidate.id === mediaId,
      )?.upload_status;
      if (status === "completed") {
        onOutcome({ state: "done" });
        return;
      }
      if (status === "failed") {
        onOutcome({ state: "failed", message: PROCESSING_FAILED_MESSAGE });
        return;
      }
    } catch {
      // A failed poll is not a failed file; try again until the timeout.
    }
    if (now() - startedAt > PROCESS_POLL_TIMEOUT_MS) {
      onOutcome({ state: "failed", message: PROCESSING_STALLED_MESSAGE });
      return;
    }
    scheduleTick();
  };
  scheduleTick();
}
