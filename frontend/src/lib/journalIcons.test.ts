import { describe, expect, it } from "vitest";
import { JOURNAL_ICONS, resolveJournalIcon } from "./journalIcons";

describe("resolveJournalIcon", () => {
  it("resolves a known key to a component", () => {
    expect(resolveJournalIcon("book-open")).toBe(
      JOURNAL_ICONS.find((i) => i.key === "book-open")?.Icon,
    );
  });

  it("returns null for an empty or missing value", () => {
    expect(resolveJournalIcon(null)).toBeNull();
    expect(resolveJournalIcon(undefined)).toBeNull();
    expect(resolveJournalIcon("")).toBeNull();
  });

  it("returns null for a value that is not one of our keys", () => {
    // A Material Symbols name written by the Flutter client, for example.
    expect(resolveJournalIcon("sentiment_very_satisfied")).toBeNull();
    expect(resolveJournalIcon("BookOpen")).toBeNull();
  });

  it("every catalogue key resolves", () => {
    for (const { key } of JOURNAL_ICONS) {
      expect(resolveJournalIcon(key)).toBeTruthy();
    }
  });
});
