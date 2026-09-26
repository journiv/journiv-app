import { describe, expect, it } from "vitest";
import {
  DISPLAY_BARS,
  formatClock,
  reducePeaks,
  usablePeaks,
} from "./waveformPeaks";

describe("usablePeaks", () => {
  it("accepts a non-empty list of numbers", () => {
    expect(usablePeaks([0, 50, 100])).toBe(true);
  });

  it("treats anything else as 'not computed yet'", () => {
    expect(usablePeaks(null)).toBe(false);
    expect(usablePeaks(undefined)).toBe(false);
    expect(usablePeaks([])).toBe(false);
    expect(usablePeaks([1, Number.NaN])).toBe(false);
  });
});

describe("reducePeaks", () => {
  it("reduces 400 stored buckets to a fixed bar count by group peak", () => {
    const peaks = Array.from({ length: 400 }, (_, i) => (i === 200 ? 100 : 10));
    const bars = reducePeaks(peaks);
    expect(bars).toHaveLength(DISPLAY_BARS);
    expect(Math.max(...bars)).toBe(1);
    // The one loud bucket survives reduction rather than being averaged away.
    expect(bars.filter((value) => value === 1)).toHaveLength(1);
    expect(bars.every((value) => value >= 0.1 - 1e-9)).toBe(true);
  });

  it("keeps a short waveform as it is, scaled to 0..1", () => {
    expect(reducePeaks([0, 50, 100], 96)).toEqual([0, 0.5, 1]);
  });

  it("clamps out-of-range values", () => {
    expect(reducePeaks([-5, 250], 96)).toEqual([0, 1]);
  });

  it("returns nothing for nothing", () => {
    expect(reducePeaks([], 10)).toEqual([]);
    expect(reducePeaks([1, 2], 0)).toEqual([]);
  });
});

describe("formatClock", () => {
  it("formats seconds", () => {
    expect(formatClock(0)).toBe("0:00");
    expect(formatClock(65.9)).toBe("1:05");
    expect(formatClock(3723)).toBe("1:02:03");
    expect(formatClock(Number.POSITIVE_INFINITY)).toBe("0:00");
    expect(formatClock(-3)).toBe("0:00");
  });
});
