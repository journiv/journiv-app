import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../../api/client/api";
import { ApiError } from "../../../api/client/errors";
import type {
  AssetType,
  IntegrationAssetResponse,
  MomentMediaResponse,
} from "../../../api/generated/types.gen";
import { uuid } from "../../../lib/uuid";
import type { InlineMediaKind } from "../deltaProfile";
import { pollMediaProcessing } from "../mediaProcessingPoll";
import type { QuillSurfaceHandle } from "../QuillSurface";
import { registerPlaceholder } from "../uploadPlaceholder";

const IMPORT_FAILED_MESSAGE =
  "Couldn’t add this item from Immich. Retry, or remove it from the entry.";
const IMPORT_NO_ROW_MESSAGE =
  "Immich didn’t return this item. Retry, or remove it from the entry.";

/** Immich assets the editor can inline. Audio / other are filtered out. */
const PICKABLE: AssetType[] = ["IMAGE", "VIDEO"];

export function isPickableImmichAsset(
  asset: IntegrationAssetResponse,
): boolean {
  return PICKABLE.includes(asset.type);
}

function kindForAssetType(type: AssetType): InlineMediaKind {
  return type === "VIDEO" ? "video" : "image";
}

function importErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 400 || error.status === 401 || error.status === 403)
      return "Immich needs reconnecting in Settings → Integrations.";
    if (error.status === 404) return "This entry is no longer available.";
  }
  return IMPORT_FAILED_MESSAGE;
}

export type ImmichAttachment = {
  uploadId: string;
  asset: IntegrationAssetResponse;
  kind: InlineMediaKind;
  state: "importing" | "processing" | "done" | "failed";
  message?: string;
  mediaId?: string;
};

/**
 * Attaching Immich library assets while writing.
 *
 *   capture caret → ensureDraft() → placeholder(s) → import → durable reference
 *   → poll until processed
 *
 * The pipeline is the device-upload one (`useMediaAttachments`) with the byte
 * upload replaced by a **single** `POST /media/import-from-immich-async` for the
 * whole selection. Each returned media row is matched back to its placeholder
 * by `origin.external_id` (the Immich asset id), so the swap stays unambiguous
 * without N parallel requests — which under SQLite raced on the write lock and
 * left every asset but the first failing. Link-only vs copy is the
 * integration's setting, decided server-side.
 *
 * The race check is identical: a completing import looks for its placeholder in
 * the *live* document. If the writer removed it while the request was in
 * flight, the media is deleted, never reinserted.
 */
