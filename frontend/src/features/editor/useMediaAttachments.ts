import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api/client/api";
import type { MomentMediaResponse } from "../../api/generated/types.gen";
import { uuid } from "../../lib/uuid";
import type { InlineMediaKind } from "./deltaProfile";
import { pollMediaProcessing } from "./mediaProcessingPoll";
import {
  MediaUploadError,
  runWithConcurrency,
  uploadErrorMessage,
  uploadMedia,
  type UploadHandle,
} from "./mediaUpload";
import type { QuillSurfaceHandle } from "./QuillSurface";
import { registerPlaceholder } from "./uploadPlaceholder";

export type Attachment = {
  uploadId: string;
  file: File;
  kind: InlineMediaKind;
  state: "uploading" | "processing" | "done" | "failed";
  message?: string;
  mediaId?: string;
  /**
   * Set only while `state` is `"failed"` and the item is already placed
   * (`placed.current.has(uploadId)`): which of the two ways a placed item
   * fails, so retry can tell them apart without parsing `message`.
   * `"server"` — the backend recorded a definitive processing failure;
   * there is no "reprocess this row" request, so retry re-uploads.
   * `"stalled"` — the poll window elapsed with no terminal state; retry
   * just resumes polling, since the item may still finish.
   */
  failureReason?: "server" | "stalled";
};

function kindForFile(file: File): InlineMediaKind {
  if (file.type.startsWith("video/")) return "video";
  if (file.type.startsWith("audio/")) return "audio";
  return "image";
}

/**
 * Attaching media while writing.
 *
 *   capture caret -> ensure server identity -> placeholder -> upload
 *   -> swap for a durable reference -> poll until processed
 *
 * The upload id is the thread through all of it. When an upload finishes, the
 * placeholder is looked up in the LIVE document: if the user removed it, or
 * undid it while the bytes were in flight, the media is deleted instead of
 * being reinserted. Resurrecting something the user took out is the one failure
 * this design exists to prevent.
 */
