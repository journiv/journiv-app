import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TIMESLICE_MS } from "./dictationFormat";
import { FakeRecorder, fakeStream } from "./dictationTestKit";
import {
  type RecordedAudio,
  type RecorderStaging,
  useDictationRecorder,
} from "./useDictationRecorder";

let getUserMedia: ReturnType<typeof vi.fn>;
let current: ReturnType<typeof fakeStream>;

beforeEach(() => {
  FakeRecorder.instances = [];
  FakeRecorder.reportedMime = null;
  FakeRecorder.supported = new Set([
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/aac",
  ]);
  current = fakeStream();
  getUserMedia = vi.fn(async () => current.stream);
  vi.stubGlobal("MediaRecorder", FakeRecorder);
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia },
  });
  Object.defineProperty(window, "isSecureContext", {
    configurable: true,
    value: true,
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

const flush = () =>
  act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });

describe("useDictationRecorder availability", () => {
  it("explains an insecure context instead of hiding the feature", () => {
    Object.defineProperty(window, "isSecureContext", {
      configurable: true,
      value: false,
    });
    const { result } = renderHook(() => useDictationRecorder());
    expect(result.current.availability).toMatchObject({
      state: "unavailable",
      reason: "insecure-context",
    });
    expect(
      result.current.availability.state === "unavailable" &&
        result.current.availability.message,
    ).toMatch(/HTTPS/);
  });

  it("is unavailable when no container is supported", () => {
    FakeRecorder.supported = new Set();
    const { result } = renderHook(() => useDictationRecorder());
    expect(result.current.availability).toMatchObject({
      state: "unavailable",
      reason: "unsupported",
    });
  });

  it("is unavailable without MediaRecorder or getUserMedia", () => {
    vi.stubGlobal("MediaRecorder", undefined);
    const { result } = renderHook(() => useDictationRecorder());
    expect(result.current.availability).toMatchObject({
      reason: "unsupported",
    });
  });

  it("start() reports the reason without touching the microphone", async () => {
    Object.defineProperty(window, "isSecureContext", {
      configurable: true,
      value: false,
    });
    const { result } = renderHook(() => useDictationRecorder());
    await act(async () => {
      expect(await result.current.start()).toBe(false);
    });
    expect(getUserMedia).not.toHaveBeenCalled();
    expect(result.current.error?.kind).toBe("insecure-context");
  });
});

describe("useDictationRecorder permission and hardware errors", () => {
  it.each([
    ["NotAllowedError", "permission-denied"],
    ["SecurityError", "permission-denied"],
    ["NotFoundError", "no-microphone"],
    ["AbortError", "failed"],
  ])("%s becomes %s with its own message", async (name, kind) => {
    getUserMedia.mockRejectedValueOnce(new DOMException("nope", name));
    const { result } = renderHook(() => useDictationRecorder());
    await act(async () => {
      expect(await result.current.start()).toBe(false);
    });
    expect(result.current.error?.kind).toBe(kind);
    expect(result.current.error?.message).toBeTruthy();
    expect(result.current.status).toBe("idle");
    act(() => result.current.clearError());
    expect(result.current.error).toBeNull();
  });
});

