import { describe, expect, it } from "vitest";
import {
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
