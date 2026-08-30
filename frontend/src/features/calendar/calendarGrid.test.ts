import { describe, expect, it } from "vitest";
import {
  buildMonthGrid,
  currentMonth,
  formatDayHeading,
  gridRange,
  isMonthKey,
  MONTH_NAMES,
  monthKeyOf,
  monthLabel,
  monthParts,
  shiftMonth,
  yearOptions,
} from "./calendarGrid";

describe("calendarGrid", () => {
  it("builds a 42-cell grid that starts on a Sunday and covers the month", () => {
    const cells = buildMonthGrid("2026-08");
    expect(cells).toHaveLength(42);
    // 1 August 2026 is a Saturday, so the grid opens with the last week of July.
    expect(cells[0].iso).toBe("2026-07-26");
    expect(cells[0].inMonth).toBe(false);
    const first = cells.find((c) => c.iso === "2026-08-01");
    expect(first?.inMonth).toBe(true);
    expect(first?.day).toBe(1);
    expect(cells.filter((c) => c.inMonth)).toHaveLength(31);
  });

  it("does not shift a cell across a DST boundary", () => {
    // Europe DST ends late October; the grid must still land on plain dates.
    const cells = buildMonthGrid("2026-10");
    expect(cells.some((c) => c.iso === "2026-10-25")).toBe(true);
    expect(cells.every((c) => /^\d{4}-\d{2}-\d{2}$/.test(c.iso))).toBe(true);
  });

  it("derives the query range from the visible grid", () => {
    expect(gridRange("2026-08")).toEqual({
      start: "2026-07-26",
      end: "2026-09-05",
    });
  });

  it("shifts months across year boundaries", () => {
    expect(shiftMonth("2026-01", -1)).toBe("2025-12");
    expect(shiftMonth("2026-12", 1)).toBe("2027-01");
    expect(shiftMonth("2026-08", 0)).toBe("2026-08");
  });

  it("validates month keys", () => {
    expect(isMonthKey("2026-08")).toBe(true);
    expect(isMonthKey("2026-8")).toBe(false);
    expect(isMonthKey("bogus")).toBe(false);
  });

  it("labels months and days in a stable, UTC-based way", () => {
    expect(monthLabel("2026-08")).toMatch(/2026/);
    expect(monthLabel("2026-08")).toMatch(/August/i);
    const heading = formatDayHeading("2026-08-08");
    expect(heading).toMatch(/August/i);
    expect(heading).toMatch(/\b8\b/);
    expect(heading).toMatch(/2026/);
    expect(heading).toMatch(/Saturday/i);
  });

  it("splits a month key into a year and a 0-based month index", () => {
    expect(monthParts("2026-08")).toEqual({ year: 2026, monthIndex: 7 });
    expect(monthParts("1999-01")).toEqual({ year: 1999, monthIndex: 0 });
  });

  it("composes a month key and normalises index overflow", () => {
    expect(monthKeyOf(2026, 7)).toBe("2026-08");
    expect(monthKeyOf(2026, 12)).toBe("2027-01");
    expect(monthKeyOf(2026, -1)).toBe("2025-12");
  });

  it("names all twelve months in order", () => {
    expect(MONTH_NAMES).toHaveLength(12);
    expect(MONTH_NAMES[0]).toMatch(/january/i);
    expect(MONTH_NAMES[11]).toMatch(/december/i);
  });

  it("lists years ascending from 1970 through next year, widened to the selection", () => {
    const now = new Date("2026-08-01T00:00:00Z");
    const normal = yearOptions(2026, now);
    expect(normal[0]).toBe(1970);
    expect(normal.at(-1)).toBe(2027);

    // A URL pointing at an out-of-range month still lists its own year.
    expect(yearOptions(1950, now)).toContain(1950);
    expect(yearOptions(2099, now)).toContain(2099);
  });

  it("reads the current month in the given timezone", () => {
    const now = new Date("2026-08-31T23:30:00Z");
    // In Tokyo it is already 1 September.
    expect(currentMonth("Asia/Tokyo", now)).toBe("2026-09");
    expect(currentMonth("America/Los_Angeles", now)).toBe("2026-08");
  });
});
