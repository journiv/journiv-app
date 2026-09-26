import { describe, expect, it } from "vitest";
import {
  anchorMatches,
  baseMimeType,
  extensionForMime,
  formatDuration,
  maxRecordingMs,
  pickRecorderMime,
  RECORDER_MIME_PREFERENCE,
  RollingPeaks,
  SIZE_SAFETY_MARGIN,
} from "./dictationFormat";

describe("pickRecorderMime", () => {
  it("prefers webm/opus, then webm, mp4 and aac, in that order", () => {
    expect(pickRecorderMime(() => true)).toBe("audio/webm;codecs=opus");
    expect(pickRecorderMime((t) => t !== "audio/webm;codecs=opus")).toBe(
      "audio/webm",
    );
    expect(
      pickRecorderMime((t) => t === "audio/mp4" || t === "audio/aac"),
    ).toBe("audio/mp4");
    expect(pickRecorderMime((t) => t === "audio/aac")).toBe("audio/aac");
  });

  it("probes in the documented order", () => {
    const seen: string[] = [];
    pickRecorderMime((type) => {
      seen.push(type);
      return false;
    });
    expect(seen).toEqual([...RECORDER_MIME_PREFERENCE]);
  });

  it("returns null rather than guessing when nothing is supported", () => {
    expect(pickRecorderMime(() => false)).toBeNull();
  });
});

describe("mime helpers", () => {
  it("strips codec parameters", () => {
    expect(baseMimeType("audio/webm;codecs=opus")).toBe("audio/webm");
    expect(baseMimeType("Audio/MP4")).toBe("audio/mp4");
  });

  it("chooses the extension from the actual container", () => {
    expect(extensionForMime("audio/webm;codecs=opus")).toBe("webm");
    expect(extensionForMime("audio/mp4")).toBe("m4a");
    expect(extensionForMime("audio/aac")).toBe("aac");
  });
});

describe("maxRecordingMs", () => {
  it("derives the cap from the upload limit and bitrate with a margin", () => {
    // 100 MB at 32 kbps (4000 B/s), less the safety margin.
    const expected = Math.floor(
      ((100 * 1024 * 1024 * SIZE_SAFETY_MARGIN) / 4000) * 1000,
    );
    expect(maxRecordingMs(100, 32_000)).toBe(expected);
  });

  it("scales with the limit and the bitrate", () => {
    const base = maxRecordingMs(10, 32_000) ?? 0;
    expect(maxRecordingMs(20, 32_000)).toBeGreaterThan(base);
    expect(maxRecordingMs(10, 64_000)).toBeLessThan(base);
  });

  it("is null, not invented, when the limit is unknown", () => {
    expect(maxRecordingMs(undefined, 32_000)).toBeNull();
    expect(maxRecordingMs(null, 32_000)).toBeNull();
    expect(maxRecordingMs(0, 32_000)).toBeNull();
    expect(maxRecordingMs(100, 0)).toBeNull();
  });
});

describe("formatDuration", () => {
  it("formats minutes and hours", () => {
    expect(formatDuration(0)).toBe("0:00");
    expect(formatDuration(5_400)).toBe("0:05");
    expect(formatDuration(65_000)).toBe("1:05");
    expect(formatDuration(3_723_000)).toBe("1:02:03");
    expect(formatDuration(-5)).toBe("0:00");
  });
});

describe("anchorMatches", () => {
  const anchor = { index: 10, before: "was raining", after: " and cold" };
  it("matches only when both sides of the context are unchanged", () => {
    expect(
      anchorMatches(anchor, { before: "was raining", after: " and cold" }),
    ).toBe(true);
    expect(
      anchorMatches(anchor, { before: "was raining", after: " and warm" }),
    ).toBe(false);
    expect(
      anchorMatches(anchor, { before: "it was raining", after: " and cold" }),
    ).toBe(false);
  });
});

describe("RollingPeaks", () => {
  it("keeps memory bounded to its capacity, newest last", () => {
    const peaks = new RollingPeaks(4);
    for (const level of [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]) peaks.push(level);
    expect(peaks.length).toBe(4);
    expect(peaks.bars(10)).toEqual([0.3, 0.4, 0.5, 0.6]);
  });

  it("resamples a full window down by taking each group's peak", () => {
    const peaks = new RollingPeaks(8);
    for (const level of [0.1, 0.9, 0.2, 0.3, 0.4, 0.4, 0.05, 0.06])
      peaks.push(level);
    expect(peaks.bars(4)).toEqual([0.9, 0.3, 0.4, 0.06]);
  });

  it("clamps to 0..1 and handles empty input", () => {
    const peaks = new RollingPeaks(3);
    expect(peaks.bars(5)).toEqual([]);
    peaks.push(-1);
    peaks.push(7);
    expect(peaks.bars(5)).toEqual([0, 1]);
  });
});
