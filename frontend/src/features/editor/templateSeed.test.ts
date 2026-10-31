import { describe, expect, it } from "vitest";
import type { JournalResponse } from "../../api/generated/types.gen";
import { isEditableDocumentDelta } from "./deltaProfile";
import { buildTemplateDelta, templateDeltaFor } from "./templateSeed";

const journal = (id: string, entry_template: string | null) =>
  ({ id, title: id, entry_template }) as JournalResponse;

describe("buildTemplateDelta", () => {
  it("returns null when there is no template", () => {
    expect(buildTemplateDelta(null)).toBeNull();
    expect(buildTemplateDelta(undefined)).toBeNull();
    expect(buildTemplateDelta("")).toBeNull();
    expect(buildTemplateDelta("  \n\n ")).toBeNull();
  });

  it("seeds the template as plain lines ending in one newline", () => {
    expect(buildTemplateDelta("Mood:\r\nOne win:\n\nTomorrow:\n\n")).toEqual({
      ops: [{ insert: "Mood:\nOne win:\n\nTomorrow:\n" }],
    });
  });

  it("produces a document the editor will open and save", () => {
    const seeded = buildTemplateDelta("Mood:\nGrateful for:");
    expect(seeded).not.toBeNull();
    expect(isEditableDocumentDelta(seeded)).toBe(true);
  });
});

describe("templateDeltaFor", () => {
  const journals = [journal("daily", "Mood:"), journal("plain", null)];

  it("finds the journal's template", () => {
    expect(templateDeltaFor(journals, "daily")).toEqual({
      ops: [{ insert: "Mood:\n" }],
    });
  });

  it("is null for a journal without one, an unknown id, or no id", () => {
    expect(templateDeltaFor(journals, "plain")).toBeNull();
    expect(templateDeltaFor(journals, "missing")).toBeNull();
    expect(templateDeltaFor(journals, undefined)).toBeNull();
  });
});
