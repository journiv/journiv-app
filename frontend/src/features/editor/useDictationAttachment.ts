import type { QueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import type { MomentMediaResponse } from "../../api/generated/types.gen";
import { queryKeys } from "../../api/query/keys";
import { uuid } from "../../lib/uuid";
import type { DictationAnchor } from "./dictationFormat";
import {
  MediaUploadError,
  runWithConcurrency,
  type UploadHandle,
  uploadErrorMessage,
  uploadMedia,
} from "./mediaUpload";

/**
 * Attaching a dictation recording to its Moment.
 *
 * This is the **document-free** attachment shape: it uploads through the same
 * `mediaUpload.ts` transport as the editor's inline media
 * (`useMediaAttachments`) and Quick Log (`useQuickLogMedia`), but it never
 * touches the Quill document — no caret capture, no placeholder, no blot. A
 * dictation recording is a Moment attachment shown in the editor tray and the
 * reader gallery; nothing from it reaches the prose. One upload transport in the app, three callers around it
 * (docs/features/editor.md, Voice notes).
 *
 * Nothing here polls. `momentMediaQuery` already polls while an item is pending
 * or processing, but it cannot *start* polling from an empty tray, so a
 * successful upload invalidates the Moment's queries once and the existing poll
 * takes over.
 */
export type DictationUploadItem = {
  uploadId: string;
  file: File;
  status: "uploading" | "failed";
  /** 0..1, or undefined when the browser cannot report real progress. */
  progress?: number;
  message?: string;
  /** The staged session this file was assembled from, if it was staged. */
  sessionId: string | null;
  /** Where in the entry recording started: captured then, kept per media id. */
  anchor: DictationAnchor | null;
};

export type DictationUploaded = {
  media: MomentMediaResponse;
  momentId: string;
  item: DictationUploadItem;
};

const PREPARE_FAILED_MESSAGE =
  "Couldn’t prepare this entry for the voice note. It is kept on this device — try again.";

const TOO_LARGE_MESSAGE =
  "This voice note is larger than this server accepts. It is kept on this device.";

export function useDictationAttachment({
  ensureDraft,
  queryClient,
  onUploaded,
}: {
  /** Resolves the Moment id, creating the draft Moment if there is none yet. */
  ensureDraft: () => Promise<{ momentId: string } | null>;
  queryClient: QueryClient;
  /**
   * The upload succeeded and the recording is now a Moment attachment. The
   * caller deletes the staged copy here — only ever after success.
   */
  onUploaded: (uploaded: DictationUploaded) => void | Promise<void>;
}) {
  const [items, setItems] = useState<DictationUploadItem[]>([]);
  const handles = useRef(new Map<string, UploadHandle>());
  const mounted = useRef(true);
  const cancelled = useRef(false);
  const onUploadedRef = useRef(onUploaded);
  onUploadedRef.current = onUploaded;

  useEffect(() => {
    mounted.current = true;
    cancelled.current = false;
    return () => {
      mounted.current = false;
      cancelled.current = true;
      for (const handle of handles.current.values()) handle.abort();
      handles.current.clear();
    };
  }, []);

  const patch = useCallback(
    (uploadId: string, changes: Partial<DictationUploadItem>) => {
      if (!mounted.current) return;
      setItems((current) =>
        current.map((item) =>
          item.uploadId === uploadId ? { ...item, ...changes } : item,
        ),
      );
    },
    [],
  );

  const drop = useCallback((uploadId: string) => {
    if (!mounted.current) return;
    setItems((current) => current.filter((item) => item.uploadId !== uploadId));
  }, []);

  const runUpload = useCallback(
    async (item: DictationUploadItem, momentId: string) => {
      if (cancelled.current) {
        drop(item.uploadId);
        return;
      }
      try {
        const handle = uploadMedia({
          file: item.file,
          momentId,
          onProgress: (fraction) =>
            patch(item.uploadId, { progress: fraction }),
        });
        handles.current.set(item.uploadId, handle);
        const media = await handle.promise;
        handles.current.delete(item.uploadId);
        // The recording is a Moment attachment now. Its own queries need a
        // single nudge: the tray is gated on the Moment's `media_count`, and
        // the media list may be cached as empty, which the tray poll (it runs
        // only while something is processing) would never leave.
        void queryClient.invalidateQueries({
          queryKey: queryKeys.moment(momentId),
        });
        drop(item.uploadId);
        try {
          await onUploadedRef.current({ media, momentId, item });
        } catch {
          // Cleanup of the staged copy is best effort; the upload itself is done.
        }
      } catch (caught) {
        handles.current.delete(item.uploadId);
        // An abort is the writer leaving; the staged copy stays for recovery.
        if (caught instanceof MediaUploadError && caught.kind === "aborted") {
          drop(item.uploadId);
          return;
        }
        patch(item.uploadId, {
          status: "failed",
          message:
            caught instanceof MediaUploadError && caught.kind === "too-large"
              ? TOO_LARGE_MESSAGE
              : uploadErrorMessage(caught),
        });
      }
    },
    [drop, patch, queryClient],
  );

  const attach = useCallback(
    async (
      file: File,
      meta: { sessionId: string | null; anchor: DictationAnchor | null },
    ) => {
      if (cancelled.current) return false;
      // The item exists before the draft is resolved, so a failure to prepare
      // the entry (no journal chosen yet, offline) leaves a retryable item and
      // the recording is never stranded with nothing on screen to act on.
      const item: DictationUploadItem = {
        uploadId: uuid(),
        file,
        status: "uploading",
        progress: 0,
        sessionId: meta.sessionId,
        anchor: meta.anchor,
      };
      setItems((current) => [...current, item]);
      const draft = await ensureDraft().catch(() => null);
      if (cancelled.current) {
        drop(item.uploadId);
        return false;
      }
      if (!draft) {
        patch(item.uploadId, {
          status: "failed",
          message: PREPARE_FAILED_MESSAGE,
        });
        return false;
      }
      await runWithConcurrency([() => runUpload(item, draft.momentId)]);
      return true;
    },
    [drop, ensureDraft, patch, runUpload],
  );

  const retry = useCallback(
    async (uploadId: string) => {
      const item = items.find((entry) => entry.uploadId === uploadId);
      if (!item || cancelled.current) return;
      const draft = await ensureDraft().catch(() => null);
      if (cancelled.current) {
        drop(uploadId);
        return;
      }
      if (!draft) {
        patch(uploadId, { status: "failed", message: PREPARE_FAILED_MESSAGE });
        return;
      }
      patch(uploadId, { status: "uploading", message: undefined, progress: 0 });
      await runUpload(item, draft.momentId);
    },
    [drop, ensureDraft, items, patch, runUpload],
  );

  /** Stops uploads in flight (leaving the editor). Staged audio is untouched. */
  const cancelAll = useCallback(() => {
    cancelled.current = true;
    for (const handle of handles.current.values()) handle.abort();
  }, []);

  /** Forgets a failed item. The caller decides what happens to the staged copy. */
  const dismiss = useCallback((uploadId: string) => drop(uploadId), [drop]);

  const pending = items.filter((item) => item.status === "uploading").length;
  const failed = items.filter((item) => item.status === "failed");

  return { items, attach, retry, dismiss, cancelAll, pending, failed };
}
