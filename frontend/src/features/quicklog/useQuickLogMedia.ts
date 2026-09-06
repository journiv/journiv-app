import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api/client/api";
import { uuid } from "../../lib/uuid";
import {
  MediaUploadError,
  runWithConcurrency,
  type UploadHandle,
  uploadErrorMessage,
  uploadMedia,
} from "../editor/mediaUpload";

/**
 * Media attachment for the Quick Log sheet.
 *
 * The editor's `useMediaAttachments` is bound to the Quill document — caret
 * capture, placeholder blots, undo races. Quick Log has no document, so this is
 * the smaller shape: a local list with object-URL previews and per-file
 * progress, uploading through the **same** `mediaUpload.ts` helper
 * (`uploadMedia` + `runWithConcurrency`) so there is one upload transport in the
 * app (docs/features/editor.md "Attachments").
 *
 * Uploading needs a `moment_id`, so the first `attach` call is what forces the
 * Quick Log moment into existence via `ensureMoment`.
 */
export type QuickLogMediaKind = "image" | "video" | "audio";

export type QuickLogMediaItem = {
  uploadId: string;
  file: File;
  kind: QuickLogMediaKind;
  /** Local preview for image/video; undefined for audio. */
  objectUrl?: string;
  status: "uploading" | "done" | "failed";
  /** 0..1, or undefined when the browser cannot report real progress. */
  progress?: number;
  message?: string;
  /** Server media id once uploaded — used to delete on remove. */
  mediaId?: string;
};

function kindForFile(file: File): QuickLogMediaKind {
  if (file.type.startsWith("video/")) return "video";
  if (file.type.startsWith("audio/")) return "audio";
  return "image";
}

export function useQuickLogMedia({
  ensureMoment,
  onChange,
}: {
  /** Resolves the moment id, creating the row if needed. */
  ensureMoment: () => Promise<string | null>;
  /** Fired whenever the item set changes, so the sheet can re-evaluate "has
   *  the user added anything meaningful yet?". */
  onChange?: () => void;
}) {
  const [items, setItems] = useState<QuickLogMediaItem[]>([]);
  const [error, setError] = useState("");
  const handles = useRef(new Map<string, UploadHandle>());
  const uploading = useRef(new Set<string>());
  const removed = useRef(new Set<string>());
  const cancellationGeneration = useRef(0);
  const objectUrls = useRef(new Set<string>());
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      for (const uploadId of uploading.current) removed.current.add(uploadId);
      for (const handle of handles.current.values()) handle.abort();
      handles.current.clear();
      for (const url of objectUrls.current) URL.revokeObjectURL(url);
      objectUrls.current.clear();
    };
  }, []);

  const patch = useCallback(
    (uploadId: string, changes: Partial<QuickLogMediaItem>) => {
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
    setItems((current) => {
      const target = current.find((item) => item.uploadId === uploadId);
      if (target?.objectUrl) {
        URL.revokeObjectURL(target.objectUrl);
        objectUrls.current.delete(target.objectUrl);
      }
      return current.filter((item) => item.uploadId !== uploadId);
    });
  }, []);

  const runUpload = useCallback(
    async (item: QuickLogMediaItem, momentId: string) => {
      if (removed.current.has(item.uploadId)) {
        uploading.current.delete(item.uploadId);
        return;
      }
      const handle = uploadMedia({
        file: item.file,
        momentId,
        onProgress: (fraction) => patch(item.uploadId, { progress: fraction }),
      });
      handles.current.set(item.uploadId, handle);
      try {
        const media = await handle.promise;
        handles.current.delete(item.uploadId);
        if (removed.current.has(item.uploadId)) {
          void api.deleteMedia(media.id).catch(() => undefined);
          return;
        }
        patch(item.uploadId, {
          status: "done",
          mediaId: media.id,
          message: undefined,
          progress: 1,
        });
        onChange?.();
      } catch (caught) {
        handles.current.delete(item.uploadId);
        if (caught instanceof MediaUploadError && caught.kind === "aborted") {
          if (!removed.current.has(item.uploadId)) drop(item.uploadId);
          return;
        }
        if (removed.current.has(item.uploadId)) return;
        patch(item.uploadId, {
          status: "failed",
          message: uploadErrorMessage(caught),
        });
      } finally {
        uploading.current.delete(item.uploadId);
      }
    },
    [drop, onChange, patch],
  );

  const attach = useCallback(
    async (files: File[]) => {
      if (!files.length) return;
      setError("");
      const generation = cancellationGeneration.current;
      const momentId = await ensureMoment();
      if (generation !== cancellationGeneration.current) return;
      if (!momentId) {
        setError("Couldn't prepare this moment for media. Try again.");
        return;
      }
      const queued: QuickLogMediaItem[] = files.map((file) => {
        const kind = kindForFile(file);
        const objectUrl =
          kind === "audio" ? undefined : URL.createObjectURL(file);
        if (objectUrl) objectUrls.current.add(objectUrl);
        return { uploadId: uuid(), file, kind, objectUrl, status: "uploading" };
      });
      for (const item of queued) uploading.current.add(item.uploadId);
      setItems((current) => [...current, ...queued]);
      onChange?.();
      await runWithConcurrency(
        queued.map((item) => () => runUpload(item, momentId)),
      );
    },
    [ensureMoment, onChange, runUpload],
  );

  const retry = useCallback(
    async (uploadId: string) => {
      const item = items.find((entry) => entry.uploadId === uploadId);
      if (!item) return;
      removed.current.delete(uploadId);
      uploading.current.add(uploadId);
      const momentId = await ensureMoment();
      if (!momentId) {
        uploading.current.delete(uploadId);
        return;
      }
      patch(uploadId, { status: "uploading", message: undefined, progress: 0 });
      await runUpload(item, momentId);
    },
    [ensureMoment, items, patch, runUpload],
  );

  const remove = useCallback(
    (uploadId: string) => {
      const item = items.find((entry) => entry.uploadId === uploadId);
      if (!item) return;
      removed.current.add(uploadId);
      drop(uploadId);
      handles.current.get(uploadId)?.abort();
      if (item.status === "done" && item.mediaId) {
        void api.deleteMedia(item.mediaId).catch(() => undefined);
      }
      onChange?.();
    },
    [drop, items, onChange],
  );

  const cancelPending = useCallback(async () => {
    cancellationGeneration.current += 1;
    const pending = [...uploading.current];
    for (const uploadId of pending) removed.current.add(uploadId);
    const settlements = [...handles.current.values()].map((handle) =>
      handle.promise.catch(() => undefined),
    );
    for (const handle of handles.current.values()) handle.abort();
    await Promise.all(settlements);
  }, []);

  const pending = items.filter((item) => item.status === "uploading").length;
  const failed = items.filter((item) => item.status === "failed");
  /** Non-failed items — the user has expressed intent to attach these. */
  const count = items.filter((item) => item.status !== "failed").length;

  return {
    items,
    attach,
    retry,
    remove,
    cancelPending,
    pending,
    failed,
    count,
    error,
  };
}
