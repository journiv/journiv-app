import { describe, expect, it } from "vitest";
import type { MediaLibraryItem } from "../../api/generated/types.gen";
import { groupMediaByMonth } from "./mediaGroups";

const item = (id: string, day: string): MediaLibraryItem => ({
  id,
  moment_id: `m-${id}`,
  media_type: "image",
  mime_type: "image/jpeg",
  upload_status: "completed",
  created_at: `${day}T10:00:00Z`,
  logged_date_tz: day,
  logged_at_utc: `${day}T10:00:00Z`,
  logged_timezone: "UTC",
});

describe("groupMediaByMonth", () => {
  it("groups a newest-first list into contiguous month sections, preserving order", () => {
    const groups = groupMediaByMonth([
      item("a", "2026-08-20"),
      item("b", "2026-08-02"),
      item("c", "2026-07-30"),
      item("d", "2026-07-01"),
      item("e", "2026-05-09"),
    ]);
    expect(groups.map((g) => g.key)).toEqual(["2026-08", "2026-07", "2026-05"]);
    expect(groups[0].items.map((i) => i.id)).toEqual(["a", "b"]);
    expect(groups[1].items.map((i) => i.id)).toEqual(["c", "d"]);
    expect(groups[0].label).toMatch(/August 2026/);
  });

  it("returns nothing for an empty list", () => {
    expect(groupMediaByMonth([])).toEqual([]);
  });
});
