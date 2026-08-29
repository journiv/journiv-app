import { describe, expect, it } from "vitest";
import {
  canonicalDeltaJson,
  cloneDelta,
  deltasEqual,
  hasUnsupportedEmbed,
  INLINE_MEDIA_KINDS,
  inlineMediaPaths,
  isQuillDocumentDelta,
  isReaderDocumentDelta,
} from "./deltaProfile";
import { CANONICAL_DELTA_FIXTURES } from "./fixtures";

describe("Journiv Delta profile", () => {
  it("accepts and safely clones every canonical fixture", () => {
    for (const [, fixture] of CANONICAL_DELTA_FIXTURES) {
      expect(isQuillDocumentDelta(fixture)).toBe(true);
      const cloned = cloneDelta(fixture);
      expect(cloned).toEqual(fixture);
      expect(cloned).not.toBe(fixture);
      expect(canonicalDeltaJson(cloned)).toBe(canonicalDeltaJson(fixture));
    }
  });

  it("rejects malformed values and change Deltas", () => {
    expect(isQuillDocumentDelta(null)).toBe(false);
    expect(isQuillDocumentDelta({ ops: [] })).toBe(false);
    expect(isQuillDocumentDelta({ ops: [{ retain: 1 }] })).toBe(false);
    expect(isQuillDocumentDelta({ ops: [{ insert: "missing newline" }] })).toBe(
      false,
    );
  });

  it.each([
    [
      "image embed",
      {
        ops: [
          { insert: { image: "https://example.test/a.jpg" } },
          { insert: "\n" },
        ],
      },
    ],
    [
      "video embed",
      {
        ops: [
          { insert: { video: "https://example.test/a.mp4" } },
          { insert: "\n" },
        ],
      },
    ],
    [
      "unknown embed",
      { ops: [{ insert: { divider: true } }, { insert: "\n" }] },
    ],
    [
      "color",
      {
        ops: [
          { insert: "red", attributes: { color: "#f00" } },
          { insert: "\n" },
        ],
      },
    ],
    [
      "code block",
      {
        ops: [
          { insert: "code" },
          { insert: "\n", attributes: { "code-block": true } },
        ],
      },
    ],
    [
      "invalid bold",
      {
        ops: [
          { insert: "bold", attributes: { bold: "true" } },
          { insert: "\n" },
        ],
      },
    ],
    [
      "invalid heading",
      {
        ops: [
          { insert: "Heading" },
          { insert: "\n", attributes: { header: 4 } },
        ],
      },
    ],
    [
      "invalid list",
      {
        ops: [
          { insert: "Task" },
          { insert: "\n", attributes: { list: "checked" } },
        ],
      },
    ],
    [
      "unsafe link",
      {
        ops: [
          { insert: "bad", attributes: { link: "javascript:alert(1)" } },
          { insert: "\n" },
        ],
      },
    ],
    [
      "line format on text",
      {
        ops: [
          { insert: "Heading", attributes: { header: 1 } },
          { insert: "\n" },
        ],
      },
    ],
    [
      "header and list on one line",
      {
        ops: [
          { insert: "Conflicting line" },
          { insert: "\n", attributes: { header: 1, list: "bullet" } },
        ],
      },
    ],
    [
      "header and blockquote on one line",
      {
        ops: [
          { insert: "Conflicting line" },
          { insert: "\n", attributes: { header: 2, blockquote: true } },
        ],
      },
    ],
    [
      "list and blockquote on one line",
      {
        ops: [
          { insert: "Conflicting line" },
          {
            insert: "\n",
            attributes: { list: "ordered", blockquote: true },
          },
        ],
      },
    ],
    [
      "header, list, and blockquote on one line",
      {
        ops: [
          { insert: "Conflicting line" },
          {
            insert: "\n",
            attributes: { header: 3, list: "bullet", blockquote: true },
          },
        ],
      },
    ],
  ])(
    "rejects unsupported or malformed %s without rewriting it",
    (_name, value) => {
      const original = structuredClone(value);
      expect(isQuillDocumentDelta(value)).toBe(false);
      expect(value).toEqual(original);
    },
  );

  it("compares semantically equivalent adjacent operations", () => {
    expect(
      deltasEqual(
        { ops: [{ insert: "Hello" }, { insert: " world\n" }] },
        { ops: [{ insert: "Hello world\n" }] },
      ),
    ).toBe(true);
  });
});

describe("inline media embeds as the API actually serialises them", () => {
  // Found in the browser: the API sends `attributes: null` on embed ops, and an
  // earlier guard rejected any op carrying an `attributes` key at all. Real
  // entries silently fell back to unformatted plain text.
  const signed =
    "/api/v1/media/6f1c9a52-2b7d-4c1e-9f83-0a5d7e4b1c20/signed?sig=a";

  it.each([...INLINE_MEDIA_KINDS])(
    "accepts a %s embed carrying attributes: null",
    (kind) => {
      const delta = {
        ops: [
          { insert: "before\n", attributes: null },
          { insert: { [kind]: signed }, attributes: null },
          { insert: "after\n" },
        ],
      } as never;
      expect(isReaderDocumentDelta(delta)).toBe(true);
      expect(hasUnsupportedEmbed(delta)).toBe(false);
      expect(inlineMediaPaths(delta)).toHaveLength(1);
    },
  );

  it("still rejects an embed carrying attributes we do not understand", () => {
    const delta = {
      ops: [
        { insert: { image: signed }, attributes: { width: 320 } },
        { insert: "\n" },
      ],
    } as never;
    expect(hasUnsupportedEmbed(delta)).toBe(true);
  });
});
