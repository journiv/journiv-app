import { QueryClient } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FakeRecorder, fakeStream } from "./dictationTestKit";
import { MediaUploadError, uploadMedia } from "./mediaUpload";
import type { QuillSurfaceHandle } from "./QuillSurface";
import { recordingRepository } from "./recordingRepository";
import { useDictation } from "./useDictation";

vi.mock("../../api/client/api", () => ({
  api: { momentMedia: vi.fn(), deleteMedia: vi.fn() },
}));
vi.mock("./mediaUpload", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./mediaUpload")>()),
  uploadMedia: vi.fn(),
}));

const upload = vi.mocked(uploadMedia);
const USER = "user-1";
const KEY = "user-1:new:abc";

/**
 * A writing surface that records every call. Dictation may only ever *read* it;
 * a call to anything that changes the document fails the test.
 */
function surface(
  initial = { index: 12, before: "It was raining", after: " and cold" },
) {
  const calls: string[] = [];
  const state = { ...initial };
  const handle = new Proxy({} as Record<string, unknown>, {
    get:
      (_target, name: string) =>
      (...args: unknown[]) => {
        calls.push(name);
        if (name === "getSelectionIndex") return state.index;
        if (name === "getTextAround")
          return { before: state.before, after: state.after };
        void args;
        return undefined;
      },
  }) as unknown as QuillSurfaceHandle;
  return { handle, calls, state };
}

let current: ReturnType<typeof fakeStream>;
const flush = async () => {
  for (let i = 0; i < 6; i += 1) await Promise.resolve();
};

beforeEach(() => {
  vi.clearAllMocks();
  FakeRecorder.instances = [];
  current = fakeStream();
  vi.stubGlobal("MediaRecorder", FakeRecorder);
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia: vi.fn(async () => current.stream) },
  });
  Object.defineProperty(window, "isSecureContext", {
    configurable: true,
    value: true,
  });
});
afterEach(() => vi.unstubAllGlobals());

function setup(
  over: {
    draftKey?: string | null;
    ensureDraft?: () => Promise<{ momentId: string } | null>;
  } = {},
) {
  const s = surface();
  const onMediaAdded = vi.fn();
  const onAttached = vi.fn();
  const ensureDraft =
    over.ensureDraft ?? vi.fn(async () => ({ momentId: "m-1" }));
  const queryClient = new QueryClient();
  const hook = renderHook(() =>
    useDictation({
      surfaceRef: { current: s.handle },
      ensureDraft,
      queryClient,
      userId: USER,
      draftKey: over.draftKey === undefined ? KEY : over.draftKey,
      maxFileSizeMb: 100,
      onMediaAdded,
      onAttached,
    }),
  );
  return { ...hook, s, onMediaAdded, onAttached, ensureDraft };
}

async function record(
  result: { current: ReturnType<typeof useDictation> },
  bytes = [100, 50],
) {
  await act(async () => {
    await result.current.start();
  });
  const recorder = FakeRecorder.instances[0] as FakeRecorder;
  for (const size of bytes) recorder.emit(size);
  await act(async () => {
    await flush();
  });
}

