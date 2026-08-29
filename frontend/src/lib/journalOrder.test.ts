import { describe, expect, it } from "vitest";
import type { JournalResponse } from "../api/generated/types.gen";
import {
  compareJournals,
  defaultJournalId,
  groupJournals,
  reorderWithinGroup,
  sortJournals,
} from "./journalOrder";

const make = (
  over: Partial<JournalResponse> & { id: string },
): JournalResponse => ({
  user_id: "u",
  title: over.title ?? over.id,
  is_favorite: false,
  is_archived: false,
  position: null,
  entry_count: 0,
  total_words: 0,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  ...over,
});

describe("compareJournals / sortJournals", () => {
  it("puts favourites first, then by position, then newest first", () => {
    const list = [
      make({ id: "old-plain", created_at: "2026-01-01T00:00:00Z" }),
      make({ id: "new-plain", created_at: "2026-06-01T00:00:00Z" }),
      make({ id: "fav-b", is_favorite: true, position: 1 }),
      make({ id: "fav-a", is_favorite: true, position: 0 }),
      make({ id: "positioned", position: 5 }),
    ];
    expect(sortJournals(list).map((j) => j.id)).toEqual([
      "fav-a",
      "fav-b",
      "positioned",
      "new-plain",
      "old-plain",
    ]);
  });

  it("treats a missing position as after any explicit one", () => {
    const withPos = make({ id: "with", position: 9 });
    const without = make({ id: "without", position: null });
    expect(compareJournals(withPos, without)).toBeLessThan(0);
  });
});

describe("groupJournals", () => {
  it("splits active / archived / favourites, each sorted", () => {
    const list = [
      make({ id: "arch", is_archived: true }),
      make({ id: "fav", is_favorite: true, position: 0 }),
      make({ id: "plain", position: 1 }),
    ];
    const groups = groupJournals(list);
    expect(groups.active.map((j) => j.id)).toEqual(["fav", "plain"]);
    expect(groups.archived.map((j) => j.id)).toEqual(["arch"]);
    expect(groups.favorites.map((j) => j.id)).toEqual(["fav"]);
  });
});

describe("defaultJournalId", () => {
  it("is the first active journal in canonical order", () => {
    const list = [
      make({ id: "plain", position: 0 }),
      make({ id: "fav", is_favorite: true, position: 3 }),
    ];
    expect(defaultJournalId(list)).toBe("fav");
  });
  it("is undefined when every journal is archived", () => {
    expect(
      defaultJournalId([make({ id: "a", is_archived: true })]),
    ).toBeUndefined();
  });
});

describe("reorderWithinGroup", () => {
  const list = [
    make({ id: "a", position: 0 }),
    make({ id: "b", position: 1 }),
    make({ id: "c", position: 2 }),
    make({ id: "fav", is_favorite: true, position: 0 }),
  ];

  it("moves a journal down within its own non-favourite peer group", () => {
    expect(reorderWithinGroup(list, "a", "down")).toEqual([
      { id: "b", position: 0 },
      { id: "a", position: 1 },
      { id: "c", position: 2 },
    ]);
  });

  it("moves a journal up", () => {
    expect(reorderWithinGroup(list, "c", "up")).toEqual([
      { id: "a", position: 0 },
      { id: "c", position: 1 },
      { id: "b", position: 2 },
    ]);
  });

  it("returns null at the edge of the group", () => {
    expect(reorderWithinGroup(list, "a", "up")).toBeNull();
    expect(reorderWithinGroup(list, "c", "down")).toBeNull();
    // The lone favourite cannot move even though non-favourites sit "below" it.
    expect(reorderWithinGroup(list, "fav", "down")).toBeNull();
  });
});
