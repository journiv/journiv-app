import { act, renderHook, waitFor } from "@testing-library/react";
import { createRef } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../../api/client/api";
import { ApiError } from "../../../api/client/errors";
import type {
  ImmichImportStartResponse,
  IntegrationAssetResponse,
  MomentMediaResponse,
  UploadStatus,
} from "../../../api/generated/types.gen";
import type { QuillSurfaceHandle } from "../QuillSurface";
import { useImmichAttachments } from "./useImmichAttachments";

vi.mock("../../../api/client/api", () => ({
  api: {
    importFromImmich: vi.fn(),
    deleteMedia: vi.fn(),
    momentMedia: vi.fn(),
  },
}));

const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
};

function makeSurface() {
  const placeholders = new Set<string>();
  /** mediaId -> the fake document index its embed was placed at. */
  const embeds = new Map<string, number>();
  let nextIndex = 100;
  const handle = {
    getSelectionIndex: vi.fn(() => 3),
    insertPlaceholder: vi.fn((_index: number, uploadId: string) => {
      placeholders.add(uploadId);
    }),
    replacePlaceholder: vi.fn(
      (uploadId: string, _kind: string, source: string) => {
        if (!placeholders.has(uploadId)) return false;
        placeholders.delete(uploadId);
        const mediaId = /\/media\/([^/?]+)/.exec(source)?.[1];
        if (mediaId) embeds.set(mediaId, nextIndex++);
        return true;
      },
    ),
    removePlaceholder: vi.fn((uploadId: string) =>
      placeholders.delete(uploadId),
    ),
    removeEmbedForMediaId: vi.fn((mediaId: string) => {
      const index = embeds.get(mediaId);
      if (index === undefined) return null;
      embeds.delete(mediaId);
      return index;
    }),
    hasPlaceholder: vi.fn((uploadId: string) => placeholders.has(uploadId)),
    setPlaceholderState: vi.fn(),
  } as unknown as QuillSurfaceHandle;
  return { handle, placeholders, embeds };
}

function setup(
  overrides: { ensureDraft?: () => Promise<{ momentId: string } | null> } = {},
) {
  const { handle, placeholders, embeds } = makeSurface();
  const ref = createRef<QuillSurfaceHandle>();
  (ref as { current: QuillSurfaceHandle }).current = handle;
  const onDirty = vi.fn();
  const onMediaAdded = vi.fn();
  const hook = renderHook(() =>
    useImmichAttachments({
      surfaceRef: ref,
      ensureDraft:
        overrides.ensureDraft ?? (async () => ({ momentId: "moment-9" })),
      onDirty,
      onMediaAdded,
    }),
  );
  return { hook, handle, placeholders, embeds, onDirty, onMediaAdded };
}

const asset = (
  id: string,
  over: Partial<IntegrationAssetResponse> = {},
): IntegrationAssetResponse => ({
  id,
  type: "IMAGE",
  title: `${id}.jpg`,
  taken_at: "2026-08-01T10:00:00Z",
  thumb_url: `/api/v1/integrations/immich/proxy/${id}/thumbnail?sig=a`,
  original_url: `/api/v1/integrations/immich/proxy/${id}/original?sig=b`,
  ...over,
});

type RowOverride = { signed_url?: string | null; upload_status?: UploadStatus };

const mediaRow = (
  assetId: string,
  over: RowOverride = {},
): MomentMediaResponse => ({
  id: `media-${assetId}`,
  media_type: "image",
  mime_type: "image/jpeg",
  created_at: "2026-08-01T10:00:00Z",
  moment_id: "moment-9",
  signed_url: `/api/v1/media/media-${assetId}/signed?sig=z`,
  upload_status: "completed",
  origin: { source: "immich", external_id: assetId },
  ...over,
});

/** A response that returns one media row per requested asset, matched by id. */
const importResult = (
  assetIds: string[],
  perAsset: Record<string, RowOverride> = {},
): ImmichImportStartResponse => ({
  job_id: "job-x",
  status: "accepted",
  message: "ok",
  total_assets: assetIds.length,
  media: assetIds.map((id) => mediaRow(id, perAsset[id])),
});

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.momentMedia).mockResolvedValue([]);
  vi.mocked(api.deleteMedia).mockResolvedValue(undefined as never);
  vi.mocked(api.importFromImmich).mockImplementation(async ({ asset_ids }) =>
    importResult(asset_ids),
  );
});
afterEach(() => vi.restoreAllMocks());

