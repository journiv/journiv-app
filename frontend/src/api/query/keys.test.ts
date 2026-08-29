import { describe, expect, it } from "vitest";
import { momentsQuery } from "./options";
import { normalizeMomentFilters, queryKeys } from "./keys";

describe("moment query policy", () => {
  it("normalizes blank search filters and produces deterministic keys", () => {
    expect(
      normalizeMomentFilters({ journal_id: "journal-1", search: "  " }),
    ).toEqual({
      journal_id: "journal-1",
    });
    expect(queryKeys.moments({ search: " rain " })).toEqual([
      "moments",
      { search: "rain" },
    ]);
  });

  it("maps an entity scope to its GET /moments filter", () => {
    expect(normalizeMomentFilters({ person_id: "p1" })).toEqual({
      person_ids: ["p1"],
    });
    expect(normalizeMomentFilters({ tag_id: "t1" })).toEqual({
      tag_ids: ["t1"],
    });
    expect(normalizeMomentFilters({ activity_id: "a1" })).toEqual({
      activity_ids: ["a1"],
    });
    expect(normalizeMomentFilters({ mood_id: "m1" })).toEqual({
      mood_ids: ["m1"],
    });
    expect(normalizeMomentFilters({ goal_id: "g1" })).toEqual({
      goal_id: "g1",
    });
  });

  it("gives each entity scope its own momentsQuery cache key", () => {
    const key = (f: Parameters<typeof momentsQuery>[0]) =>
      JSON.stringify(momentsQuery(f).queryKey);
    const all = key({});
    expect(key({ person_id: "p1" })).not.toEqual(all);
    expect(key({ tag_id: "t1" })).not.toEqual(all);
    expect(key({ goal_id: "g1" })).not.toEqual(all);
    expect(key({ person_id: "p1" })).not.toEqual(key({ person_id: "p2" }));
    expect(key({ person_id: "p1" })).not.toEqual(key({ tag_id: "p1" }));
  });
});
