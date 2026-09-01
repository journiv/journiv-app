import { describe, expect, it } from "vitest";
import {
  chunkRows,
  columnCountFor,
  type VirtualGridOptions,
} from "./useVirtualGrid";

const options: VirtualGridOptions = {
  minTileWidth: 132,
  gap: 8,
  minColumns: 3,
  maxColumns: 8,
};

describe("columnCountFor", () => {
  it("falls back to the minimum for an unmeasured container", () => {
    expect(columnCountFor(0, options)).toBe(3);
    expect(columnCountFor(Number.NaN, options)).toBe(3);
  });

  it("never drops below the minimum on a narrow phone", () => {
    // 320px would geometrically fit ~2 columns; the floor keeps it a grid.
    expect(columnCountFor(320, options)).toBe(3);
  });

  it("scales with width", () => {
    expect(columnCountFor(560, options)).toBe(4); // (560+8)/140 = 4.05
    expect(columnCountFor(900, options)).toBe(6); // (900+8)/140 = 6.48
    expect(columnCountFor(1200, options)).toBe(8); // clamped at max
  });

  it("never exceeds the maximum on a very wide pane", () => {
    expect(columnCountFor(4000, options)).toBe(8);
  });
});

describe("chunkRows", () => {
  it("splits an even list", () => {
    expect(chunkRows([1, 2, 3, 4], 2)).toEqual([
      [1, 2],
      [3, 4],
    ]);
  });

  it("keeps a short final row", () => {
    expect(chunkRows([1, 2, 3, 4, 5], 3)).toEqual([
      [1, 2, 3],
      [4, 5],
    ]);
  });

  it("returns nothing for an empty list", () => {
    expect(chunkRows([], 4)).toEqual([]);
  });

  it("degrades to a single row rather than dividing by zero", () => {
    expect(chunkRows([1, 2], 0)).toEqual([[1, 2]]);
    expect(chunkRows([], 0)).toEqual([]);
  });
});
