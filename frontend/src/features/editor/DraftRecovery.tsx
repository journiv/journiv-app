import { CloudOff, FileClock, TriangleAlert } from "lucide-react";
import { Button } from "../../components/ui/button";
import { StatusView } from "../../components/journiv/StatusView";
import { formatDateMedium, formatTimeOfDay } from "../../lib/datetime";
import { draftPlainText } from "./draftCanonical";
import type { EditorDraftV1 } from "./draftRepository";
import type { DraftStatus } from "./useLocalDraft";

/**
 * The surfaces that stand between a stored draft and the editor.
 *
 * Both are pane-level states in the `StatusView` shape the rest of the editor
 * already uses for "cannot be loaded" and "cannot be edited here" — a draft
 * decision is the same kind of thing: something to settle before writing, not a
 * banner floating over a live document.
 */

/**
 * When the draft was last written, in the reader's own timezone.
 *
 * `modifiedAt` is a local event with no timezone of its own — unlike a Moment,
 * whose date is rendered where it happened (docs/domain/moments.md) — so the viewer's
 * zone is the right one here.
 */
function writtenWhen(record: EditorDraftV1) {
  const when = new Date(record.modifiedAt);
  if (Number.isNaN(when.getTime())) return null;
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  return `${formatDateMedium(record.modifiedAt)} at ${formatTimeOfDay(record.modifiedAt, timezone)}`;
}

/**
 * Discarding is the one irreversible thing either surface can do — the writing
 * is gone and there is no server copy to fall back on. It always asks first.
 */
function confirmDiscard() {
  return window.confirm(
    "Discard this local draft? The writing kept on this device will be deleted, and it was never saved to your journal.",
  );
}

export function DraftRecoveryPrompt({
  draft,
  serverChanged,
  unresolvedMediaCount,
  isNewEntry,
  onRecover,
  onDiscard,
}: {
  draft: EditorDraftV1;
  serverChanged: boolean;
  unresolvedMediaCount: number;
  isNewEntry: boolean;
  onRecover: () => void;
  onDiscard: () => void;
}) {
  const when = writtenWhen(draft);
  const omittedUploads = draft.omittedTransientUploads ?? 0;
  return (
    <div className="jv-pane-status">
      <StatusView
        icon={<FileClock size={22} />}
        title={
          isNewEntry
            ? "You have writing that was never saved"
            : "You have unsaved changes to this entry"
        }
        description={
          <>
            {when
              ? `Kept on this device on ${when}, and never saved to your journal.`
              : "Kept on this device, and never saved to your journal."}
            {serverChanged && (
              <span className="jv-draft-warning" role="alert">
                <TriangleAlert aria-hidden="true" size={15} />
                This entry has also changed somewhere else since then.
                Recovering replaces that newer version — the two are not
                combined.
              </span>
            )}
            {unresolvedMediaCount > 0 && (
              <span className="jv-draft-warning" role="alert">
                <TriangleAlert aria-hidden="true" size={15} />
                {unresolvedMediaCount === 1
                  ? "One attachment is no longer available and will not come back."
                  : `${unresolvedMediaCount} attachments are no longer available and will not come back.`}
              </span>
            )}
            {omittedUploads > 0 && (
              <span className="jv-draft-warning" role="alert">
                <TriangleAlert aria-hidden="true" size={15} />
                {omittedUploads === 1
                  ? "A file was still uploading and is not part of this draft. Attach it again after recovering."
                  : `${omittedUploads} files were still uploading and are not part of this draft. Attach them again after recovering.`}
              </span>
            )}
          </>
        }
        action={
          <>
            <Button variant="default" onClick={onRecover}>
              Recover
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                if (confirmDiscard()) onDiscard();
              }}
            >
              Discard draft
            </Button>
          </>
        }
      />
    </div>
  );
}

/**
 * A draft with attachments, and no way to reach the server to re-sign them.
 *
 * The editor stays closed on purpose. Opening it would mean opening a document
 * whose photos are missing — and pressing Done on that document would tell the
 * backend to delete them, because a save removes media the Delta dropped
 * (docs/features/editor.md). The writing is shown here instead, so nothing feels lost
 * while the connection is out.
 */
export function DraftMediaUnreachable({
  draft,
  onRetry,
  onDiscard,
}: {
  draft: EditorDraftV1;
  onRetry: () => void;
  onDiscard: () => void;
}) {
  const text = draftPlainText(draft.contentDelta);
  return (
    <div className="jv-pane-status">
      <StatusView
        icon={<CloudOff size={22} />}
        title="Your draft is safe, but its attachments need a connection"
        description={
          <>
            The writing below is stored on this device, shown here as it was
            left. Journiv cannot reach the server to restore the photos or
            recordings in it, so editing stays closed until it can — opening
            without them and saving would remove them from this entry. Try again
            once you are back online.
          </>
        }
        action={
          <>
            <Button variant="default" onClick={onRetry}>
              Try again
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                if (confirmDiscard()) onDiscard();
              }}
            >
              Discard draft
            </Button>
          </>
        }
      />
      {/* A rendering of the stored text, not an editing surface — and a sibling
          of the status rather than part of its description, because a scrollable
          region has to be a real landmark and cannot live inside a <p>. */}
      {text && (
        <section className="jv-draft-excerpt" aria-label="Your stored draft">
          <p className="jv-draft-excerpt__text">{text}</p>
        </section>
      )}
    </div>
  );
}

/**
 * The quiet line that replaced "Journiv does not autosave yet".
 *
 * It sits where that notice sat — below the entry header, visible at every
 * width, unlike the `PageBar` save status which the journal selector hides on
 * compact layouts. It must never overstate what happened: `Saved locally` is
 * set only once a write has actually landed, and a browser that will not store
 * anything says so rather than staying quiet.
 */
export function LocalDraftStatus({
  status,
  omittedTransientUploads,
}: {
  status: DraftStatus;
  omittedTransientUploads: number;
}) {
  const failure =
    status === "failed"
      ? "Journiv couldn’t keep a local copy of this writing. Press Done before leaving this page."
      : status === "unavailable"
        ? "This browser won’t keep a local copy. Press Done before leaving this page."
        : status === "unsupported"
          ? // Nothing was stored, and the line must not imply otherwise. This
            // entry holds something a draft cannot represent, and a partial
            // copy would lose it on recovery.
            "Journiv can’t keep a local copy of this entry — it contains something this editor cannot store safely. Press Done before leaving this page."
          : null;

  return (
    <>
      <p
        className="jv-caption jv-editor__notice"
        role={failure ? "alert" : status === "idle" ? "note" : "status"}
      >
        {failure ??
          (status === "saving"
            ? "Saving locally…"
            : status === "saved"
              ? "Saved locally · not in your journal yet"
              : "Saved on this device as you write. Press Done to save it to your journal.")}
      </p>
      {status === "saved" && omittedTransientUploads > 0 && (
        <p className="jv-editor__error" role="alert">
          {omittedTransientUploads === 1
            ? "A file is still uploading and is not in the local copy. If you reload before it finishes, attach it again."
            : `${omittedTransientUploads} files are still uploading and are not in the local copy. If you reload before they finish, attach them again.`}
        </p>
      )}
    </>
  );
}
