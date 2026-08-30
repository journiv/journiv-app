import { describe, expect, it } from "vitest";
import type { MomentResponse } from "../../api/generated/types.gen";
import { groupMomentsByDay } from "./dateGroups";

const viewerTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;

const moment = (date: string, utc: string, timezone = viewerTimezone) =>
  ({
    id: `m-${date}-${timezone}`,
    logged_date_tz: date,
    logged_at_utc: utc,
    logged_timezone: timezone,
  }) as unknown as MomentResponse;

describe("Timeline day grouping", () => {
  it("groups by the Moment's own local day, not the viewer's", () => {
    const groups = groupMomentsByDay([
      moment("2026-08-17", "2026-08-17T18:04:00Z"),
      moment("2026-08-17", "2026-08-17T02:10:00Z"),
      moment("2026-08-16", "2026-08-16T20:00:00Z"),
    ]);
    expect(groups.map((group) => group.key)).toEqual([
      "2026-08-17",
      "2026-08-16",
    ]);
    expect(groups[0].moments).toHaveLength(2);
  });

  it("uses Today and Yesterday only in the viewer's own timezone", () => {
    const now = new Date("2026-08-17T18:00:00Z");
    const today = new Intl.DateTimeFormat("en-CA", {
      timeZone: viewerTimezone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(now);

    const local = groupMomentsByDay(
      [moment(today, "2026-08-17T18:00:00Z")],
      now,
    );
    expect(local[0].label).toBe("Today");

    // Same instant, logged somewhere else: the explicit date is shown instead.
    const elsewhere = groupMomentsByDay(
      [moment(today, "2026-08-17T18:00:00Z", "Asia/Tokyo")],
      now,
    );
    expect(elsewhere[0].label).not.toBe("Today");
  });
});