export function useImmichAttachments({
  surfaceRef,
  ensureDraft,
  onDirty,
  onMediaAdded,
}: {
  surfaceRef: React.RefObject<QuillSurfaceHandle | null>;
  ensureDraft: () => Promise<{ momentId: string } | null>;
  onDirty: () => void;
  onMediaAdded: (mediaId: string) => void;
}) {
  const [attachments, setAttachments] = useState<ImmichAttachment[]>([]);
  const [error, setError] = useState("");
  const timers = useRef(new Set<number>());
  /** Upload ids whose media is already in the document (placeholder swapped). */
  const placed = useRef(new Set<string>());
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      for (const timer of timers.current) window.clearTimeout(timer);
      timers.current.clear();
      placed.current.clear();
    };
  }, []);

  const patch = useCallback(
    (uploadId: string, changes: Partial<ImmichAttachment>) => {
      if (!mounted.current) return;
      setAttachments((current) =>
        current.map((item) =>
          item.uploadId === uploadId ? { ...item, ...changes } : item,
        ),
      );
    },
    [],
  );

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

  /** Swap one placeholder for the media row the import produced for it. */
  const applyImportedRow = useCallback(
    async (
      attachment: ImmichAttachment,
      media: MomentMediaResponse,
      momentId: string,
    ) => {
      const { uploadId, kind } = attachment;
      patch(uploadId, { mediaId: media.id });

      // THE RACE CHECK — see the hook's docstring.
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

  /**
   * Imports a group of attachments in one request, then distributes the
   * returned media rows back to their placeholders by `origin.external_id`
   * (falling back to request order). An attachment the response has no row for
   * keeps its placeholder and is offered a retry.
   */
  const importGroup = useCallback(
    async (group: ImmichAttachment[], momentId: string) => {
      if (!group.length) return;
      let rows: MomentMediaResponse[];
      try {
        const response = await api.importFromImmich({
          moment_id: momentId,
          asset_ids: group.map((item) => item.asset.id),
          assets: group.map((item) => ({
            id: item.asset.id,
            type: item.asset.type,
            title: item.asset.title,
            taken_at: item.asset.taken_at,
            thumb_url: item.asset.thumb_url,
            original_url: item.asset.original_url,
          })),
        });
        rows = response.media ?? [];
      } catch (caught) {
        const message = importErrorMessage(caught);
        for (const item of group) {
          if (!placed.current.has(item.uploadId))
            surfaceRef.current?.setPlaceholderState(item.uploadId, "failed");
          patch(item.uploadId, { state: "failed", message });
        }
        return;
      }

      const byExternalId = new Map<string, MomentMediaResponse>();
      for (const row of rows) {
        const externalId = row.origin?.external_id;
        if (externalId) byExternalId.set(externalId, row);
      }

      for (const [position, item] of group.entries()) {
        // Trust `origin.external_id` when the backend echoes it; only fall back
        // to request order for an older backend that returns no external ids.
        const row =
          byExternalId.get(item.asset.id) ??
          (byExternalId.size === 0 ? rows[position] : undefined);
        if (!row) {
          if (!placed.current.has(item.uploadId))
            surfaceRef.current?.setPlaceholderState(item.uploadId, "failed");
          patch(item.uploadId, {
            state: "failed",
            message: IMPORT_NO_ROW_MESSAGE,
          });
          continue;
        }
        await applyImportedRow(item, row, momentId);
      }
    },
    [applyImportedRow, patch, surfaceRef],
  );

  const attach = useCallback(
    async (assets: IntegrationAssetResponse[], atIndex?: number) => {
      const surface = surfaceRef.current;
      const pickable = assets.filter(isPickableImmichAsset);
      if (!surface || !pickable.length) return;
      setError("");

      const queued: ImmichAttachment[] = [];
      try {
        // Captured before the picker dialog closes — a dialog dismissal, like a
        // native file picker, can move the selection.
        const caret = atIndex ?? surface.getSelectionIndex();

        const draft = await ensureDraft();
        if (!draft) return;

        for (const asset of pickable) {
          queued.push({
            uploadId: uuid(),
            asset,
            kind: kindForAssetType(asset.type),
            state: "importing",
          });
        }

        let index = caret;
        for (const [position, attachment] of queued.entries()) {
          registerPlaceholder(attachment.uploadId, {
            kind: attachment.kind,
            fileName: attachment.asset.title ?? "Immich item",
          });
          surface.insertPlaceholder(index, attachment.uploadId);
          if (position < queued.length - 1) index = surface.getSelectionIndex();
        }
        setAttachments((current) => [...current, ...queued]);
        onDirty();

        await importGroup(queued, draft.momentId);
      } catch {
        for (const attachment of queued)
          surface.removePlaceholder(attachment.uploadId);
        setAttachments((current) =>
          current.filter(
            (item) => !queued.some((q) => q.uploadId === item.uploadId),
          ),
        );
        setError("Could not add media from Immich. Try again.");
      }
    },
    [ensureDraft, importGroup, onDirty, surfaceRef],
  );

  const retry = useCallback(
    async (uploadId: string) => {
      const attachment = attachments.find((item) => item.uploadId === uploadId);
      const draft = await ensureDraft();
      if (!attachment || !draft) return;
      const reprocessing = placed.current.has(uploadId);
      patch(uploadId, {
        state: reprocessing ? "processing" : "importing",
        message: undefined,
      });
      if (!reprocessing) {
        surfaceRef.current?.setPlaceholderState(uploadId, "uploading");
        await importGroup([attachment], draft.momentId);
        return;
      }
      if (attachment.mediaId) {
        pollUntilProcessed(uploadId, draft.momentId, attachment.mediaId);
      } else {
        await importGroup([attachment], draft.momentId);
      }
    },
    [
      attachments,
      ensureDraft,
      importGroup,
      patch,
      pollUntilProcessed,
      surfaceRef,
    ],
  );

  const cancel = useCallback(
    (uploadId: string) => {
      surfaceRef.current?.removePlaceholder(uploadId);
      setAttachments((current) =>
        current.filter((item) => item.uploadId !== uploadId),
      );
    },
    [surfaceRef],
  );

  const pending = attachments.filter(
    (item) => item.state === "importing",
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
