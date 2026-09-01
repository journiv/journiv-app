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
              ? { state: "done", message: undefined }
              : { state: "failed", message: outcome.message },
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
      patch(uploadId, {
        state: reprocessing ? "processing" : "uploading",
        message: undefined,
      });
      if (!reprocessing) {
        surfaceRef.current?.setPlaceholderState(uploadId, "uploading");
        await runUpload(attachment, draft.momentId);
        return;
      }
      if (attachment.mediaId) {
        pollUntilProcessed(uploadId, draft.momentId, attachment.mediaId);
      } else {
        // A durable embed should always have a media id. Fall back to upload
        // only if state from an older session lacks it.
        await runUpload(attachment, draft.momentId);
      }
    },
    [
      attachments,
      ensureDraft,
      patch,
      pollUntilProcessed,
      runUpload,
      surfaceRef,
    ],
  );

  const cancel = useCallback(
    (uploadId: string) => {
      handles.current.get(uploadId)?.abort();
      surfaceRef.current?.removePlaceholder(uploadId);
      setAttachments((current) =>
        current.filter((item) => item.uploadId !== uploadId),
      );
    },
    [surfaceRef],
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
