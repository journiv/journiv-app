import { Loader2, Mic, Square, TriangleAlert, X } from "lucide-react";
import { useState, useSyncExternalStore } from "react";
import { AppConfirmDialog } from "../../components/journiv/AppConfirmDialog";
import { WaveformBars } from "../../components/journiv/media/WaveformBars";
import { Button } from "../../components/ui/button";
import { IconButton } from "../../components/ui/icon-button";
import { formatDuration } from "./dictationFormat";
import type { RecordingSession } from "./recordingRepository";
import type { useDictation } from "./useDictation";
import "./dictation.css";

export type DictationController = ReturnType<typeof useDictation>;

type Confirm =
  | { kind: "recording" }
  | { kind: "staged"; sessionId: string }
  | { kind: "failed"; uploadId: string };

/**
 * Everything dictation has to say, in one non-scrolling region under the
 * PageBar: the live recording, an upload in progress or failed, a recording
 * left over from an earlier session, and errors.
 *
 * It is a flex sibling of the scroll owner like PageBar and the toolbar — never
 * a sticky layer over the prose — so the Stop control is on screen however far
 * the writer has scrolled, and at the compact width it sits above the prose
 * rather than fighting the keyboard-docked formatting bar. It renders nothing
 * (and takes no space) while there is nothing to say.
 *
 * See docs/features/editor.md, Voice notes.
 */
export function DictationBar({
  dictation,
}: {
  dictation: DictationController;
}) {
  const [confirm, setConfirm] = useState<Confirm | null>(null);
  const {
    phase,
    recording,
    starting,
    error,
    notice,
    uploads,
    recoverable,
    crashSafe,
  } = dictation;

  const uploading = uploads.items.filter((item) => item.status === "uploading");
  const nothingToShow =
    !recording &&
    !starting &&
    !error &&
    !notice &&
    uploads.items.length === 0 &&
    recoverable.length === 0;

  const confirmCopy = confirm
    ? confirm.kind === "recording"
      ? {
          title: "Discard this voice note?",
          description:
            "The audio you have recorded so far will be deleted. This can’t be undone.",
        }
      : {
          title: "Discard this voice note?",
          description:
            "The voice note kept on this device will be deleted, and it was never added to your journal. This can’t be undone.",
        }
    : null;

  const onConfirm = async () => {
    if (!confirm) return;
    if (confirm.kind === "recording") await dictation.discard();
    else if (confirm.kind === "staged")
      await dictation.discardStaged(confirm.sessionId);
    else await dictation.discardFailed(confirm.uploadId);
    setConfirm(null);
  };

  return (
    <>
      {/* Announced once per change, never per tick. */}
      <p className="sr-only" role="status">
        {phase === "recording"
          ? "Recording"
          : phase === "stopping" || phase === "uploading"
            ? "Adding your voice note to this moment"
            : ""}
      </p>
      {!nothingToShow && (
        <section className="jv-dictation" aria-label="Voice note">
          {starting && <StartingRow onCancel={() => void dictation.stop()} />}

          {recording && (
            <RecordingRow
              dictation={dictation}
              crashSafe={crashSafe}
              onDiscard={() => setConfirm({ kind: "recording" })}
            />
          )}

          {error && (
            <p
              className="jv-dictation__row jv-dictation__row--alert"
              role="alert"
            >
              <TriangleAlert aria-hidden="true" size={16} />
              <span>{error.message}</span>
              <IconButton
                label="Dismiss"
                size="sm"
                onClick={dictation.clearError}
              >
                <X aria-hidden="true" size={15} />
              </IconButton>
            </p>
          )}

          {notice && (
            <p className="jv-dictation__row" role="status">
              <span>{notice}</span>
              <IconButton
                label="Dismiss"
                size="sm"
                onClick={dictation.clearNotice}
              >
                <X aria-hidden="true" size={15} />
              </IconButton>
            </p>
          )}

          {uploading.map((item) => (
            <p key={item.uploadId} className="jv-dictation__row" role="status">
              <Loader2 className="jv-spin" aria-hidden="true" size={16} />
              <span>
                Adding voice note to this moment
                {typeof item.progress === "number" && item.progress > 0
                  ? `… ${Math.round(item.progress * 100)}%`
                  : "…"}
              </span>
            </p>
          ))}

          {uploads.failed.map((item) => (
            <div
              key={item.uploadId}
              className="jv-dictation__row jv-dictation__row--alert"
              role="alert"
            >
              <TriangleAlert aria-hidden="true" size={16} />
              <span>{item.message}</span>
              <span className="jv-dictation__actions">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => void uploads.retry(item.uploadId)}
                >
                  Retry
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    setConfirm({ kind: "failed", uploadId: item.uploadId })
                  }
                >
                  Discard voice note
                </Button>
              </span>
            </div>
          ))}

          {recoverable.map((session) => (
            <div key={session.id} className="jv-dictation__row">
              <Mic aria-hidden="true" size={16} />
              <span>{recoverPrompt(session)}</span>
              <span className="jv-dictation__actions">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => void dictation.recover(session.id)}
                >
                  Recover
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    setConfirm({ kind: "staged", sessionId: session.id })
                  }
                >
                  Discard
                </Button>
              </span>
            </div>
          ))}
        </section>
      )}

      {confirmCopy && (
        <AppConfirmDialog
          open
          onOpenChange={(open) => {
            if (!open) setConfirm(null);
          }}
          title={confirmCopy.title}
          description={confirmCopy.description}
          confirmLabel="Discard voice note"
          cancelLabel={
            confirm?.kind === "recording" ? "Keep recording" : "Keep voice note"
          }
          destructive
          onConfirm={onConfirm}
        />
      )}
    </>
  );
}