describe("useDictation", () => {
  it("uploads the recording as a Moment attachment and never touches the document", async () => {
    upload.mockReturnValue({
      promise: Promise.resolve({ id: "media-1" } as never),
      abort: vi.fn(),
    });
    const { result, s, onMediaAdded, onAttached } = setup();

    await record(result);
    await act(async () => {
      await result.current.stop();
    });

    const sent = upload.mock.calls[0]?.[0];
    expect(sent?.momentId).toBe("m-1");
    expect(sent?.file.type).toBe("audio/webm;codecs=opus");
    expect(sent?.file.name).toMatch(/^voice-note-.*\.webm$/);
    expect(sent?.file.size).toBe(150);
    expect(onMediaAdded).toHaveBeenCalledWith("media-1");
    expect(onAttached).toHaveBeenCalledTimes(1);

    // Only reads: no placeholder, no embed, no edit of any kind.
    expect(new Set(s.calls)).toEqual(
      new Set(["getSelectionIndex", "getTextAround"]),
    );
  });

  it("captures the anchor when recording starts, not when it stops", async () => {
    upload.mockReturnValue({
      promise: Promise.resolve({ id: "media-1" } as never),
      abort: vi.fn(),
    });
    const { result, s } = setup();
    await act(async () => {
      await result.current.start();
    });
    // The caret moves while the writer talks.
    s.state.index = 99;
    s.state.before = "something else entirely";
    (FakeRecorder.instances[0] as FakeRecorder).emit(10);
    await act(async () => {
      await result.current.stop();
    });

    // The anchor survives to upload completion, keyed by the media id.
    await waitFor(
      async () => {
        expect(await recordingRepository.readAnchor("media-1")).toMatchObject({
          momentId: "m-1",
          draftKey: KEY,
          anchor: { index: 12, before: "It was raining", after: " and cold" },
        });
      },
      { timeout: 10_000 },
    );
  });

  it("stages chunks while recording and deletes them only after the upload succeeds", async () => {
    let finish: (value: never) => void = () => undefined;
    upload.mockReturnValue({
      promise: new Promise((resolve) => {
        finish = resolve as never;
      }),
      abort: vi.fn(),
    });
    const { result } = setup();
    await record(result);

    // Mid-recording the audio is already durable.
    expect(await recordingRepository.listUnfinished(USER)).toHaveLength(1);
    expect(result.current.crashSafe).toBe(true);

    await act(async () => {
      void result.current.stop();
      await flush();
    });
    // Uploading: still staged.
    await waitFor(() => expect(upload).toHaveBeenCalled(), { timeout: 10_000 });
    expect(await recordingRepository.listUnfinished(USER)).toHaveLength(1);
    expect(result.current.phase).toBe("uploading");

    await act(async () => {
      finish({ id: "media-1" } as never);
      await flush();
    });
    await waitFor(
      async () =>
        expect(await recordingRepository.listUnfinished(USER)).toHaveLength(0),
      { timeout: 10_000 },
    );
  });

  it("keeps the anchor once the staged audio is gone, and drops it only with the media", async () => {
    upload.mockReturnValue({
      promise: Promise.resolve({ id: "media-1" } as never),
      abort: vi.fn(),
    });
    const { result } = setup();
    await record(result);
    await act(async () => {
      await result.current.stop();
    });
    await waitFor(
      async () =>
        expect(await recordingRepository.listUnfinished(USER)).toHaveLength(0),
      { timeout: 10_000 },
    );

    // The staged audio is deleted; the anchor deliberately is not.
    expect(await recordingRepository.readAnchor("media-1")).not.toBeNull();

    // While the media is on the Moment the anchor stays, however far ahead the
    // list is fetched...
    const later = Date.now() + 24 * 3600_000;
    expect(
      await recordingRepository.pruneAnchors(
        "m-1",
        new Set(["media-1"]),
        later,
      ),
    ).toBe(0);
    expect(await recordingRepository.readAnchor("media-1")).not.toBeNull();

    // ...and it goes when the media does.
    expect(
      await recordingRepository.pruneAnchors("m-1", new Set(), later),
    ).toBe(1);
    expect(await recordingRepository.readAnchor("media-1")).toBeNull();
  });

  it("keeps a failed upload recoverable, then recovers it after a reload", async () => {
    upload.mockImplementationOnce(() => ({
      promise: Promise.reject(new MediaUploadError("network", "x")),
      abort: vi.fn(),
    }));
    const first = setup();
    await record(first.result);
    await act(async () => {
      await first.result.current.stop();
    });
    await waitFor(
      () => expect(first.result.current.uploads.failed).toHaveLength(1),
      { timeout: 10_000 },
    );
    // The upload failed, so the audio is still on this device.
    const staged = await recordingRepository.listUnfinished(USER);
    expect(staged).toHaveLength(1);
    first.unmount();

    // A new page load: the unfinished recording is offered back.
    upload.mockReturnValueOnce({
      promise: Promise.resolve({ id: "media-9" } as never),
      abort: vi.fn(),
    });
    const second = setup();
    await waitFor(
      () => expect(second.result.current.recoverable).toHaveLength(1),
      { timeout: 10_000 },
    );
    const offered = second.result.current.recoverable[0];
    expect(offered?.anchor).toMatchObject({ index: 12 });

    await act(async () => {
      await second.result.current.recover(offered?.id as string);
    });
    expect(upload).toHaveBeenLastCalledWith(
      expect.objectContaining({ momentId: "m-1" }),
    );
    expect(upload.mock.calls.at(-1)?.[0].file.size).toBe(150);
    await waitFor(
      async () =>
        expect(await recordingRepository.listUnfinished(USER)).toHaveLength(0),
      { timeout: 10_000 },
    );
    expect(second.onMediaAdded).toHaveBeenCalledWith("media-9");
  });

  it("only offers recordings that belong to this entry", async () => {
    await recordingRepository.createSession({
      id: "other",
      userId: USER,
      draftKey: "user-1:entry:someone-elses",
      mimeType: "audio/webm",
      startedAt: "2026-09-19T10:00:00.000Z",
      updatedAt: "2026-09-19T10:00:00.000Z",
      durationMs: 1000,
      chunkCount: 1,
      status: "stopped",
      anchor: { index: 0, before: "", after: "" },
    });
    const { result } = setup();
    await act(async () => {
      await flush();
    });
    expect(result.current.recoverable).toEqual([]);
  });

  it("discarding a failed upload deletes its staged copy", async () => {
    upload.mockImplementationOnce(() => ({
      promise: Promise.reject(new MediaUploadError("server", "x")),
      abort: vi.fn(),
    }));
    const { result } = setup();
    await record(result);
    await act(async () => {
      await result.current.stop();
    });
    await waitFor(() => expect(result.current.uploads.failed).toHaveLength(1), {
      timeout: 10_000,
    });
    await act(async () => {
      await result.current.discardFailed(
        result.current.uploads.failed[0]?.uploadId as string,
      );
    });
    expect(result.current.uploads.failed).toHaveLength(0);
    expect(await recordingRepository.listUnfinished(USER)).toHaveLength(0);
  });

  it("discarding a recording removes its staged copy and releases the microphone", async () => {
    const { result } = setup();
    await record(result);
    expect(await recordingRepository.listUnfinished(USER)).toHaveLength(1);
    await act(async () => {
      await result.current.discard();
    });
    expect(await recordingRepository.listUnfinished(USER)).toHaveLength(0);
    expect(current.track.stop).toHaveBeenCalled();
    expect(upload).not.toHaveBeenCalled();
    expect(result.current.phase).toBe("idle");
  });

  it("records without staging when there is no draft key, and says it is not crash-safe", async () => {
    upload.mockReturnValue({
      promise: Promise.resolve({ id: "media-1" } as never),
      abort: vi.fn(),
    });
    const { result } = setup({ draftKey: null });
    await record(result);
    expect(result.current.crashSafe).toBe(false);
    await act(async () => {
      await result.current.stop();
    });
    // The audio still reached the upload, assembled from memory.
    expect(upload.mock.calls[0]?.[0].file.size).toBe(150);
  });

  it("never uploads a partial file when staged chunks cannot be read", async () => {
    const { result } = setup();
    await record(result);
    const assemble = vi
      .spyOn(recordingRepository, "assemble")
      .mockRejectedValueOnce(new Error("IndexedDB read failed"));
    try {
      await act(async () => {
        await result.current.stop();
      });
      expect(upload).not.toHaveBeenCalled();
      expect(result.current.notice).toMatch(/full voice note couldn’t be read/);
      expect(await recordingRepository.listUnfinished(USER)).toHaveLength(1);
      expect(result.current.recoverable).toHaveLength(1);
    } finally {
      assemble.mockRestore();
    }
  });

  it("says so when nothing was captured", async () => {
    const { result } = setup();
    await act(async () => {
      await result.current.start();
    });
    await act(async () => {
      await result.current.stop();
    });
    expect(upload).not.toHaveBeenCalled();
    expect(result.current.notice).toMatch(/Nothing was recorded/);
    expect(await recordingRepository.listUnfinished(USER)).toHaveLength(0);
  });

  it("stops at the limit and still uploads what was recorded", async () => {
    upload.mockReturnValue({
      promise: Promise.resolve({ id: "media-1" } as never),
      abort: vi.fn(),
    });
    const s = surface();
    const queryClient = new QueryClient();
    const { result } = renderHook(() =>
      useDictation({
        surfaceRef: { current: s.handle },
        ensureDraft: async () => ({ momentId: "m-1" }),
        queryClient,
        userId: USER,
        draftKey: KEY,
        maxFileSizeMb: 1,
        onMediaAdded: vi.fn(),
        onAttached: vi.fn(),
      }),
    );
    await act(async () => {
      await result.current.start();
    });
    await act(async () => {
      (FakeRecorder.instances[0] as FakeRecorder).emit(900_000);
      await flush();
    });
    await waitFor(() => expect(upload).toHaveBeenCalled(), { timeout: 10_000 });
    expect(result.current.notice).toMatch(/largest size/);
    expect(current.track.stop).toHaveBeenCalled();
  });

  it("reports a recorder error without recording", async () => {
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        getUserMedia: vi.fn(async () => {
          throw new DOMException("no", "NotAllowedError");
        }),
      },
    });
    const { result } = setup();
    await act(async () => {
      expect(await result.current.start()).toBe(false);
    });
    expect(result.current.error?.kind).toBe("permission-denied");
    expect(await recordingRepository.listUnfinished(USER)).toHaveLength(0);
  });
});

