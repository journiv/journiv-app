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
  const handle = {
    getSelectionIndex: vi.fn(() => 3),
    insertPlaceholder: vi.fn((_index: number, uploadId: string) => {
      placeholders.add(uploadId);
    }),
    replacePlaceholder: vi.fn((uploadId: string) => {
      if (!placeholders.has(uploadId)) return false;
      placeholders.delete(uploadId);
      return true;
    }),
    removePlaceholder: vi.fn((uploadId: string) =>
      placeholders.delete(uploadId),
    ),
    hasPlaceholder: vi.fn((uploadId: string) => placeholders.has(uploadId)),
    setPlaceholderState: vi.fn(),
  } as unknown as QuillSurfaceHandle;
  return { handle, placeholders };
}

function setup(
  overrides: { ensureDraft?: () => Promise<{ momentId: string } | null> } = {},
) {
  const { handle, placeholders } = makeSurface();
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
  return { hook, handle, placeholders, onDirty, onMediaAdded };
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
});
