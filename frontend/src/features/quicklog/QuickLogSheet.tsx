import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { ChevronRight, ImagePlus, Loader2, RotateCw, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api/client/api";
import { queryKeys } from "../../api/query/keys";
import { mediaFormatsQuery, momentQuery } from "../../api/query/options";
import { AppAdaptiveDialog } from "../../components/journiv/AppAdaptiveDialog";
import { AppConfirmDialog } from "../../components/journiv/AppConfirmDialog";
import { MomentDetailsPanel } from "../../components/journiv/MomentDetailsPanel";
import { Button } from "../../components/ui/button";
import { IconButton } from "../../components/ui/icon-button";
import { Textarea } from "../../components/ui/textarea";
import { browserTimeZone } from "../../lib/datetime";
import { cx } from "../../lib/cx";
import { useCompactViewport } from "../../lib/useCompactViewport";
import { acceptAttribute } from "../editor/mediaUpload";
import { useQuickLogMedia } from "./useQuickLogMedia";
import { useQuickLogMoment } from "./useQuickLogMoment";
import "./quicklog.css";

/** `moment.note` is capped at 500 characters server-side (app/schemas/moment.py). */
const NOTE_MAX = 500;

/**
 * Quick Log — a lightweight moment capture (docs/features/quicklog.md).
 *
 * Composition is the existing "substantial form" overlay: `AppAdaptiveDialog`
 * gives a bottom Drawer at ≤860px and a centred Dialog above it (DESIGN.md,
 * "Adaptive overlays"). Mood is surfaced at the top; location, weather, people
 * and tags sit in an "Add details" disclosure. Both reuse the shared
 * `MomentDetailsPanel` — every write goes straight to a real Moment, created on
 * first intent (`useQuickLogMoment`), so "Continue as full entry" is a lossless
 * hand-off to `/timeline/$momentId/edit`.
 *
 * The parent (`AppShell`) remounts this with a fresh `key` on every open, so all
 * state here starts clean and `useQuickLogMoment` owns exactly one session.
 */
export function QuickLogSheet({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  // Mood is the intended first interaction, so nothing here autofocuses — which
  // also keeps the compact sheet from summoning the keyboard on open (DESIGN.md).
  const compact = useCompactViewport();

  // "Now", fixed for the life of this capture. Quick Log has no date control —
  // backdating is a full-editor affordance (docs/features/editor.md).
  const loggedAt = useMemo(
    () => ({ utc: new Date().toISOString(), timezone: browserTimeZone() }),
    [],
  );

  const quickLog = useQuickLogMoment({
    loggedAtUtc: loggedAt.utc,
    loggedTimezone: loggedAt.timezone,
  });
  const momentId = quickLog.momentId;

  // The live Moment behind this capture — feeds the details panel's current
  // values and the "is there anything worth keeping?" check.
  const liveMoment = useQuery({
    ...momentQuery(momentId ?? ""),
    enabled: Boolean(momentId),
  });

  const formats = useQuery(mediaFormatsQuery());
  const accept = acceptAttribute(formats.data);

  const [note, setNote] = useState("");
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [error, setError] = useState("");
  const [discardOpen, setDiscardOpen] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const [hasUnsyncedDetails, setHasUnsyncedDetails] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const ensureMomentId = useCallback(async () => {
    try {
      return await quickLog.ensure();
    } catch {
      setError(
        "Couldn't prepare this moment. Check your connection and retry.",
      );
      return null;
    }
  }, [quickLog]);

  const media = useQuickLogMedia({
    ensureMoment: ensureMomentId,
    onChange: () => setError(""),
  });

  const current = liveMoment.data;
  useEffect(() => {
    if (current) setHasUnsyncedDetails(false);
  }, [current]);

  const onDetailsSaved = useCallback(
    (savedId: string) => {
      setError("");
      // A newly-created Moment has no query data until this invalidation
      // completes. Keep the successful detail write in local session state so
      // Cancel cannot delete it as an apparently empty capture in that gap.
      if (!current) setHasUnsyncedDetails(true);
      void queryClient.invalidateQueries({
        queryKey: queryKeys.moment(savedId),
      });
      void queryClient.invalidateQueries({ queryKey: queryKeys.allMoments });
    },
    [current, queryClient],
  );

  // "Meaningful content" — matches the domain rule that a Moment is meaningful
  // when it has any of these (docs/domain/moments.md). Auto-fetched weather on
  // its own does not count.
  const hasContent =
    note.trim().length > 0 ||
    Boolean(current?.primary_mood_id) ||
    (current?.people?.length ?? 0) > 0 ||
    (current?.tags?.length ?? 0) > 0 ||
    Boolean(current?.location_json) ||
    hasUnsyncedDetails ||
    media.count > 0;

  const commit = useMutation({
    mutationFn: async () => {
      const id = await quickLog.ensure();
      const trimmed = note.trim();
      if (trimmed) await api.updateMoment(id, { note: trimmed });
      return id;
    },
    onSuccess: async (id) => {
      quickLog.adopt();
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.allMoments }),
        queryClient.invalidateQueries({ queryKey: queryKeys.moment(id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.insights }),
        queryClient.invalidateQueries({ queryKey: queryKeys.journals }),
      ]);
      onOpenChange(false);
    },
    onError: () =>
      setError("This moment couldn't be saved. Your details are still here."),
  });

  const continueFull = useMutation({
    mutationFn: async () => {
      const id = await quickLog.ensure();
      const trimmed = note.trim();
      // Persist the note before leaving, so the editor can seed it and a failed
      // navigation never loses it (docs/features/quicklog.md).
      if (trimmed) await api.updateMoment(id, { note: trimmed });
      return { id, hadNote: trimmed.length > 0 };
    },
    onSuccess: async ({ id, hadNote }) => {
      quickLog.adopt();
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.moment(id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.allMoments }),
      ]);
      onOpenChange(false);
      void navigate({
        to: "/timeline/$momentId/edit",
        params: { momentId: id },
        search: { q: "", seedNote: hadNote ? true : undefined },
      });
    },
    onError: () =>
      setError("Couldn't open the full editor. Your details are saved."),
  });

  const busy = commit.isPending || continueFull.isPending || discarding;
  const ready = hasContent && !busy && media.pending === 0;

  const finalizeDiscard = useCallback(async () => {
    if (discarding) return;
    setDiscarding(true);
    // Media the user actually uploaded is kept as a media-only Moment — the same
    // rule the editor's Cancel uses (docs/features/editor.md). Everything else,
    // including the unsaved note, is dropped.
    try {
      await media.cancelPending();
      const keepMedia = media.items.some((item) => item.status === "done");
      await quickLog.discard(keepMedia);
      if (keepMedia) {
        await queryClient.invalidateQueries({ queryKey: queryKeys.allMoments });
      }
      setDiscardOpen(false);
      onOpenChange(false);
    } finally {
      setDiscarding(false);
    }
  }, [
    discarding,
    media.cancelPending,
    media.items,
    quickLog,
    queryClient,
    onOpenChange,
  ]);

  const requestClose = useCallback(
    (next: boolean) => {
      if (next) {
        onOpenChange(true);
        return;
      }
      if (busy) return;
      if (hasContent) {
        setDiscardOpen(true);
        return;
      }
      // Nothing worth keeping — but a bare row may still exist (a mood picked
      // then cleared), so route through discard to delete it.
      void finalizeDiscard();
    },
    [busy, hasContent, finalizeDiscard, onOpenChange],
  );

  const atLimit = note.length >= NOTE_MAX;

  const footer = (
    <>
      {!compact && (
        <Button
          variant="ghost"
          onClick={() => requestClose(false)}
          disabled={busy}
        >
          Cancel
        </Button>
      )}
      <Button
        variant="secondary"
        onClick={() => continueFull.mutate()}
        disabled={!ready}
      >
        {continueFull.isPending ? "Opening…" : "Continue as full entry"}
      </Button>
      <Button
        variant="default"
        onClick={() => commit.mutate()}
        disabled={!ready}
      >
        {commit.isPending ? "Saving…" : "Log moment"}
      </Button>
    </>
  );

  return (
    <>
      <AppAdaptiveDialog
        open={open}
        onOpenChange={requestClose}
        title="Quick log"
        description="Capture a moment now. Add the rest whenever you like."
        size="md"
        dismissible={!busy}
        footer={footer}
      >
        <div className="jv-quicklog">
          {error && (
            <p className="jv-quicklog__error" role="alert">
              {error}
            </p>
          )}

          <MomentDetailsPanel
            sections={["mood"]}
            moment={current}
            ensureMomentId={ensureMomentId}
            onSaved={onDetailsSaved}
            loggedAtUtc={loggedAt.utc}
            loggedTimezone={loggedAt.timezone}
            disabled={busy}
          />

          <div className="jv-quicklog__note">
            <div className="jv-quicklog__note-head">
              <label className="jv-label" htmlFor="quicklog-note">
                Note
              </label>
              <span
                className={cx(
                  "jv-caption",
                  atLimit && "jv-quicklog__count--limit",
                )}
                aria-live="polite"
              >
                {note.length}/{NOTE_MAX}
              </span>
            </div>
            <Textarea
              id="quicklog-note"
              value={note}
              onChange={(event) =>
                setNote(event.target.value.slice(0, NOTE_MAX))
              }
              maxLength={NOTE_MAX}
              rows={3}
              placeholder="Jot down what's happening…"
              autoComplete="off"
              disabled={busy}
            />
            {atLimit && (
              <p className="jv-caption">
                Need more room? Continue as full entry.
              </p>
            )}
          </div>

          <div className="jv-quicklog__media">
            <div className="jv-quicklog__media-head">
              <span className="jv-label">Photos and video</span>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  setError("");
                  fileInputRef.current?.click();
                }}
                disabled={busy}
              >
                <ImagePlus aria-hidden="true" size={15} />
                Add media
              </Button>
            </div>
            {media.items.length > 0 && (
              <ul className="jv-quicklog__media-grid">
                {media.items.map((item) => (
                  <li
                    key={item.uploadId}
                    className={cx(
                      "jv-quicklog__media-item",
                      item.status === "failed" &&
                        "jv-quicklog__media-item--failed",
                    )}
                  >
                    {item.objectUrl ? (
                      item.kind === "video" ? (
                        <video
                          className="jv-quicklog__media-thumb"
                          src={item.objectUrl}
                          width={72}
                          height={72}
                          muted
                          playsInline
                        />
                      ) : (
                        <img
                          className="jv-quicklog__media-thumb"
                          src={item.objectUrl}
                          width={72}
                          height={72}
                          alt={item.file.name}
                        />
                      )
                    ) : (
                      <span
                        className="jv-quicklog__media-thumb jv-quicklog__media-thumb--audio"
                        aria-hidden="true"
                      />
                    )}
                    {item.status === "uploading" && (
                      <span className="jv-quicklog__media-status" role="status">
                        <Loader2
                          className="jv-spin"
                          aria-hidden="true"
                          size={16}
                        />
                        <span className="sr-only">
                          Uploading {item.file.name}
                        </span>
                      </span>
                    )}
                    {item.status === "failed" && (
                      <button
                        type="button"
                        className="jv-quicklog__media-status jv-quicklog__media-retry"
                        onClick={() => media.retry(item.uploadId)}
                        title={item.message ?? "Upload failed. Retry"}
                      >
                        <RotateCw aria-hidden="true" size={15} />
                        <span className="sr-only">
                          Retry upload for {item.file.name}
                        </span>
                      </button>
                    )}
                    <IconButton
                      label={`Remove ${item.file.name}`}
                      size="sm"
                      className="jv-quicklog__media-remove"
                      onClick={() => media.remove(item.uploadId)}
                      disabled={busy}
                    >
                      <X aria-hidden="true" size={13} />
                    </IconButton>
                  </li>
                ))}
              </ul>
            )}
            {media.error && (
              <p className="jv-details__error" role="alert">
                {media.error}
              </p>
            )}
            <input
              ref={fileInputRef}
              className="sr-only"
              type="file"
              accept={accept}
              multiple
              tabIndex={-1}
              aria-hidden="true"
              onChange={(event) => {
                const files = [...(event.target.files ?? [])];
                event.target.value = "";
                if (files.length) void media.attach(files);
              }}
            />
          </div>

          <details
            className="jv-quicklog__details"
            open={detailsOpen}
            onToggle={(event) =>
              setDetailsOpen((event.target as HTMLDetailsElement).open)
            }
          >
            <summary className="jv-quicklog__disclosure">
              <ChevronRight
                className="jv-quicklog__disclosure-chevron"
                aria-hidden="true"
                size={16}
              />
              <span className="jv-quicklog__disclosure-text">
                <span className="jv-label">Add details</span>
                <span className="jv-caption">
                  location, weather, people, tags
                </span>
              </span>
            </summary>
            <div className="jv-quicklog__details-body">
              <MomentDetailsPanel
                sections={["location", "weather", "people", "tags"]}
                moment={current}
                ensureMomentId={ensureMomentId}
                onSaved={onDetailsSaved}
                loggedAtUtc={loggedAt.utc}
                loggedTimezone={loggedAt.timezone}
                disabled={busy}
              />
            </div>
          </details>
        </div>
      </AppAdaptiveDialog>

      <AppConfirmDialog
        open={discardOpen}
        onOpenChange={setDiscardOpen}
        title="Discard quick log?"
        description={
          media.items.some((item) => item.status === "done")
            ? "The photos you added stay as a moment. The note and anything else is discarded."
            : "This quick log won't be saved."
        }
        confirmLabel="Discard"
        cancelLabel="Keep editing"
        destructive
        onConfirm={finalizeDiscard}
      />
    </>
  );
}
