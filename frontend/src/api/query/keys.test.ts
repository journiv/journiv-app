import { describe, expect, it } from "vitest";
import { momentsQuery } from "./options";
import { normalizeMomentFilters, queryKeys, sameMomentScope } from "./keys";

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

describe("sameMomentScope", () => {
  const norm = normalizeMomentFilters;

  it("treats a search change within the same scope as the same scope", () => {
    expect(
      sameMomentScope(norm({ search: "vac" }), norm({ search: "vacation" })),
    ).toBe(true);
    expect(sameMomentScope(norm({}), norm({ search: "vacation" }))).toBe(true);
    expect(
      sameMomentScope(
        norm({ journal_id: "j1", search: "a" }),
        norm({ journal_id: "j1", search: "b" }),
      ),
    ).toBe(true);
  });

  it("treats a scope-subject change as a different scope", () => {
    expect(sameMomentScope(norm({}), norm({ person_id: "p1" }))).toBe(false);
    expect(
      sameMomentScope(norm({ person_id: "p1" }), norm({ person_id: "p2" })),
    ).toBe(false);
    expect(
      sameMomentScope(norm({ journal_id: "j1" }), norm({ journal_id: "j2" })),
    ).toBe(false);
    expect(
      sameMomentScope(norm({ journal_id: "j1" }), norm({ tag_id: "j1" })),
    ).toBe(false);
  });

  it("covers every scope field, including ones no entity view sets", () => {
    // Scope identity is defined by removing `search`, not by listing fields,
    // so a filter the helper was never explicitly taught about — the
    // calendar's day range — still separates two scopes.
    expect(
      sameMomentScope(
        norm({ start_date: "2026-01-01", end_date: "2026-01-01" }),
        norm({ start_date: "2026-01-02", end_date: "2026-01-02" }),
      ),
    ).toBe(false);
    expect(sameMomentScope(norm({ start_date: "2026-01-01" }), norm({}))).toBe(
      false,
    );
  });

  it("has no previous scope to compare against on first load", () => {
    expect(sameMomentScope(undefined, norm({}))).toBe(false);
  });
});
