import { describe, expect, it } from "vitest";
import type { QuillDelta } from "../../api/generated/types.gen";
import { prependPlainParagraph } from "./bodySeed";

const EMPTY: QuillDelta = { ops: [{ insert: "\n" }] };

describe("prependPlainParagraph", () => {
  it("seeds text as an unattributed opening paragraph", () => {
    expect(prependPlainParagraph(EMPTY, "Coffee with Sam")).toEqual({
      ops: [
        { insert: "Coffee with Sam" },
        { insert: "\n\n" },
        { insert: "\n" },
      ],
    });
  });

  it("keeps existing content below the seeded text", () => {
    const doc: QuillDelta = {
      ops: [{ insert: "later thoughts" }, { insert: "\n" }],
    };
    expect(prependPlainParagraph(doc, "note")).toEqual({
      ops: [
        { insert: "note" },
        { insert: "\n\n" },
        { insert: "later thoughts" },
        { insert: "\n" },
      ],
    });
  });

  it("trims surrounding whitespace", () => {
    expect(prependPlainParagraph(EMPTY, "  spaced  ")).toEqual({
      ops: [{ insert: "spaced" }, { insert: "\n\n" }, { insert: "\n" }],
    });
  });

  it("returns the document untouched for blank text", () => {
    expect(prependPlainParagraph(EMPTY, "   ")).toBe(EMPTY);
  });

  it("preserves internal newlines", () => {
    expect(prependPlainParagraph(EMPTY, "line one\nline two")).toEqual({
      ops: [
        { insert: "line one\nline two" },
        { insert: "\n\n" },
        { insert: "\n" },
      ],
    });
  });
});