describe("useImmichAttachments", () => {
  it("imports the whole selection in one call and swaps every placeholder", async () => {
    const { hook, handle, onMediaAdded } = setup();

    await act(async () => {
      await hook.result.current.attach([asset("a"), asset("b")]);
    });

    expect(handle.getSelectionIndex).toHaveBeenCalled();
    expect(handle.insertPlaceholder).toHaveBeenCalledTimes(2);
    // One request for the batch — not one per asset (the SQLite write-lock race).
    expect(api.importFromImmich).toHaveBeenCalledTimes(1);
    expect(api.importFromImmich).toHaveBeenCalledWith(
      expect.objectContaining({
        moment_id: "moment-9",
        asset_ids: ["a", "b"],
      }),
    );
    expect(handle.replacePlaceholder).toHaveBeenCalledWith(
      expect.any(String),
      "image",
      "/api/v1/media/media-a/signed?sig=z",
    );
    expect(handle.replacePlaceholder).toHaveBeenCalledWith(
      expect.any(String),
      "image",
      "/api/v1/media/media-b/signed?sig=z",
    );
    expect(onMediaAdded).toHaveBeenCalledWith("media-a");
    expect(onMediaAdded).toHaveBeenCalledWith("media-b");
    await waitFor(() => expect(hook.result.current.pending).toBe(0));
  });

  it("matches rows to placeholders by origin.external_id even when reordered", async () => {
    vi.mocked(api.importFromImmich).mockResolvedValue({
      job_id: "job-x",
      status: "accepted",
      message: "ok",
      total_assets: 3,
      // Deliberately out of request order — positional mapping would misplace them.
      media: [mediaRow("c"), mediaRow("a"), mediaRow("b")],
    });
    const { hook, handle } = setup();

    await act(async () => {
      await hook.result.current.attach([asset("a"), asset("b"), asset("c")]);
    });

    // Each placeholder must receive *its own* asset's signed URL, keyed by the
    // upload id the attachment was created with.
    for (const attachment of hook.result.current.attachments) {
      expect(handle.replacePlaceholder).toHaveBeenCalledWith(
        attachment.uploadId,
        "image",
        `/api/v1/media/media-${attachment.asset.id}/signed?sig=z`,
      );
    }
  });

  it("fails only the asset the response omitted, keeping its placeholder", async () => {
    vi.mocked(api.importFromImmich).mockResolvedValue(importResult(["a"]));
    const { hook, handle, onMediaAdded } = setup();

    await act(async () => {
      await hook.result.current.attach([asset("a"), asset("b")]);
    });

    expect(handle.replacePlaceholder).toHaveBeenCalledWith(
      expect.any(String),
      "image",
      "/api/v1/media/media-a/signed?sig=z",
    );
    expect(onMediaAdded).toHaveBeenCalledTimes(1);
    expect(onMediaAdded).toHaveBeenCalledWith("media-a");
    expect(handle.setPlaceholderState).toHaveBeenCalledWith(
      expect.any(String),
      "failed",
    );
    await waitFor(() => expect(hook.result.current.failed).toHaveLength(1));
    expect(hook.result.current.failed[0].asset.id).toBe("b");
  });

  it("maps a video asset to the video embed kind", async () => {
    const { hook, handle } = setup();
    await act(async () => {
      await hook.result.current.attach([asset("v", { type: "VIDEO" })]);
    });
    expect(handle.replacePlaceholder).toHaveBeenCalledWith(
      expect.any(String),
      "video",
      expect.any(String),
    );
  });

  it("skips assets Journiv cannot inline", async () => {
    const { hook, handle } = setup();
    await act(async () => {
      await hook.result.current.attach([asset("aud", { type: "AUDIO" })]);
    });
    expect(handle.insertPlaceholder).not.toHaveBeenCalled();
    expect(api.importFromImmich).not.toHaveBeenCalled();
  });

  it("does NOT resurrect media whose placeholder was removed mid-import", async () => {
    const pending = deferred<ImmichImportStartResponse>();
    vi.mocked(api.importFromImmich).mockReturnValue(pending.promise as never);
    const { hook, handle, placeholders, onMediaAdded } = setup();

    await act(async () => {
      void hook.result.current.attach([asset("a")]);
      await Promise.resolve();
    });
    // Writer deletes the placeholder while the import is in flight.
    placeholders.clear();

    await act(async () => {
      pending.resolve(importResult(["a"]));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(handle.replacePlaceholder).toHaveReturnedWith(false);
    expect(onMediaAdded).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(api.deleteMedia).toHaveBeenCalledWith("media-a"),
    );
  });

  it("keeps the placeholder and offers a retry when the import fails", async () => {
    vi.mocked(api.importFromImmich)
      .mockRejectedValueOnce(new ApiError("boom", { status: 500 }))
      .mockImplementationOnce(async ({ asset_ids }) => importResult(asset_ids));
    const { hook, handle } = setup();

    await act(async () => {
      await hook.result.current.attach([asset("a")]);
    });

    expect(handle.setPlaceholderState).toHaveBeenCalledWith(
      expect.any(String),
      "failed",
    );
    await waitFor(() => expect(hook.result.current.failed).toHaveLength(1));
    expect(handle.removePlaceholder).not.toHaveBeenCalled();

    const uploadId = hook.result.current.attachments[0].uploadId;
    await act(async () => {
      await hook.result.current.retry(uploadId);
    });
    expect(api.importFromImmich).toHaveBeenCalledTimes(2);
    await waitFor(() => expect(hook.result.current.failed).toHaveLength(0));
  });

  it("surfaces a reconnect hint on an auth failure", async () => {
    vi.mocked(api.importFromImmich).mockRejectedValue(
      new ApiError("nope", { status: 401 }),
    );
    const { hook } = setup();
    await act(async () => {
      await hook.result.current.attach([asset("a")]);
    });
    await waitFor(() =>
      expect(hook.result.current.failed[0].message).toMatch(/reconnect/i),
    );
  });

  it("fails the tile when the import returns no media at all", async () => {
    vi.mocked(api.importFromImmich).mockResolvedValue({
      job_id: "job-x",
      status: "accepted",
      message: "ok",
      total_assets: 1,
      media: [],
    });
    const { hook, handle } = setup();
    await act(async () => {
      await hook.result.current.attach([asset("a")]);
    });
    expect(handle.setPlaceholderState).toHaveBeenCalledWith(
      expect.any(String),
      "failed",
    );
    await waitFor(() => expect(hook.result.current.failed).toHaveLength(1));
  });

  it("fails the tile, not the race path, when a row has no displayable URL", async () => {
    vi.mocked(api.importFromImmich)
      .mockResolvedValueOnce(
        importResult(["a"], {
          a: { signed_url: null, upload_status: "processing" },
        }),
      )
      .mockImplementationOnce(async ({ asset_ids }) => importResult(asset_ids));
    const { hook, handle, placeholders, onMediaAdded } = setup();

    await act(async () => {
      await hook.result.current.attach([asset("a")]);
    });

    expect(handle.replacePlaceholder).not.toHaveBeenCalled();
    expect(handle.setPlaceholderState).toHaveBeenCalledWith(
      expect.any(String),
      "failed",
    );
    expect(placeholders.size).toBe(1);
    expect(onMediaAdded).not.toHaveBeenCalled();
    expect(api.deleteMedia).toHaveBeenCalledWith("media-a");
    await waitFor(() => expect(hook.result.current.failed).toHaveLength(1));

    const uploadId = hook.result.current.attachments[0].uploadId;
    await act(async () => {
      await hook.result.current.retry(uploadId);
    });
    expect(api.importFromImmich).toHaveBeenCalledTimes(2);
    expect(onMediaAdded).toHaveBeenCalledWith("media-a");
    await waitFor(() => expect(hook.result.current.failed).toHaveLength(0));
  });

  it("does not block saving while the server is still processing", async () => {
    vi.mocked(api.importFromImmich).mockResolvedValue(
      importResult(["a"], { a: { upload_status: "pending" } }),
    );
    const { hook } = setup();
    await act(async () => {
      await hook.result.current.attach([asset("a")]);
    });
    await waitFor(() => expect(hook.result.current.processing).toBe(1));
    expect(hook.result.current.pending).toBe(0);
  });

  it("blocks saving while the import call is still in flight", async () => {
    const pending = deferred<ImmichImportStartResponse>();
    vi.mocked(api.importFromImmich).mockReturnValue(pending.promise as never);
    const { hook } = setup();
    await act(async () => {
      void hook.result.current.attach([asset("a")]);
      await Promise.resolve();
    });
    expect(hook.result.current.pending).toBe(1);
    await act(async () => {
      pending.resolve(importResult(["a"]));
      await pending.promise;
    });
  });

  it("does nothing when there is no journal to attach against", async () => {
    const { hook, handle } = setup({ ensureDraft: async () => null });
    await act(async () => {
      await hook.result.current.attach([asset("a")]);
    });
    expect(handle.insertPlaceholder).not.toHaveBeenCalled();
    expect(api.importFromImmich).not.toHaveBeenCalled();
  });

  it("removes the embed (not just a placeholder) when cancelling an already-placed item", async () => {
    // Regression: once the placeholder is swapped for the real embed,
    // `removePlaceholder` finds nothing — the broken image used to stay in
    // the document with only the notice disappearing.
    vi.mocked(api.importFromImmich).mockResolvedValue(
      importResult(["a"], { a: { upload_status: "processing" } }),
    );
    const { hook, handle, embeds, onDirty } = setup();

    await act(async () => {
      await hook.result.current.attach([asset("a")]);
    });
    expect(embeds.has("media-a")).toBe(true);
    onDirty.mockClear();

    const uploadId = hook.result.current.attachments[0].uploadId;
    act(() => hook.result.current.cancel(uploadId));

    expect(handle.removeEmbedForMediaId).toHaveBeenCalledWith("media-a");
    expect(embeds.has("media-a")).toBe(false);
    expect(handle.removePlaceholder).not.toHaveBeenCalled();
    expect(onDirty).toHaveBeenCalled();
    // Session media the saved document never referenced: the save's orphan
    // cleanup would never collect it, so Remove deletes the row itself.
    expect(api.deleteMedia).toHaveBeenCalledWith("media-a");
    expect(hook.result.current.attachments).toHaveLength(0);
  });

  it("keepPlacedMedia leaves an already-placed item's embed untouched", async () => {
    // Regression: leaving the editor without saving sweeps every attachment
    // through cancel() to abort in-flight work. Before this option, that
    // swept an already-placed item's embed too — removing content from the
    // document AND marking it dirty, which re-armed and resurrected the
    // local draft the same flow had just explicitly discarded.
    vi.mocked(api.importFromImmich).mockResolvedValue(
      importResult(["a"], { a: { upload_status: "processing" } }),
    );
    const { hook, handle, embeds, onDirty } = setup();

    await act(async () => {
      await hook.result.current.attach([asset("a")]);
    });
    expect(embeds.has("media-a")).toBe(true);
    onDirty.mockClear();

    const uploadId = hook.result.current.attachments[0].uploadId;
    act(() => hook.result.current.cancel(uploadId, { keepPlacedMedia: true }));

    expect(handle.removeEmbedForMediaId).not.toHaveBeenCalled();
    expect(embeds.has("media-a")).toBe(true);
    expect(onDirty).not.toHaveBeenCalled();
    expect(api.deleteMedia).not.toHaveBeenCalled();
    expect(hook.result.current.attachments).toHaveLength(0);
  });

  it("retries a stalled placed item by resuming the poll, not by re-importing", async () => {
    vi.useFakeTimers();
    try {
      vi.mocked(api.importFromImmich).mockResolvedValue(
        importResult(["a"], { a: { upload_status: "processing" } }),
      );
      vi.mocked(api.momentMedia).mockResolvedValue([
        { id: "media-a", upload_status: "processing" },
      ] as never);
      const { hook, handle, embeds } = setup();

      await act(async () => {
        await hook.result.current.attach([asset("a")]);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(190_000);
      });
      expect(hook.result.current.failed).toHaveLength(1);
      expect(hook.result.current.failed[0].message).toMatch(
        /still being processed/i,
      );
      const uploadId = hook.result.current.attachments[0].uploadId;
      const importsBeforeRetry = vi.mocked(api.importFromImmich).mock.calls
        .length;

      await act(async () => {
        await hook.result.current.retry(uploadId);
      });

      // A stalled item may still finish server-side: retry just resumes
      // polling. It must not touch the embed or re-import the asset.
      expect(hook.result.current.attachments[0].failureReason).toBeUndefined();
      expect(handle.removeEmbedForMediaId).not.toHaveBeenCalled();
      expect(vi.mocked(api.importFromImmich).mock.calls.length).toBe(
        importsBeforeRetry,
      );
      expect(embeds.has("media-a")).toBe(true);
    } finally {
      vi.useRealTimers();
    }
  });

  it("retries a server-failed placed item by re-importing, since the backend upserts the row", async () => {
    vi.useFakeTimers();
    try {
      vi.mocked(api.importFromImmich).mockResolvedValue(
        importResult(["a"], { a: { upload_status: "processing" } }),
      );
      vi.mocked(api.momentMedia).mockResolvedValue([
        { id: "media-a", upload_status: "failed" },
      ] as never);
      const { hook, embeds } = setup();

      await act(async () => {
        await hook.result.current.attach([asset("a")]);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });
      expect(hook.result.current.failed).toHaveLength(1);
      expect(hook.result.current.failed[0].message).toMatch(
        /couldn.t be processed/i,
      );
      const uploadId = hook.result.current.attachments[0].uploadId;
      const importsBeforeRetry = vi.mocked(api.importFromImmich).mock.calls
        .length;

      await act(async () => {
        await hook.result.current.retry(uploadId);
      });

      // A definitive server failure needs a fresh import: the backend
      // upserts the existing row (matched by asset id) back to processing —
      // nothing to delete, and the embed already points at the same id.
      expect(vi.mocked(api.importFromImmich).mock.calls.length).toBe(
        importsBeforeRetry + 1,
      );
      expect(api.deleteMedia).not.toHaveBeenCalled();
      expect(embeds.has("media-a")).toBe(true);
      expect(
        hook.result.current.attachments.some(
          (item) => item.uploadId === uploadId,
        ),
      ).toBe(true);
    } finally {
      vi.useRealTimers();
    }
  });
});
