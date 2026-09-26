import { act, renderHook, waitFor } from "@testing-library/react";
import { createRef } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client/api";
import type { QuillSurfaceHandle } from "./QuillSurface";
import { useMediaAttachments } from "./useMediaAttachments";

vi.mock("../../api/client/api", () => ({
  api: { deleteMedia: vi.fn(), momentMedia: vi.fn() },
}));

const deferred = () => {
  let resolve!: (value: unknown) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise((res, rej) => {
    resolve = res as never;
    reject = rej as never;
  });
  return { promise, resolve, reject };
};

const uploadMock = vi.fn();
vi.mock("./mediaUpload", async () => {
  const actual =
    await vi.importActual<typeof import("./mediaUpload")>("./mediaUpload");
  return {
    ...actual,
    uploadMedia: (...args: unknown[]) => uploadMock(...args),
  };
});

function makeSurface() {
  const placeholders = new Set<string>();
  /** mediaId -> the fake document index its embed was placed at. */
  const embeds = new Map<string, number>();
  let nextIndex = 100;
  const handle: QuillSurfaceHandle = {
    getSelectionIndex: vi.fn(() => 5),
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
    useMediaAttachments({
      surfaceRef: ref,
      ensureDraft:
        overrides.ensureDraft ?? (async () => ({ momentId: "moment-1" })),
      onDirty,
      onMediaAdded,
    }),
  );
  return { hook, handle, placeholders, embeds, onDirty, onMediaAdded };
}

const photo = (name = "photo.jpg") =>
  new File(["bytes"], name, { type: "image/jpeg" });

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: vi.fn(() => "blob:preview"),
    revokeObjectURL: vi.fn(),
  });
  vi.mocked(api.momentMedia).mockResolvedValue([]);
  vi.mocked(api.deleteMedia).mockResolvedValue(undefined as never);
});
afterEach(() => vi.unstubAllGlobals());