describe("useDictation cancelling a start", () => {
  const holdPrompt = () => {
    let resolve!: (stream: MediaStream) => void;
    const promise = new Promise<MediaStream>((res) => {
      resolve = res;
    });
    vi.mocked(navigator.mediaDevices.getUserMedia).mockImplementationOnce(
      () => promise,
    );
    return resolve;
  };
  const flush = async () => {
    for (let i = 0; i < 10; i += 1) await Promise.resolve();
  };
  const databaseNames = async () =>
    (await indexedDB.databases()).map((info) => info.name);

  it("leaves nothing behind when Stop is pressed while the prompt is open", async () => {
    const answer = holdPrompt();
    const { result } = setup();
    let start: Promise<boolean> = Promise.resolve(true);
    await act(async () => {
      start = result.current.start();
      await flush();
    });
    expect(result.current.phase).toBe("starting");

    await act(async () => {
      await result.current.stop();
    });
    expect(result.current.phase).toBe("idle");

    await act(async () => {
      answer(current.stream);
      await start;
    });
    expect(await start).toBe(false);
    expect(current.track.stop).toHaveBeenCalled(); // the microphone is released
    expect(upload).not.toHaveBeenCalled();
    expect(result.current.recoverable).toEqual([]);
    // No recording was made, so no database was created to hold one.
    expect(await databaseNames()).not.toContain("journiv-recordings");
  });

  it("Discard while the prompt is open does not start recording afterwards", async () => {
    const answer = holdPrompt();
    const { result } = setup();
    let start: Promise<boolean> = Promise.resolve(true);
    await act(async () => {
      start = result.current.start();
      await flush();
    });
    await act(async () => {
      await result.current.discard();
    });
    await act(async () => {
      answer(current.stream);
      await start;
    });
    expect(await start).toBe(false);
    expect(current.track.stop).toHaveBeenCalled();
    expect(FakeRecorder.instances[0]?.timeslice).toBeUndefined();
    expect(result.current.phase).toBe("idle");
    expect(await databaseNames()).not.toContain("journiv-recordings");
  });

  it("deletes the staged session a start created before it was cancelled", async () => {
    let release!: () => void;
    const gate = new Promise<void>((res) => {
      release = res;
    });
    const create = recordingRepository.createSession.bind(recordingRepository);
    const spy = vi
      .spyOn(recordingRepository, "createSession")
      .mockImplementation(async (session) => {
        await gate; // staging is still opening while the writer cancels
        await create(session);
      });
    try {
      const { result } = setup();
      let start: Promise<boolean> = Promise.resolve(true);
      await act(async () => {
        start = result.current.start();
        await flush();
      });
      expect(spy).toHaveBeenCalledTimes(1);

      await act(async () => {
        await result.current.stop();
      });
      await act(async () => {
        release();
        await start;
      });
      expect(await start).toBe(false);
      // The session was written by then, and must not survive as an "unfinished
      // recording" that recovery would offer with nothing in it.
      expect(await recordingRepository.listUnfinished(USER)).toHaveLength(0);
      expect(current.track.stop).toHaveBeenCalled();
      expect(FakeRecorder.instances[0]?.state).toBe("inactive");
    } finally {
      spy.mockRestore();
    }
  });

  it("pressing record while already recording is refused and disturbs nothing", async () => {
    upload.mockReturnValue({
      promise: Promise.resolve({ id: "media-1" } as never),
      abort: vi.fn(),
    });
    const { result } = setup();
    await record(result);
    await act(async () => {
      expect(await result.current.start()).toBe(false);
    });
    // The live session is intact: stopping still assembles and uploads it.
    expect(result.current.recording).toBe(true);
    await act(async () => {
      await result.current.stop();
    });
    await waitFor(() => expect(upload).toHaveBeenCalledTimes(1), {
      timeout: 10_000,
    });
    expect(upload.mock.calls[0]?.[0].file.size).toBe(150);
  });

  it("does not count a start still waiting on the microphone as a recording", async () => {
    holdPrompt();
    const { result } = setup();
    await act(async () => {
      void result.current.start();
      await flush();
    });
    // Nothing is captured yet: Done must not be blocked, nor Cancel warn about
    // losing a recording.
    expect(result.current.starting).toBe(true);
    expect(result.current.recording).toBe(false);
    await act(async () => {
      await result.current.stop();
    });
  });
});