export function useMediaAttachments({
  surfaceRef,
  ensureDraft,
  onDirty,
  onMediaAdded,
}: {
  surfaceRef: React.RefObject<QuillSurfaceHandle | null>;
  ensureDraft: () => Promise<{ momentId: string } | null>;
  onDirty: () => void;
  /** Lets the editor track media introduced by this session, for cancel. */
  onMediaAdded: (mediaId: string) => void;
}) {
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [error, setError] = useState("");
  const handles = useRef(new Map<string, UploadHandle>());
  const timers = useRef(new Set<number>());
  /** Upload ids whose media is already in the document (placeholder swapped). */
  const placed = useRef(new Set<string>());
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      for (const handle of handles.current.values()) handle.abort();
      handles.current.clear();
      for (const timer of timers.current) window.clearTimeout(timer);
      timers.current.clear();
      placed.current.clear();
    };
  }, []);

  const patch = useCallback(
    (uploadId: string, changes: Partial<Attachment>) => {
      if (!mounted.current) return;
      setAttachments((current) =>
        current.map((item) =>
          item.uploadId === uploadId ? { ...item, ...changes } : item,
        ),
      );
    },
    [],
  );

  /**
   * Uploads return before the worker has produced dimensions and thumbnails.
   * The shared poll (`mediaProcessingPoll`) stops at a terminal state, pauses
   * while the page is hidden, and reports a stalled file as failed rather than
   * a false success — a stuck upload must reach the writer.
   */
  const pollUntilProcessed = useCallback(
    (uploadId: string, momentId: string, mediaId: string) => {
      pollMediaProcessing({
        momentId,
        mediaId,
        isActive: () => mounted.current,
        timers: timers.current,
        onOutcome: (outcome) =>
          patch(
            uploadId,
            outcome.state === "done"
              ? { state: "done", message: undefined, failureReason: undefined }
              : {
                  state: "failed",
                  message: outcome.message,
                  failureReason: outcome.reason,
                },
          ),
      });
    },
    [patch],
  );

  const runUpload = useCallback(
    async (attachment: Attachment, momentId: string) => {
      const { uploadId, file, kind } = attachment;
      const handle = uploadMedia({
        file,
        momentId,
        onProgress: (fraction) =>
          surfaceRef.current?.setPlaceholderState(
            uploadId,
            "uploading",
            fraction,
          ),
      });
      handles.current.set(uploadId, handle);

      let media: MomentMediaResponse;
      try {
        media = await handle.promise;
      } catch (error) {
        handles.current.delete(uploadId);
        if (error instanceof MediaUploadError && error.kind === "aborted") {
          // Intentional: the placeholder is already gone. Stay quiet.
          setAttachments((current) =>
            current.filter((item) => item.uploadId !== uploadId),
          );
          return;
        }
        surfaceRef.current?.setPlaceholderState(uploadId, "failed");
        patch(uploadId, {
          state: "failed",
          message: uploadErrorMessage(error),
        });
        return;
      }
      handles.current.delete(uploadId);
      patch(uploadId, { mediaId: media.id });

      // THE RACE CHECK. If the placeholder is gone the user does not want this
      // media, so remove what we just uploaded rather than forcing it back in.
      // Exception: a retry of a file that already made it into the document
      // (its processing failed or stalled) has no placeholder left and must be
      // kept, not deleted.
      const source = media.signed_url;
      const replaced =
        Boolean(source) &&
        (surfaceRef.current?.replacePlaceholder(uploadId, kind, source ?? "") ??
          false);
      if (replaced) {
        placed.current.add(uploadId);
      } else if (!placed.current.has(uploadId)) {
        setAttachments((current) =>
          current.filter((item) => item.uploadId !== uploadId),
        );
        await api.deleteMedia(media.id).catch(() => undefined);
        return;
      }

      onMediaAdded(media.id);
      onDirty();
      if (media.upload_status === "completed") {
        patch(uploadId, { state: "done", message: undefined });
        return;
      }
      patch(uploadId, { state: "processing" });
      pollUntilProcessed(uploadId, momentId, media.id);
    },
    [onDirty, onMediaAdded, patch, pollUntilProcessed, surfaceRef],
  );

  const attach = useCallback(
    async (files: File[], atIndex?: number) => {
      const surface = surfaceRef.current;
      if (!surface || !files.length) return;
      setError("");

      const queued: Attachment[] = [];
      try {
        // Captured BEFORE anything can steal focus — the file picker
        // backgrounds the page on mobile and the selection does not survive it.
        // A drop supplies its own position instead.
        const caret = atIndex ?? surface.getSelectionIndex();

        const draft = await ensureDraft();
        if (!draft) return;

        for (const file of files) {
          queued.push({
            uploadId: uuid(),
            file,
            kind: kindForFile(file),
            state: "uploading",
          });
        }

        // Placeholders go in first, in selection order, so the writing shows
        // where each file will land before any byte is sent.
        let index = caret;
        for (const [position, attachment] of queued.entries()) {
          const preview =
            attachment.kind === "image"
              ? { objectUrl: URL.createObjectURL(attachment.file) }
              : {};
          registerPlaceholder(attachment.uploadId, {
            kind: attachment.kind,
            fileName: attachment.file.name,
            ...preview,
          });
          surface.insertPlaceholder(index, attachment.uploadId);
          // The caret now sits after the placeholder, which is where the next
          // file belongs. Only ask when there is a next one.
          if (position < queued.length - 1) index = surface.getSelectionIndex();
        }
        setAttachments((current) => [...current, ...queued]);
        onDirty();

        await runWithConcurrency(
          queued.map(
            (attachment) => () => runUpload(attachment, draft.momentId),
          ),
        );
      } catch {
        // An attach must never fail silently. Anything unexpected here — a
        // missing browser API, a rejected draft — has to reach the writer, and
        // any placeholders already inserted have to come back out.
        for (const attachment of queued)
          surface.removePlaceholder(attachment.uploadId);
        setAttachments((current) =>
          current.filter(
            (item) => !queued.some((q) => q.uploadId === item.uploadId),
          ),
        );
        setError("Could not add that media. Try again.");
      }
    },
    [ensureDraft, onDirty, runUpload, surfaceRef],
  );

  const retry = useCallback(
    async (uploadId: string) => {
      const attachment = attachments.find((item) => item.uploadId === uploadId);
      const draft = await ensureDraft();
      if (!attachment || !draft) return;
      // A file that already reached the document (processing failed/stalled) is
      // being re-processed, not re-inserted — it must not block saving.
      const reprocessing = placed.current.has(uploadId);
      if (!reprocessing) {
        patch(uploadId, { state: "uploading", message: undefined });
        surfaceRef.current?.setPlaceholderState(uploadId, "uploading");
        await runUpload(attachment, draft.momentId);
        return;
      }

      // A placed item's retry means one of two different things depending on
      // why it failed: a stalled poll just needs to keep waiting, while a
      // definitive server-side failure has no "reprocess this row" request to
      // make — uploading always creates a new row — so its embed is removed
      // and a placeholder reinserted at the same spot for a fresh upload to
      // swap back in, the same way the first upload did.
      if (attachment.mediaId && attachment.failureReason === "stalled") {
        patch(uploadId, { state: "processing", message: undefined });
        pollUntilProcessed(uploadId, draft.momentId, attachment.mediaId);
        return;
      }
      if (attachment.mediaId) {
        const index = surfaceRef.current?.removeEmbedForMediaId(
          attachment.mediaId,
        );
        // The fresh upload creates a new row, so the failed one it replaces
        // is deleted here; nothing else would ever collect it.
        void api.deleteMedia(attachment.mediaId).catch(() => undefined);
        patch(uploadId, { mediaId: undefined });
        // No longer placed either way. If the embed was already gone there is
        // no placeholder for the new upload to land in, and the race check
        // deletes that upload instead of keeping a row nothing references.
        placed.current.delete(uploadId);
        if (index !== null && index !== undefined) {
          const preview =
            attachment.kind === "image"
              ? { objectUrl: URL.createObjectURL(attachment.file) }
              : {};
          registerPlaceholder(uploadId, {
            kind: attachment.kind,
            fileName: attachment.file.name,
            ...preview,
          });
          surfaceRef.current?.insertPlaceholder(index, uploadId);
          onDirty();
        }
      }
      // A durable embed should always have a media id; a missing one (state
      // from an older session) also falls through to a fresh upload.
      patch(uploadId, { state: "uploading", message: undefined });
      await runUpload(attachment, draft.momentId);
    },
    [
      attachments,
      ensureDraft,
      onDirty,
      patch,
      pollUntilProcessed,
      runUpload,
      surfaceRef,
    ],
  );

  const cancel = useCallback(
    (
      uploadId: string,
      options: {
        /**
         * True for the "leave without saving" sweep, which aborts anything
         * still uploading but must leave an already-placed item exactly
         * alone: the Moment keeps what was actually attached, and touching
         * the document here would mark it dirty and re-arm the local draft
         * this same flow just explicitly discarded (`useLocalDraft`'s
         * `retired` latch), reviving a draft the user just discarded.
         */
        keepPlacedMedia?: boolean;
      } = {},
    ) => {
      handles.current.get(uploadId)?.abort();
      // A placed item has no placeholder left to remove — its real embed is
      // in the document, and only removing that embed (rather than leaving
      // it as a broken image with the notice merely gone) actually removes
      // it. Its row is deleted too: it was created in this session, and the
      // save's orphan cleanup only collects media the previously saved
      // document referenced, so an unsaved one would otherwise stay on the
      // Moment as an "unavailable" attachment.
      const attachment = attachments.find((item) => item.uploadId === uploadId);
      if (placed.current.has(uploadId)) {
        if (!options.keepPlacedMedia && attachment?.mediaId) {
          const removed = surfaceRef.current?.removeEmbedForMediaId(
            attachment.mediaId,
          );
          if (removed !== null && removed !== undefined) onDirty();
          placed.current.delete(uploadId);
          void api.deleteMedia(attachment.mediaId).catch(() => undefined);
        }
      } else {
        surfaceRef.current?.removePlaceholder(uploadId);
      }
      setAttachments((current) =>
        current.filter((item) => item.uploadId !== uploadId),
      );
    },
    [attachments, onDirty, surfaceRef],
  );

  // Only the upload phase blocks saving. Once a placeholder has been swapped
  // for a durable reference the document is correct, and server-side
  // processing is something the reader already renders a state for — making
  // the writer wait up to a minute for a thumbnail would be absurd.
  const pending = attachments.filter(
    (item) => item.state === "uploading",
  ).length;
  const processing = attachments.filter(
    (item) => item.state === "processing",
  ).length;
  const failed = attachments.filter((item) => item.state === "failed");

  return {
    attachments,
    attach,
    retry,
    cancel,
    pending,
    processing,
    failed,
    error,
  };
}
