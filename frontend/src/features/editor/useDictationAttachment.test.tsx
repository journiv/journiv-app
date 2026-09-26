import { QueryClient } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client/api";
import { queryKeys } from "../../api/query/keys";
import { MediaUploadError, uploadMedia } from "./mediaUpload";
import { useDictationAttachment } from "./useDictationAttachment";

vi.mock("../../api/client/api", () => ({
  api: { momentMedia: vi.fn(), deleteMedia: vi.fn() },
}));
vi.mock("./mediaUpload", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./mediaUpload")>()),
  uploadMedia: vi.fn(),
}));

const upload = vi.mocked(uploadMedia);
const file = () =>
  new File(["audio"], "dictation.webm", { type: "audio/webm" });
const anchor = { index: 3, before: "ab", after: "cd" };

function setup(ensureDraft = vi.fn(async () => ({ momentId: "m-1" }))) {
  const queryClient = new QueryClient();
  const invalidate = vi.spyOn(queryClient, "invalidateQueries");
  const onUploaded = vi.fn();
  const hook = renderHook(() =>
    useDictationAttachment({ ensureDraft, queryClient, onUploaded }),
  );
  return { ...hook, ensureDraft, invalidate, onUploaded };
}

beforeEach(() => vi.clearAllMocks());

describe("useDictationAttachment", () => {
  it("uploads through the shared transport into the ensured Moment", async () => {
    upload.mockReturnValue({
      promise: Promise.resolve({ id: "media-1" } as never),
      abort: vi.fn(),
    });
    const { result, onUploaded, ensureDraft } = setup();

    await act(async () => {
      await result.current.attach(file(), { sessionId: "s-1", anchor });
    });

    expect(ensureDraft).toHaveBeenCalledTimes(1);
    expect(upload).toHaveBeenCalledWith(
      expect.objectContaining({ momentId: "m-1" }),
    );
    expect(onUploaded).toHaveBeenCalledWith(
      expect.objectContaining({
        momentId: "m-1",
        media: { id: "media-1" },
        item: expect.objectContaining({ sessionId: "s-1", anchor }),
      }),
    );
    // A finished upload leaves no item behind: the tray owns it from here.
    expect(result.current.items).toEqual([]);
    expect(result.current.pending).toBe(0);
  });

  it("nudges the Moment's queries once instead of polling", async () => {
    upload.mockReturnValue({
      promise: Promise.resolve({ id: "media-1" } as never),
      abort: vi.fn(),
    });
    const { result, invalidate } = setup();
    await act(async () => {
      await result.current.attach(file(), { sessionId: null, anchor: null });
    });
    expect(invalidate).toHaveBeenCalledTimes(1);
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: queryKeys.moment("m-1"),
    });
    // The media list is a child of that key, so this covers it too.
    expect(queryKeys.momentMedia("m-1").slice(0, 2)).toEqual(
      queryKeys.moment("m-1"),
    );
    // No second poll of our own.
    expect(api.momentMedia).not.toHaveBeenCalled();
  });

  it("reports a failed upload with a retry that succeeds", async () => {
    upload.mockImplementationOnce(() => ({
      promise: Promise.reject(new MediaUploadError("network", "x")),
      abort: vi.fn(),
    }));
    const { result, onUploaded } = setup();
    await act(async () => {
      await result.current.attach(file(), { sessionId: "s-1", anchor });
    });
    expect(result.current.failed).toHaveLength(1);
    expect(result.current.failed[0]?.message).toMatch(/Upload failed/);
    expect(onUploaded).not.toHaveBeenCalled();

    upload.mockReturnValueOnce({
      promise: Promise.resolve({ id: "media-2" } as never),
      abort: vi.fn(),
    });
    await act(async () => {
      await result.current.retry(result.current.failed[0]?.uploadId as string);
    });
    await waitFor(() => expect(onUploaded).toHaveBeenCalledTimes(1), {
      timeout: 10_000,
    });
    expect(result.current.items).toEqual([]);
  });

  it("says the recording is kept when the server refuses its size", async () => {
    upload.mockImplementation(() => ({
      promise: Promise.reject(new MediaUploadError("too-large", "x")),
      abort: vi.fn(),
    }));
    const { result } = setup();
    await act(async () => {
      await result.current.attach(file(), { sessionId: "s-1", anchor });
    });
    expect(result.current.failed[0]?.message).toMatch(/kept on this device/);
  });

  it("keeps a retryable item when the entry cannot be prepared", async () => {
    const { result } = setup(vi.fn(async () => null as never));
    let accepted: boolean | undefined;
    await act(async () => {
      accepted = await result.current.attach(file(), {
        sessionId: "s-1",
        anchor,
      });
    });
    expect(accepted).toBe(false);
    expect(upload).not.toHaveBeenCalled();
    expect(result.current.failed).toHaveLength(1);
    expect(result.current.failed[0]?.message).toMatch(/kept on this device/);
  });

  it("keeps the voice note retryable when preparing the entry throws", async () => {
    const ensureDraft = vi
      .fn()
      .mockRejectedValueOnce(new Error("offline"))
      .mockRejectedValueOnce(new Error("still offline"))
      .mockResolvedValue({ momentId: "m-1" });
    const { result } = setup(ensureDraft);
    await act(async () => {
      expect(
        await result.current.attach(file(), { sessionId: "s-1", anchor }),
      ).toBe(false);
    });
    expect(result.current.pending).toBe(0);
    expect(result.current.failed[0]?.message).toMatch(/kept on this device/);

    const uploadId = result.current.failed[0]?.uploadId as string;
    await act(async () => {
      await result.current.retry(uploadId);
    });
    expect(result.current.failed[0]?.message).toMatch(/kept on this device/);

    upload.mockReturnValueOnce({
      promise: Promise.resolve({ id: "media-2" } as never),
      abort: vi.fn(),
    });
    await act(async () => {
      await result.current.retry(uploadId);
    });
    expect(result.current.items).toEqual([]);
  });

  it("does not report success for an aborted upload", async () => {
    upload.mockImplementation(() => ({
      promise: Promise.reject(new MediaUploadError("aborted", "x")),
      abort: vi.fn(),
    }));
    const { result, onUploaded } = setup();
    await act(async () => {
      await result.current.attach(file(), { sessionId: "s-1", anchor });
    });
    expect(onUploaded).not.toHaveBeenCalled();
    expect(result.current.items).toEqual([]);
  });

  it("aborts uploads in flight on cancelAll and on unmount", async () => {
    const abort = vi.fn();
    upload.mockReturnValue({ promise: new Promise(() => undefined), abort });
    const { result, unmount } = setup();
    act(() => {
      void result.current.attach(file(), { sessionId: null, anchor: null });
    });
    await waitFor(() => expect(upload).toHaveBeenCalled(), { timeout: 10_000 });
    expect(result.current.pending).toBe(1);
    act(() => result.current.cancelAll());
    expect(abort).toHaveBeenCalledTimes(1);
    unmount();
    expect(abort).toHaveBeenCalledTimes(2);
  });

  it("does not start a late upload after cancellation while the draft is preparing", async () => {
    let finishDraft: (value: { momentId: string }) => void = () => undefined;
    const ensureDraft = vi.fn(
      () =>
        new Promise<{ momentId: string }>((resolve) => {
          finishDraft = resolve;
        }),
    );
    const { result } = setup(ensureDraft);
    let pending: Promise<boolean> = Promise.resolve(true);
    act(() => {
      pending = result.current.attach(file(), { sessionId: "s-1", anchor });
    });
    act(() => result.current.cancelAll());
    await act(async () => {
      finishDraft({ momentId: "m-1" });
      expect(await pending).toBe(false);
    });
    expect(upload).not.toHaveBeenCalled();
    expect(result.current.items).toEqual([]);
  });
});
