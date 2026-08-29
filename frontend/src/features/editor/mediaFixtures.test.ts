import { describe, expect, it } from "vitest";
import type { QuillDelta } from "../../api/generated/types.gen";
import {
  hasUnsupportedEmbed,
  inlineMediaPaths,
  isQuillDocumentDelta,
  isReaderDocumentDelta,
} from "./deltaProfile";
import { CANONICAL_MEDIA_FIXTURES } from "./fixtures";

/**
 * Fixtures hold the PERSISTED form — a bare media id. The client only ever sees
 * the hydrated form, because the backend swaps ids for signed URLs on read.
 * This mirrors that hydration so the reader can be tested against reality.
 */
function hydrate(delta: QuillDelta): QuillDelta {
  return {
    ops: (delta.ops ?? []).map((op) => {
      const insert = op.insert as Record<string, unknown>;
      if (typeof op.insert === "string" || !insert) return op;
      const [key] = Object.keys(insert);
      const id = insert[key];
      return typeof id === "string"
        ? { insert: { [key]: `/api/v1/media/${id}/signed?uid=u&exp=1&sig=s` } }
        : op;
    }),
  } as QuillDelta;
}

describe("inline media fixtures", () => {
  it.each(CANONICAL_MEDIA_FIXTURES)(
    "%s is rejected by the editor profile in both forms",
    (_name, fixture) => {
      // Editor attachment is not built yet: Gate-1 still refuses every embed,
      // so entries containing inline media stay read-only.
      expect(isQuillDocumentDelta(fixture)).toBe(false);
      expect(isQuillDocumentDelta(hydrate(fixture))).toBe(false);
    },
  );

  it.each(CANONICAL_MEDIA_FIXTURES)(
    "%s is not reader-renderable in its persisted form",
    (_name, fixture) => {
      // A bare id is not a safe same-origin URL, so it must never render.
      expect(
        isReaderDocumentDelta(fixture) && !hasUnsupportedEmbed(fixture),
      ).toBe(false);
    },
  );

  it("renders hydrated inline images and reports their paths", () => {
    const [, imageFixture] = CANONICAL_MEDIA_FIXTURES[0];
    const hydrated = hydrate(imageFixture);
    expect(isReaderDocumentDelta(hydrated)).toBe(true);
    expect(hasUnsupportedEmbed(hydrated)).toBe(false);
    expect(inlineMediaPaths(hydrated)).toEqual([
      "/api/v1/media/6f1c9a52-2b7d-4c1e-9f83-0a5d7e4b1c20/signed",
    ]);
  });

  it.each([
    ["inline video", 1],
    ["inline audio", 2],
  ])("renders hydrated %s inline", (_name, index) => {
    const [, fixture] = CANONICAL_MEDIA_FIXTURES[index];
    const hydrated = hydrate(fixture);
    expect(isReaderDocumentDelta(hydrated)).toBe(true);
    expect(hasUnsupportedEmbed(hydrated)).toBe(false);
  });

  it("still refuses embed kinds Journiv does not render", () => {
    const formula = {
      ops: [{ insert: { formula: "/api/v1/x" } }, { insert: "\n" }],
    };
    const divider = {
      ops: [{ insert: { divider: "/api/v1/x" } }, { insert: "\n" }],
    };
    expect(hasUnsupportedEmbed(formula as never)).toBe(true);
    expect(hasUnsupportedEmbed(divider as never)).toBe(true);
  });

  it("reports every inline media path regardless of kind", () => {
    const [, combined] = CANONICAL_MEDIA_FIXTURES[3];
    const paths = inlineMediaPaths(hydrate(combined));
    expect(paths).toHaveLength(2);
    expect(paths.every((path) => path.endsWith("/signed"))).toBe(true);
  });
});