describe("useMediaAttachments", () => {
  it("captures the caret, inserts a placeholder, then uploads", async () => {
    const pending = deferred();
    uploadMock.mockReturnValue({ promise: pending.promise, abort: vi.fn() });
    const { hook, handle, onDirty } = setup();

    await act(async () => {
      void hook.result.current.attach([photo()]);
      await Promise.resolve();
    });

    expect(handle.getSelectionIndex).toHaveBeenCalled();
    expect(handle.insertPlaceholder).toHaveBeenCalledWith(
      5,
      expect.any(String),
    );
    expect(onDirty).toHaveBeenCalled();
    expect(uploadMock.mock.calls[0][0]).toMatchObject({ momentId: "moment-1" });

    await act(async () => {
      pending.resolve({
        id: "media-1",
        signed_url: "/s",
        upload_status: "completed",
      });
      await pending.promise.catch(() => undefined);
    });
  });

  it("swaps the placeholder for the durable reference on success", async () => {
    uploadMock.mockReturnValue({
      promise: Promise.resolve({
        id: "media-1",
        signed_url: "/api/v1/media/media-1/signed?sig=a",
        upload_status: "completed",
      }),
      abort: vi.fn(),
    });
    const { hook, handle, onMediaAdded } = setup();

    await act(async () => {
      await hook.result.current.attach([photo()]);
    });

    expect(handle.replacePlaceholder).toHaveBeenCalledWith(
      expect.any(String),
      "image",
      "/api/v1/media/media-1/signed?sig=a",
    );
    expect(onMediaAdded).toHaveBeenCalledWith("media-1");
    await waitFor(() => expect(hook.result.current.pending).toBe(0));
  });

  it("does NOT resurrect media whose placeholder was removed mid-upload", async () => {
    const pending = deferred();
    uploadMock.mockReturnValue({ promise: pending.promise, abort: vi.fn() });
    const { hook, handle, placeholders, onMediaAdded } = setup();

    await act(async () => {
      void hook.result.current.attach([photo()]);
      await Promise.resolve();
    });
    // The user deletes the placeholder — or undoes it — while bytes are in
    // flight. This is the race the whole design exists to prevent.
    placeholders.clear();

    await act(async () => {
      pending.resolve({
        id: "media-1",
        signed_url: "/s",
        upload_status: "completed",
      });
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(handle.replacePlaceholder).toHaveReturnedWith(false);
    expect(onMediaAdded).not.toHaveBeenCalled();
    // The orphan is cleaned up rather than left on the Moment.
    await waitFor(() =>
      expect(api.deleteMedia).toHaveBeenCalledWith("media-1"),
    );
  });

  it("does not block saving while the server is still processing", async () => {
    // Found in the browser: counting `processing` as pending made Done refuse
    // for up to a minute after the upload had already finished. Once the
    // placeholder is swapped for a durable reference the document is correct.
    uploadMock.mockReturnValue({
      promise: Promise.resolve({
        id: "media-1",
        signed_url: "/api/v1/media/media-1/signed",
        upload_status: "pending",
      }),
      abort: vi.fn(),
    });
    const { hook } = setup();

    await act(async () => {
      await hook.result.current.attach([photo()]);
    });

    await waitFor(() => expect(hook.result.current.processing).toBe(1));
    expect(hook.result.current.pending).toBe(0);
  });

  it("keeps the writing and offers a retry when an upload fails", async () => {
    const failing = deferred();
    uploadMock.mockReturnValue({ promise: failing.promise, abort: vi.fn() });
    const { hook, handle } = setup();

    await act(async () => {
      void hook.result.current.attach([photo()]);
      await Promise.resolve();
    });
    await act(async () => {
      failing.reject(new Error("network"));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(handle.setPlaceholderState).toHaveBeenCalledWith(
      expect.any(String),
      "failed",
    );
    await waitFor(() => expect(hook.result.current.failed).toHaveLength(1));
    // The placeholder stays put, so the writing around it is untouched.
    expect(handle.removePlaceholder).not.toHaveBeenCalled();
  });

  it("creates a local preview URL for images only", async () => {
    uploadMock.mockReturnValue({
      promise: new Promise(() => {}),
      abort: vi.fn(),
    });
    const { hook } = setup();
    await act(async () => {
      void hook.result.current.attach([
        photo(),
        new File(["v"], "clip.mp4", { type: "video/mp4" }),
      ]);
      await Promise.resolve();
    });
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
  });

  it("aborts quietly on cancel instead of reporting a failure", async () => {
    const abort = vi.fn();
    uploadMock.mockReturnValue({ promise: new Promise(() => {}), abort });
    const { hook, handle } = setup();
    await act(async () => {
      void hook.result.current.attach([photo()]);
      await Promise.resolve();
    });

    const uploadId = hook.result.current.attachments[0].uploadId;
    act(() => hook.result.current.cancel(uploadId));

    expect(abort).toHaveBeenCalled();
    expect(handle.removePlaceholder).toHaveBeenCalledWith(uploadId);
    expect(hook.result.current.attachments).toHaveLength(0);
    expect(hook.result.current.failed).toHaveLength(0);
  });

  it("removes the embed (not just a placeholder) when cancelling an already-placed item", async () => {
    // Regression: once the placeholder is swapped for the real embed,
    // `removePlaceholder` finds nothing — the broken image used to stay in
    // the document with only the notice disappearing.
    uploadMock.mockReturnValue({
      promise: Promise.resolve({
        id: "media-1",
        signed_url: "/api/v1/media/media-1/signed",
        upload_status: "completed",
      }),
      abort: vi.fn(),
    });
    const { hook, handle, embeds, onDirty } = setup();

    await act(async () => {
      await hook.result.current.attach([photo()]);
    });
    expect(embeds.has("media-1")).toBe(true);
    onDirty.mockClear();

    const uploadId = hook.result.current.attachments[0].uploadId;
    act(() => hook.result.current.cancel(uploadId));

    expect(handle.removeEmbedForMediaId).toHaveBeenCalledWith("media-1");
    expect(embeds.has("media-1")).toBe(false);
    expect(handle.removePlaceholder).not.toHaveBeenCalled();
    expect(onDirty).toHaveBeenCalled();
    // Session media the saved document never referenced: the save's orphan
    // cleanup would never collect it, so Remove deletes the row itself.
    expect(api.deleteMedia).toHaveBeenCalledWith("media-1");
    expect(hook.result.current.attachments).toHaveLength(0);
  });

  it("keepPlacedMedia leaves an already-placed item's embed untouched", async () => {
    // Regression: leaving the editor without saving sweeps every attachment
    // through cancel() to abort in-flight work. Before this option, that
    // swept an already-placed item's embed too — removing content from the
    // document AND marking it dirty, which re-armed and resurrected the
    // local draft the same flow had just explicitly discarded.
    uploadMock.mockReturnValue({
      promise: Promise.resolve({
        id: "media-1",
        signed_url: "/api/v1/media/media-1/signed",
        upload_status: "completed",
      }),
      abort: vi.fn(),
    });
    const { hook, handle, embeds, onDirty } = setup();

    await act(async () => {
      await hook.result.current.attach([photo()]);
    });
    expect(embeds.has("media-1")).toBe(true);
    onDirty.mockClear();

    const uploadId = hook.result.current.attachments[0].uploadId;
    act(() => hook.result.current.cancel(uploadId, { keepPlacedMedia: true }));

    expect(handle.removeEmbedForMediaId).not.toHaveBeenCalled();
    expect(embeds.has("media-1")).toBe(true);
    expect(onDirty).not.toHaveBeenCalled();
    expect(api.deleteMedia).not.toHaveBeenCalled();
    expect(hook.result.current.attachments).toHaveLength(0);
  });

  it("keeps successful siblings when one of several files fails", async () => {
    // Selecting a batch is normal. One bad file must not discard the rest.
    const good = {
      id: "media-good",
      signed_url: "/good",
      upload_status: "completed",
    };
    uploadMock
      .mockReturnValueOnce({ promise: Promise.resolve(good), abort: vi.fn() })
      .mockReturnValueOnce({
        promise: Promise.reject(new Error("boom")),
        abort: vi.fn(),
      })
      .mockReturnValueOnce({
        promise: Promise.resolve({ ...good, id: "media-third" }),
        abort: vi.fn(),
      });
    const { hook, onMediaAdded } = setup();

    await act(async () => {
      await hook.result.current.attach([photo(), photo(), photo()]);
    });

    await waitFor(() => expect(hook.result.current.failed).toHaveLength(1));
    expect(onMediaAdded).toHaveBeenCalledWith("media-good");
    expect(onMediaAdded).toHaveBeenCalledWith("media-third");
    expect(onMediaAdded).toHaveBeenCalledTimes(2);
  });

  it("places several files in the order they were chosen", async () => {
    uploadMock.mockReturnValue({
      promise: new Promise(() => {}),
      abort: vi.fn(),
    });
    const { hook, handle } = setup();

    await act(async () => {
      void hook.result.current.attach([
        photo("a.jpg"),
        photo("b.jpg"),
        photo("c.jpg"),
      ]);
      await Promise.resolve();
    });

    // Placeholders go in before any byte is sent, so the writer sees where each
    // file will land immediately.
    expect(handle.insertPlaceholder).toHaveBeenCalledTimes(3);
    expect(
      hook.result.current.attachments.map((item) => item.file.name),
    ).toEqual(["a.jpg", "b.jpg", "c.jpg"]);
  });

  it("honours an explicit drop position instead of the caret", async () => {
    uploadMock.mockReturnValue({
      promise: new Promise(() => {}),
      abort: vi.fn(),
    });
    const { hook, handle } = setup();

    await act(async () => {
      void hook.result.current.attach([photo()], 42);
      await Promise.resolve();
    });

    expect(handle.insertPlaceholder).toHaveBeenCalledWith(
      42,
      expect.any(String),
    );
    expect(handle.getSelectionIndex).not.toHaveBeenCalled();
  });

  it("attaches without a secure context, where crypto.randomUUID is missing", async () => {
    // Over plain HTTP on a LAN this threw and the photo simply never appeared.
    vi.stubGlobal("crypto", {
      getRandomValues: globalThis.crypto.getRandomValues.bind(
        globalThis.crypto,
      ),
    });
    uploadMock.mockReturnValue({
      promise: new Promise(() => {}),
      abort: vi.fn(),
    });
    const { hook, handle } = setup();

    await act(async () => {
      void hook.result.current.attach([photo()]);
      await Promise.resolve();
    });

    expect(handle.insertPlaceholder).toHaveBeenCalledTimes(1);
    expect(hook.result.current.error).toBe("");
  });

  it("reports a failed attach instead of doing nothing", async () => {
    const { hook, handle } = setup({
      ensureDraft: async () => {
        throw new Error("draft unavailable");
      },
    });

    await act(async () => {
      await hook.result.current.attach([photo()]);
    });

    // Silence is the worst outcome: the writer taps a photo and nothing happens.
    await waitFor(() => expect(hook.result.current.error).not.toBe(""));
    expect(handle.insertPlaceholder).not.toHaveBeenCalled();
  });

  it("does nothing when there is no server identity to upload against", async () => {
    const { hook, handle } = setup({ ensureDraft: async () => null });
    await act(async () => {
      await hook.result.current.attach([photo()]);
    });
    expect(handle.insertPlaceholder).not.toHaveBeenCalled();
    expect(uploadMock).not.toHaveBeenCalled();
  });

  it("surfaces a message when the server reports processing failed", async () => {
    vi.useFakeTimers();
    try {
      uploadMock.mockReturnValue({
        promise: Promise.resolve({
          id: "media-1",
          signed_url: "/api/v1/media/media-1/signed",
          upload_status: "pending",
        }),
        abort: vi.fn(),
      });
      vi.mocked(api.momentMedia).mockResolvedValue([
        { id: "media-1", upload_status: "failed" },
      ] as never);
      const { hook } = setup();

      await act(async () => {
        await hook.result.current.attach([photo()]);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });

      expect(hook.result.current.failed).toHaveLength(1);
      expect(hook.result.current.failed[0].message).toMatch(
        /couldn.t be processed/i,
      );
    } finally {
      vi.useRealTimers();
    }
  });

  it("reports a stalled file as failed rather than a false success on timeout", async () => {
    // Regression: the poll used to give up after its window and mark the
    // attachment `done`, hiding media that never finished processing.
    vi.useFakeTimers();
    try {
      uploadMock.mockReturnValue({
        promise: Promise.resolve({
          id: "media-1",
          signed_url: "/api/v1/media/media-1/signed",
          upload_status: "pending",
        }),
        abort: vi.fn(),
      });
      vi.mocked(api.momentMedia).mockResolvedValue([
        { id: "media-1", upload_status: "pending" },
      ] as never);
      const { hook } = setup();

      await act(async () => {
        await hook.result.current.attach([photo()]);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(190_000);
      });

      const attachment = hook.result.current.attachments[0];
      expect(attachment.state).toBe("failed");
      expect(attachment.message).toMatch(/still being processed/i);
      expect(hook.result.current.failed).toHaveLength(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("retries a stalled placed item by resuming the poll, not by re-uploading", async () => {
    vi.useFakeTimers();
    try {
      uploadMock.mockReturnValue({
        promise: Promise.resolve({
          id: "media-1",
          signed_url: "/api/v1/media/media-1/signed",
          upload_status: "pending",
        }),
        abort: vi.fn(),
      });
      vi.mocked(api.momentMedia).mockResolvedValue([
        { id: "media-1", upload_status: "pending" },
      ] as never);
      const { hook, handle, embeds } = setup();

      await act(async () => {
        await hook.result.current.attach([photo()]);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(190_000);
      });
      expect(hook.result.current.failed).toHaveLength(1);
      expect(hook.result.current.failed[0].message).toMatch(
        /still being processed/i,
      );
      const uploadId = hook.result.current.attachments[0].uploadId;
      const uploadsBeforeRetry = uploadMock.mock.calls.length;

      await act(async () => {
        await hook.result.current.retry(uploadId);
      });

      // A stalled item may still finish server-side: retry just resumes
      // polling. It must not touch the embed or upload the file again.
      expect(handle.removeEmbedForMediaId).not.toHaveBeenCalled();
      expect(uploadMock.mock.calls.length).toBe(uploadsBeforeRetry);
      expect(embeds.has("media-1")).toBe(true);
      expect(api.deleteMedia).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it("does not keep a re-upload whose embed the writer already removed", async () => {
    vi.useFakeTimers();
    try {
      uploadMock.mockReturnValue({
        promise: Promise.resolve({
          id: "media-1",
          signed_url: "/api/v1/media/media-1/signed",
          upload_status: "pending",
        }),
        abort: vi.fn(),
      });
      vi.mocked(api.momentMedia).mockResolvedValue([
        { id: "media-1", upload_status: "failed" },
      ] as never);
      const { hook, embeds } = setup();

      await act(async () => {
        await hook.result.current.attach([photo()]);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });
      const uploadId = hook.result.current.attachments[0].uploadId;
      // The writer deleted the broken image from the prose before retrying.
      embeds.delete("media-1");
      uploadMock.mockReturnValue({
        promise: Promise.resolve({
          id: "media-2",
          signed_url: "/api/v1/media/media-2/signed",
          upload_status: "completed",
        }),
        abort: vi.fn(),
      });

      await act(async () => {
        await hook.result.current.retry(uploadId);
      });

      // Nothing in the document references either row, so neither may stay
      // on the Moment: the failed one and the fresh upload are both deleted.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(api.deleteMedia).toHaveBeenCalledWith("media-1");
      expect(api.deleteMedia).toHaveBeenCalledWith("media-2");
      expect(embeds.size).toBe(0);
    } finally {
      vi.useRealTimers();
    }
  });

  it("retries a server-failed placed item by removing its embed and re-uploading", async () => {
    vi.useFakeTimers();
    try {
      uploadMock.mockReturnValue({
        promise: Promise.resolve({
          id: "media-1",
          signed_url: "/api/v1/media/media-1/signed",
          upload_status: "pending",
        }),
        abort: vi.fn(),
      });
      vi.mocked(api.momentMedia).mockResolvedValue([
        { id: "media-1", upload_status: "failed" },
      ] as never);
      const { hook, handle, embeds, onDirty } = setup();

      await act(async () => {
        await hook.result.current.attach([photo()]);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });
      expect(hook.result.current.failed).toHaveLength(1);
      expect(hook.result.current.failed[0].message).toMatch(
        /couldn.t be processed/i,
      );
      const uploadId = hook.result.current.attachments[0].uploadId;
      const uploadsBeforeRetry = uploadMock.mock.calls.length;
      onDirty.mockClear();
      uploadMock.mockReturnValue({
        promise: Promise.resolve({
          id: "media-2",
          signed_url: "/api/v1/media/media-2/signed",
          upload_status: "completed",
        }),
        abort: vi.fn(),
      });

      await act(async () => {
        await hook.result.current.retry(uploadId);
      });

      // A definitive server failure has no "reprocess this row" request —
      // uploading always makes a new row — so the old embed comes out, a
      // fresh upload swaps a new one back in at the same spot, and the failed
      // row it replaces is deleted rather than left on the Moment.
      expect(handle.removeEmbedForMediaId).toHaveBeenCalledWith("media-1");
      expect(uploadMock.mock.calls.length).toBe(uploadsBeforeRetry + 1);
      expect(embeds.has("media-1")).toBe(false);
      expect(embeds.has("media-2")).toBe(true);
      expect(onDirty).toHaveBeenCalled();
      expect(api.deleteMedia).toHaveBeenCalledTimes(1);
      expect(api.deleteMedia).toHaveBeenCalledWith("media-1");
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