describe("useDictationRecorder recording", () => {
  it("negotiates webm/opus first, with a timeslice", async () => {
    const { result } = renderHook(() => useDictationRecorder());
    await act(async () => {
      await result.current.start();
    });
    const recorder = FakeRecorder.instances[0];
    expect(recorder?.mimeType).toBe("audio/webm;codecs=opus");
    expect(recorder?.timeslice).toBe(TIMESLICE_MS);
    expect(result.current.status).toBe("recording");
  });

  it("falls back through the preference order", async () => {
    FakeRecorder.supported = new Set(["audio/mp4"]);
    const { result } = renderHook(() => useDictationRecorder());
    await act(async () => {
      await result.current.start();
    });
    expect(FakeRecorder.instances[0]?.mimeType).toBe("audio/mp4");
  });

  it("takes the final MIME from the recorder, not from the request", async () => {
    FakeRecorder.reportedMime = "audio/webm";
    const { result } = renderHook(() => useDictationRecorder());
    await act(async () => {
      await result.current.start();
    });
    let audio: RecordedAudio | null = null;
    await act(async () => {
      audio = await result.current.stop();
    });
    expect((audio as RecordedAudio | null)?.mimeType).toBe("audio/webm");
  });

  it("produces the recording on stop and releases the microphone", async () => {
    const { result } = renderHook(() => useDictationRecorder());
    await act(async () => {
      await result.current.start();
    });
    const recorder = FakeRecorder.instances[0] as FakeRecorder;
    recorder.emit(100);
    recorder.emit(50);
    let audio: RecordedAudio | null = null;
    await act(async () => {
      audio = await result.current.stop();
    });
    const recorded = audio as RecordedAudio | null;
    expect(recorded).not.toBeNull();
    expect(recorded?.chunkCount).toBe(2);
    expect([...(recorded?.unstaged.keys() ?? [])]).toEqual([0, 1]);
    expect(recorded?.staged).toBe(false); // no staging sink was given
    expect(current.track.stop).toHaveBeenCalled();
    expect(result.current.status).toBe("idle");
  });

  it("stops every track when unmounted mid-recording", async () => {
    const { result, unmount } = renderHook(() => useDictationRecorder());
    await act(async () => {
      await result.current.start();
    });
    unmount();
    await flush();
    expect(current.track.stop).toHaveBeenCalled();
  });

  it("stops every track when the recording is discarded", async () => {
    const { result } = renderHook(() => useDictationRecorder());
    await act(async () => {
      await result.current.start();
    });
    await act(async () => {
      await result.current.discard();
    });
    expect(current.track.stop).toHaveBeenCalled();
    expect(result.current.status).toBe("idle");
  });

  it("settles captured audio and releases the microphone if stop throws", async () => {
    const { result } = renderHook(() => useDictationRecorder());
    await act(async () => {
      await result.current.start();
    });
    const recorder = FakeRecorder.instances[0] as FakeRecorder;
    recorder.emit(64);
    vi.spyOn(recorder, "stop").mockImplementationOnce(() => {
      throw new Error("recorder stopped unexpectedly");
    });
    let audio: RecordedAudio | null = null;
    await act(async () => {
      audio = await result.current.stop();
    });
    expect((audio as RecordedAudio | null)?.chunkCount).toBe(1);
    expect(current.track.stop).toHaveBeenCalled();
    expect(result.current.status).toBe("idle");
  });

  it("releases the microphone if discard throws from stop", async () => {
    const { result } = renderHook(() => useDictationRecorder());
    await act(async () => {
      await result.current.start();
    });
    const recorder = FakeRecorder.instances[0] as FakeRecorder;
    vi.spyOn(recorder, "stop").mockImplementationOnce(() => {
      throw new Error("recorder stopped unexpectedly");
    });
    await act(async () => {
      await result.current.discard();
    });
    expect(current.track.stop).toHaveBeenCalled();
    expect(result.current.status).toBe("idle");
  });

  it("keeps what was recorded when the microphone disappears", async () => {
    const onEnded = vi.fn();
    const { result } = renderHook(() => useDictationRecorder({ onEnded }));
    await act(async () => {
      await result.current.start();
    });
    (FakeRecorder.instances[0] as FakeRecorder).emit(64);
    await act(async () => {
      current.track.dispatchEvent(new Event("ended"));
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(onEnded).toHaveBeenCalledTimes(1);
    const audio = onEnded.mock.calls[0]?.[0] as RecordedAudio;
    expect(audio.endedBecause).toBe("interrupted");
    expect(audio.chunkCount).toBe(1);
  });
});

describe("useDictationRecorder staging", () => {
  const sink = (): RecorderStaging & {
    begin: ReturnType<typeof vi.fn>;
    append: ReturnType<typeof vi.fn>;
  } => ({
    begin: vi.fn(async () => undefined),
    append: vi.fn(async () => undefined),
  });

  it("hands each chunk to staging as it arrives, without holding it in memory", async () => {
    const staging = sink();
    const { result } = renderHook(() => useDictationRecorder({ staging }));
    await act(async () => {
      await result.current.start();
    });
    const recorder = FakeRecorder.instances[0] as FakeRecorder;
    expect(staging.begin).toHaveBeenCalledWith(
      expect.objectContaining({ mimeType: "audio/webm;codecs=opus" }),
    );
    recorder.emit(10);
    recorder.emit(20);
    expect(staging.append).toHaveBeenCalledTimes(2);
    expect(staging.append.mock.calls.map((call) => call[0])).toEqual([0, 1]);

    let audio: RecordedAudio | null = null;
    await act(async () => {
      audio = await result.current.stop();
    });
    const recorded = audio as RecordedAudio | null;
    expect(recorded?.staged).toBe(true);
    expect(recorded?.unstaged.size).toBe(0);
  });

  it("keeps a chunk in memory when staging it fails, and says it is not crash-safe", async () => {
    const staging = sink();
    staging.append.mockRejectedValueOnce(new Error("quota"));
    const { result } = renderHook(() => useDictationRecorder({ staging }));
    await act(async () => {
      await result.current.start();
    });
    const recorder = FakeRecorder.instances[0] as FakeRecorder;
    recorder.emit(10);
    await flush(); // the failed write is now known
    recorder.emit(20);
    // Once staging has failed it is not trusted again: later chunks stay in
    // memory rather than being written to a store that just refused one.
    expect(staging.append).toHaveBeenCalledTimes(1);
    let audio: RecordedAudio | null = null;
    await act(async () => {
      audio = await result.current.stop();
    });
    const recorded = audio as RecordedAudio | null;
    expect(recorded?.staged).toBe(false);
    expect([...(recorded?.unstaged.keys() ?? [])]).toEqual([0, 1]);
  });

  it("loses nothing when a failure lands after a later chunk was already staged", async () => {
    const staging = sink();
    staging.append.mockRejectedValueOnce(new Error("quota"));
    const { result } = renderHook(() => useDictationRecorder({ staging }));
    await act(async () => {
      await result.current.start();
    });
    const recorder = FakeRecorder.instances[0] as FakeRecorder;
    recorder.emit(10); // fails
    recorder.emit(20); // already in flight, succeeds
    let audio: RecordedAudio | null = null;
    await act(async () => {
      audio = await result.current.stop();
    });
    const recorded = audio as RecordedAudio | null;
    expect(recorded?.staged).toBe(false);
    // Chunk 0 is held in memory; chunk 1 is in staging. Assembly merges both.
    expect([...(recorded?.unstaged.keys() ?? [])]).toEqual([0]);
  });

  it("records anyway, in memory, when staging cannot begin", async () => {
    const staging = sink();
    staging.begin.mockRejectedValueOnce(new Error("no indexeddb"));
    const { result } = renderHook(() => useDictationRecorder({ staging }));
    await act(async () => {
      expect(await result.current.start()).toBe(true);
    });
    (FakeRecorder.instances[0] as FakeRecorder).emit(10);
    expect(staging.append).not.toHaveBeenCalled();
    let audio: RecordedAudio | null = null;
    await act(async () => {
      audio = await result.current.stop();
    });
    const recorded = audio as RecordedAudio | null;
    expect(recorded?.staged).toBe(false);
    expect(recorded?.unstaged.size).toBe(1);
  });
});

describe("useDictationRecorder duration cap", () => {
  it("derives the cap from the upload limit and stops cleanly, keeping the audio", async () => {
    vi.useFakeTimers();
    const onEnded = vi.fn();
    // 1 MB at 32 kbps, less the margin, is ~200 s.
    const { result } = renderHook(() =>
      useDictationRecorder({ maxFileSizeMb: 1, onEnded }),
    );
    await act(async () => {
      await result.current.start();
    });
    (FakeRecorder.instances[0] as FakeRecorder).emit(10);
    const snapshot = () => result.current.live.getSnapshot();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    const remaining = snapshot().remainingMs;
    expect(remaining).not.toBeNull();
    expect(remaining as number).toBeGreaterThan(190_000);
    expect(remaining as number).toBeLessThan(210_000);
    expect(snapshot().lowTime).toBe(false);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(150_000);
    });
    expect(snapshot().lowTime).toBe(true); // last minute warning

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(onEnded).toHaveBeenCalledTimes(1);
    const audio = onEnded.mock.calls[0]?.[0] as RecordedAudio;
    expect(audio.endedBecause).toBe("limit");
    expect(audio.chunkCount).toBe(1); // kept, not discarded
    expect(current.track.stop).toHaveBeenCalled();
  });

  it("stops when the recorded bytes reach the limit even before the clock does", async () => {
    const onEnded = vi.fn();
    const { result } = renderHook(() =>
      useDictationRecorder({ maxFileSizeMb: 1, onEnded }),
    );
    await act(async () => {
      await result.current.start();
    });
    await act(async () => {
      (FakeRecorder.instances[0] as FakeRecorder).emit(900_000);
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(onEnded).toHaveBeenCalledTimes(1);
    const ended = onEnded.mock.calls[0]?.[0] as RecordedAudio;
    expect(ended.endedBecause).toBe("limit");
  });

  it("is uncapped, not invented, when the limit is unknown", async () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useDictationRecorder());
    await act(async () => {
      await result.current.start();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(result.current.live.getSnapshot().remainingMs).toBeNull();
    expect(result.current.status).toBe("recording");
  });
});

/** A promise the test settles by hand, to hold a start half way. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const microtasks = () =>
  act(async () => {
    for (let i = 0; i < 8; i += 1) await Promise.resolve();
  });

describe("useDictationRecorder cancelling a start", () => {
  // The Stop and Discard controls are reachable while the recorder is still
  // starting: the permission prompt can stay open indefinitely, and staging opens
  // IndexedDB before recording begins. There is nothing to stop or discard then —
  // only a start to abandon, which must never go on to record.

  it("Stop while the permission prompt is open cancels the start", async () => {
    const prompt = deferred<MediaStream>();
    getUserMedia.mockImplementationOnce(() => prompt.promise);
    const { result } = renderHook(() => useDictationRecorder());

    let started: boolean | undefined;
    let pending: Promise<boolean> = Promise.resolve(false);
    act(() => {
      pending = result.current.start().then((value) => {
        started = value;
        return value;
      });
    });
    await microtasks();
    expect(getUserMedia).toHaveBeenCalledTimes(1);
    expect(result.current.status).toBe("starting");
    expect(result.current.isStarting()).toBe(true);

    let audio: RecordedAudio | null | undefined;
    await act(async () => {
      audio = await result.current.stop();
    });
    // Back to idle straight away: the writer is not left looking at a dead control.
    expect(audio).toBeNull();
    expect(result.current.status).toBe("idle");
    expect(result.current.isStarting()).toBe(false);

    // The prompt is answered afterwards. The microphone is released, not recorded.
    await act(async () => {
      prompt.resolve(current.stream);
      await pending;
    });
    expect(started).toBe(false);
    expect(current.track.stop).toHaveBeenCalled();
    expect(FakeRecorder.instances).toHaveLength(0);
    expect(result.current.status).toBe("idle");
  });

  it("Discard while the permission prompt is open never goes on to record", async () => {
    const prompt = deferred<MediaStream>();
    getUserMedia.mockImplementationOnce(() => prompt.promise);
    const { result } = renderHook(() => useDictationRecorder());
    let pending: Promise<boolean> = Promise.resolve(false);
    act(() => {
      pending = result.current.start();
    });
    await microtasks();
    expect(getUserMedia).toHaveBeenCalledTimes(1);

    await act(async () => {
      await result.current.discard();
    });
    expect(result.current.status).toBe("idle");

    await act(async () => {
      prompt.resolve(current.stream);
      await pending;
    });
    // Previously the start carried on regardless and left the microphone open.
    expect(await pending).toBe(false);
    expect(current.track.stop).toHaveBeenCalled();
    expect(FakeRecorder.instances).toHaveLength(0);
    expect(result.current.status).toBe("idle");
  });

  it("cancelling while staging opens releases the microphone and never starts the recorder", async () => {
    const begin = deferred<void>();
    const staging: RecorderStaging = {
      begin: vi.fn(() => begin.promise),
      append: vi.fn(async () => undefined),
    };
    const { result } = renderHook(() => useDictationRecorder({ staging }));
    let pending: Promise<boolean> = Promise.resolve(false);
    act(() => {
      pending = result.current.start();
    });
    await microtasks();
    expect(getUserMedia).toHaveBeenCalledTimes(1);
    await microtasks(); // the prompt is answered; staging is now opening
    expect(staging.begin).toHaveBeenCalledTimes(1);
    expect(result.current.status).toBe("starting");

    await act(async () => {
      await result.current.stop();
    });
    expect(result.current.status).toBe("idle");

    await act(async () => {
      begin.resolve();
      await pending;
    });
    expect(await pending).toBe(false);
    expect(current.track.stop).toHaveBeenCalled();
    // The recorder object existed, but was never started and never published.
    expect(FakeRecorder.instances[0]?.timeslice).toBeUndefined();
    expect(FakeRecorder.instances[0]?.state).toBe("inactive");
    expect(result.current.status).toBe("idle");
    // With nothing published, a later Stop has nothing to do.
    await act(async () => {
      expect(await result.current.stop()).toBeNull();
    });
  });

  it("a start cancelled before the prompt is even raised never asks for the microphone", async () => {
    const { result } = renderHook(() => useDictationRecorder());
    let pending: Promise<boolean> = Promise.resolve(true);
    act(() => {
      pending = result.current.start();
    });
    await act(async () => {
      await result.current.discard();
      await pending;
    });
    expect(await pending).toBe(false);
    expect(getUserMedia).not.toHaveBeenCalled();
    expect(FakeRecorder.instances).toHaveLength(0);
    expect(result.current.status).toBe("idle");
  });

  it("does not report an error for a prompt that fails after it was cancelled", async () => {
    const prompt = deferred<MediaStream>();
    getUserMedia.mockImplementationOnce(() => prompt.promise);
    const { result } = renderHook(() => useDictationRecorder());
    let pending: Promise<boolean> = Promise.resolve(false);
    act(() => {
      pending = result.current.start();
    });
    await microtasks();
    expect(getUserMedia).toHaveBeenCalledTimes(1);
    await act(async () => {
      await result.current.stop();
    });
    await act(async () => {
      prompt.reject(new DOMException("blocked", "NotAllowedError"));
      await pending;
    });
    expect(result.current.error).toBeNull();
    expect(result.current.status).toBe("idle");
  });

  it("a new start after cancelling waits for the old prompt, then records", async () => {
    const first = fakeStream();
    const second = fakeStream();
    const prompt = deferred<MediaStream>();
    getUserMedia
      .mockImplementationOnce(() => prompt.promise)
      .mockImplementationOnce(async () => second.stream);
    const { result } = renderHook(() => useDictationRecorder());

    let firstStart: Promise<boolean> = Promise.resolve(false);
    act(() => {
      firstStart = result.current.start();
    });
    await microtasks();
    expect(getUserMedia).toHaveBeenCalledTimes(1);
    await act(async () => {
      await result.current.stop();
    });
    expect(result.current.status).toBe("idle");

    // Pressed again while the first prompt is still on screen.
    let secondStart: Promise<boolean> = Promise.resolve(false);
    act(() => {
      secondStart = result.current.start();
    });
    expect(result.current.status).toBe("starting");
    await microtasks();
    // It has not asked for a second microphone: the first request is still open.
    expect(getUserMedia).toHaveBeenCalledTimes(1);

    await act(async () => {
      prompt.resolve(first.stream);
      await firstStart;
      await secondStart;
    });
    expect(await firstStart).toBe(false);
    expect(await secondStart).toBe(true);
    expect(first.track.stop).toHaveBeenCalled(); // the cancelled one, released
    expect(second.track.stop).not.toHaveBeenCalled(); // the live one, still open
    expect(getUserMedia).toHaveBeenCalledTimes(2);
    expect(result.current.status).toBe("recording");
    expect(FakeRecorder.instances).toHaveLength(1);
    expect(FakeRecorder.instances[0]?.stream).toBe(second.stream);
  });

  it("leaving the editor mid-start releases the microphone once it arrives", async () => {
    const prompt = deferred<MediaStream>();
    getUserMedia.mockImplementationOnce(() => prompt.promise);
    const { result, unmount } = renderHook(() => useDictationRecorder());
    let pending: Promise<boolean> = Promise.resolve(false);
    act(() => {
      pending = result.current.start();
    });
    await microtasks();
    expect(getUserMedia).toHaveBeenCalledTimes(1);
    unmount();
    prompt.resolve(current.stream);
    expect(await pending).toBe(false);
    expect(current.track.stop).toHaveBeenCalled();
    expect(FakeRecorder.instances).toHaveLength(0);
  });

  it("refuses a second start while one is in flight, without disturbing it", async () => {
    const prompt = deferred<MediaStream>();
    getUserMedia.mockImplementationOnce(() => prompt.promise);
    const { result } = renderHook(() => useDictationRecorder());
    let firstStart: Promise<boolean> = Promise.resolve(false);
    act(() => {
      firstStart = result.current.start();
    });
    await microtasks();
    expect(getUserMedia).toHaveBeenCalledTimes(1);
    await act(async () => {
      expect(await result.current.start()).toBe(false);
    });
    expect(getUserMedia).toHaveBeenCalledTimes(1);
    await act(async () => {
      prompt.resolve(current.stream);
      await firstStart;
    });
    expect(await firstStart).toBe(true);
    expect(result.current.status).toBe("recording");
  });
});
