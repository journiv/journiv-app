import { describe, expect, it, vi } from "vitest";
import {
  dayGroupLabel,
  formatDayMedium,
  wallTimePartsInZone,
  zonedWallTimeToUtcIso,
  type WallTimeParts,
} from "./datetime";

describe("zonedWallTimeToUtcIso", () => {
  it("interprets the same wall-clock differently per zone", () => {
    const parts: WallTimeParts = {
      year: 2026,
      month: 1,
      day: 15,
      hour: 20,
      minute: 0,
    };
    // Warsaw is UTC+1 in January; Los Angeles is UTC-8.
    expect(zonedWallTimeToUtcIso(parts, "Europe/Warsaw")).toBe(
      "2026-01-15T19:00:00.000Z",
    );
    expect(zonedWallTimeToUtcIso(parts, "America/Los_Angeles")).toBe(
      "2026-01-16T04:00:00.000Z",
    );
  });

  it("round-trips through wallTimePartsInZone", () => {
    const parts: WallTimeParts = {
      year: 2025,
      month: 7,
      day: 4,
      hour: 8,
      minute: 30,
    };
    for (const tz of ["Europe/Warsaw", "America/Los_Angeles", "Asia/Kolkata"]) {
      const utc = zonedWallTimeToUtcIso(parts, tz);
      expect(wallTimePartsInZone(utc, tz)).toEqual(parts);
    }
  });

  it("pushes a nonexistent spring-forward local time past the gap", () => {
    // 2025-03-09 02:30 does not exist in New York (02:00 -> 03:00).
    const utc = zonedWallTimeToUtcIso(
      { year: 2025, month: 3, day: 9, hour: 2, minute: 30 },
      "America/New_York",
    );
    // date-fns-tz resolves it deterministically with the pre-gap offset
    // (EST, -5), so the instant lands just after the skipped hour.
    expect(utc).toBe("2025-03-09T07:30:00.000Z");
  });

  it("resolves an ambiguous fall-back local time to the earlier offset", () => {
    // 2025-11-02 01:30 happens twice in New York; the first is EDT (-4).
    const utc = zonedWallTimeToUtcIso(
      { year: 2025, month: 11, day: 2, hour: 1, minute: 30 },
      "America/New_York",
    );
    expect(utc).toBe("2025-11-02T05:30:00.000Z");
  });
});

describe("wallTimePartsInZone", () => {
  it("reads the calendar day in the target zone, not the caller's", () => {
    // 23:30 UTC on the 15th is already the 16th in Kolkata (+5:30).
    expect(
      wallTimePartsInZone("2026-02-15T23:30:00.000Z", "Asia/Kolkata"),
    ).toEqual({ year: 2026, month: 2, day: 16, hour: 5, minute: 0 });
  });
});

describe("dayGroupLabel", () => {
  it("uses the viewer's local year at the New Year boundary", () => {
    const resolvedOptions = Intl.DateTimeFormat.prototype.resolvedOptions;
    const spy = vi
      .spyOn(Intl.DateTimeFormat.prototype, "resolvedOptions")
      .mockImplementation(function (this: Intl.DateTimeFormat) {
        return {
          ...resolvedOptions.call(this),
          timeZone: "America/Los_Angeles",
        };
      });

    try {
      const now = new Date("2027-01-01T00:30:00.000Z");
      const utc = "2026-12-30T17:00:00.000Z";
      expect(dayGroupLabel("2026-12-30", "America/New_York", utc, now)).toBe(
        formatDayMedium(utc, "America/New_York"),
      );
    } finally {
      spy.mockRestore();
    }
  });
});
