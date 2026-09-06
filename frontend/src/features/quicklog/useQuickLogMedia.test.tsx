import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client/api";
import { MediaUploadError, uploadMedia } from "../editor/mediaUpload";
import { useQuickLogMedia } from "./useQuickLogMedia";

vi.mock("../../api/client/api", () => ({
  api: { deleteMedia: vi.fn() },
}));
vi.mock("../editor/mediaUpload", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../editor/mediaUpload")>()),
  uploadMedia: vi.fn(),
}));

const uploadMock = vi.mocked(uploadMedia);
const deleteMedia = vi.mocked(api.deleteMedia);

const file = (name: string, type = "image/jpeg") =>
  new File(["x"], name, { type });

beforeEach(() => {
  vi.clearAllMocks();
  deleteMedia.mockResolvedValue(undefined as never);
  globalThis.URL.createObjectURL = vi.fn(() => "blob:preview");
  globalThis.URL.revokeObjectURL = vi.fn();
});

describe("useQuickLogMedia", () => {
  it("uploads through the shared helper and records the media id", async () => {
    uploadMock.mockReturnValue({
      promise: Promise.resolve({ id: "media-1" } as never),
      abort: vi.fn(),
    });
    const ensureMoment = vi.fn(async () => "m-1");
    const { result } = renderHook(() => useQuickLogMedia({ ensureMoment }));

    await act(async () => {
      await result.current.attach([file("a.jpg")]);
    });

    expect(ensureMoment).toHaveBeenCalledTimes(1);
    expect(uploadMock).toHaveBeenCalledWith(
      expect.objectContaining({ momentId: "m-1" }),
    );
    await waitFor(() => {
      expect(result.current.items[0]?.status).toBe("done");
      expect(result.current.items[0]?.mediaId).toBe("media-1");
    });
    expect(result.current.count).toBe(1);
  });

  it("deletes an uploaded file from the server when removed", async () => {
    uploadMock.mockReturnValue({
      promise: Promise.resolve({ id: "media-1" } as never),
      abort: vi.fn(),
    });
    const { result } = renderHook(() =>
      useQuickLogMedia({ ensureMoment: async () => "m-1" }),
    );
    await act(async () => {
      await result.current.attach([file("a.jpg")]);
    });
    const uploadId = result.current.items[0].uploadId;

    act(() => result.current.remove(uploadId));

    expect(deleteMedia).toHaveBeenCalledWith("media-1");
    expect(result.current.items).toHaveLength(0);
  });

  it("deletes media that completes after its upload was removed", async () => {
    let resolveUpload!: (media: never) => void;
    const abort = vi.fn();
    uploadMock.mockReturnValue({
      promise: new Promise((resolve) => {
        resolveUpload = resolve;
      }) as Promise<never>,
      abort,
    });
    const { result } = renderHook(() =>
      useQuickLogMedia({ ensureMoment: async () => "m-1" }),
    );

    act(() => {
      void result.current.attach([file("a.jpg")]);
    });
    await waitFor(() => expect(result.current.items).toHaveLength(1));
    const uploadId = result.current.items[0].uploadId;

    act(() => result.current.remove(uploadId));
    expect(abort).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveUpload({ id: "media-late" } as never);
    });
    await waitFor(() => expect(deleteMedia).toHaveBeenCalledWith("media-late"));
    expect(result.current.items).toHaveLength(0);
  });

  it("aborts active uploads and waits for their settlement", async () => {
    let rejectUpload: ((error: Error) => void) | undefined;
    const abort = vi.fn();
    uploadMock.mockReturnValue({
      promise: new Promise((_, reject) => {
        rejectUpload = reject;
      }),
      abort,
    });
    const { result } = renderHook(() =>
      useQuickLogMedia({ ensureMoment: async () => "m-1" }),
    );

    act(() => {
      void result.current.attach([file("a.jpg")]);
    });
    await waitFor(() => expect(result.current.pending).toBe(1));

    let cancellationComplete = false;
    let cancellation: Promise<void> | undefined;
    act(() => {
      cancellation = result.current.cancelPending();
      void cancellation.then(() => {
        cancellationComplete = true;
      });
    });
    expect(abort).toHaveBeenCalledTimes(1);
    await Promise.resolve();
    expect(cancellationComplete).toBe(false);

    act(() => {
      rejectUpload?.(new MediaUploadError("aborted", "cancelled"));
    });
    await act(async () => cancellation);
    expect(cancellationComplete).toBe(true);
  });

  it("does not queue media when cancellation happens during moment preparation", async () => {
    let resolveMoment: ((id: string) => void) | undefined;
    const ensureMoment = vi.fn(
      () =>
        new Promise<string>((resolve) => {
          resolveMoment = resolve;
        }),
    );
    const { result } = renderHook(() => useQuickLogMedia({ ensureMoment }));

    let attachment: Promise<void> | undefined;
    act(() => {
      attachment = result.current.attach([file("a.jpg")]);
    });
    await act(async () => result.current.cancelPending());

    act(() => resolveMoment?.("m-1"));
    await act(async () => attachment);
    expect(uploadMock).not.toHaveBeenCalled();
    expect(result.current.items).toHaveLength(0);
  });

  it("surfaces a failed upload and can retry it", async () => {
    uploadMock.mockReturnValueOnce({
      promise: Promise.reject(new MediaUploadError("server", "boom")),
      abort: vi.fn(),
    });
    const { result } = renderHook(() =>
      useQuickLogMedia({ ensureMoment: async () => "m-1" }),
    );
    await act(async () => {
      await result.current.attach([file("a.jpg")]);
    });
    await waitFor(() => expect(result.current.failed).toHaveLength(1));

    uploadMock.mockReturnValueOnce({
      promise: Promise.resolve({ id: "media-2" } as never),
      abort: vi.fn(),
    });
    await act(async () => {
      await result.current.retry(result.current.items[0].uploadId);
    });

    await waitFor(() => expect(result.current.items[0]?.status).toBe("done"));
    expect(result.current.failed).toHaveLength(0);
  });

  it("does not upload when no moment id can be resolved", async () => {
    const { result } = renderHook(() =>
      useQuickLogMedia({ ensureMoment: async () => null }),
    );
    await act(async () => {
      await result.current.attach([file("a.jpg")]);
    });
    expect(uploadMock).not.toHaveBeenCalled();
    expect(result.current.error).not.toBe("");
  });
});