/**
 * A start that has not begun recording: the browser's microphone prompt may be
 * open, or staging may be opening. Nothing has been captured, so there is no
 * Stop and nothing to confirm discarding — only the start to abandon.
 */
function StartingRow({ onCancel }: { onCancel: () => void }) {
  return (
    <div className="jv-dictation__row" role="status">
      <Loader2 className="jv-spin" aria-hidden="true" size={16} />
      <span>Waiting for the microphone…</span>
      <span className="jv-dictation__actions">
        <Button variant="outline" size="sm" onClick={onCancel}>
          Cancel recording
        </Button>
      </span>
    </div>
  );
}

function RecordingRow({
  dictation,
  crashSafe,
  onDiscard,
}: {
  dictation: DictationController;
  crashSafe: boolean | null;
  onDiscard: () => void;
}) {
  // Only this row re-renders on the live tick — never the editor page.
  const live = useSyncExternalStore(
    dictation.live.subscribe,
    dictation.live.getSnapshot,
    dictation.live.getSnapshot,
  );
  const stopping = dictation.phase === "stopping";
  return (
    <div className="jv-dictation__row jv-dictation__row--recording">
      <span className="jv-dictation__dot" aria-hidden="true" />
      {/* role="timer" is not announced as it ticks. */}
      <span
        className="jv-dictation__time"
        role="timer"
        aria-label="Recording time"
      >
        {formatDuration(live.elapsedMs)}
      </span>
      <WaveformBars bars={live.bars} className="jv-dictation__meter" />
      <span className="jv-dictation__actions">
        <Button
          variant="secondary"
          size="sm"
          disabled={stopping}
          onClick={() => void dictation.stop()}
        >
          <Square aria-hidden="true" size={13} />
          {stopping ? "Stopping…" : "Stop"}
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={stopping}
          onClick={onDiscard}
        >
          Discard
        </Button>
      </span>
      {live.lowTime && live.remainingMs !== null && (
        <span className="jv-dictation__hint" role="status">
          {live.remainingMs > 0
            ? `About ${Math.max(1, Math.ceil(live.remainingMs / 1000))} seconds left before this server’s upload limit.`
            : "Reached this server’s upload limit."}
        </span>
      )}
      {crashSafe === false && (
        <span className="jv-dictation__hint">
          This browser can’t keep a safety copy while you record. Keep this page
          open until the recording is added.
        </span>
      )}
    </div>
  );
}

function recoverPrompt(session: RecordingSession): string {
  const length =
    session.durationMs > 0 ? ` (${formatDuration(session.durationMs)})` : "";
  const started = new Date(session.startedAt);
  const when = Number.isNaN(started.getTime())
    ? ""
    : ` from ${started.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}`;
  return `Recover unfinished voice note${length}${when}?`;
}
