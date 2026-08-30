import { describe, expect, it } from "vitest";
import type { QuillDelta } from "../../api/generated/types.gen";
import { isEditableDocumentDelta } from "./deltaProfile";
import {
  canonicalizeDeltaForDraft,
  draftComparisonKey,
  draftContentEquals,
  draftMediaIds,
  durableMediaId,
  isDurableDraftDelta,
  rehydrateDraftDelta,
} from "./draftCanonical";

const PHOTO = "0f8b1c2d-3e4f-4a5b-8c9d-0e1f2a3b4c5d";
const CLIP = "1a2b3c4d-5e6f-4071-8293-a4b5c6d7e8f9";

/** What the backend actually hydrates into a document: path + signed query. */
const signed = (id: string, sig: string) =>
  `/api/v1/media/${id}/signed?uid=user-1&exp=1790000000&sig=${sig}`;

const delta = (ops: unknown[]) => ({ ops }) as QuillDelta;

describe("durableMediaId", () => {
  it("reads the id out of a signed media URL", () => {
    expect(durableMediaId(signed(PHOTO, "abc"))).toBe(PHOTO);
  });

  it("reads the id out of an unsigned media path", () => {
    expect(durableMediaId(`/api/v1/media/${PHOTO}/signed`)).toBe(PHOTO);
  });

  it("refuses sources that are not Journiv media paths", () => {
    expect(durableMediaId("/media/holiday.jpg")).toBeNull();
    expect(durableMediaId("https://tracker.example.com/x.png")).toBeNull();
    expect(durableMediaId(`/api/v1/other/${PHOTO}/signed`)).toBeNull();
    expect(durableMediaId("/api/v1/media/not-a-uuid/signed")).toBeNull();
  });
});

describe("canonicalizeDeltaForDraft", () => {
  it("leaves a text-only document untouched and round trips it", () => {
    const source = delta([
      { insert: "Rain all morning" },
      { insert: "\n", attributes: { header: 2 } },
      { insert: "Coffee", attributes: { bold: true } },
      { insert: " while it passed.\n" },
    ]);
    const {
      delta: canonical,
      omittedTransientUploads,
      unsupportedEmbeds,
    } = canonicalizeDeltaForDraft(source);

    expect(omittedTransientUploads).toBe(0);
    expect(unsupportedEmbeds).toBe(0);
    expect(canonical).toEqual(source);
    // A text-only durable document is still a valid editable document, so it
    // needs no rehydration to mount.
    const { delta: back, unresolvedMediaCount } = rehydrateDraftDelta(
      canonical,
      new Map(),
    );
    expect(unresolvedMediaCount).toBe(0);
    expect(back).toEqual(source);
    expect(isEditableDocumentDelta(back)).toBe(true);
  });

  it("reduces image and audio embeds to bare media ids", () => {
    const {
      delta: canonical,
      omittedTransientUploads,
      unsupportedEmbeds,
    } = canonicalizeDeltaForDraft(
      delta([
        { insert: "Before\n" },
        { insert: { image: signed(PHOTO, "sig-one") } },
        { insert: { audio: signed(CLIP, "sig-two") } },
        { insert: "After\n" },
      ]),
    );

    expect(omittedTransientUploads).toBe(0);
    expect(unsupportedEmbeds).toBe(0);
    expect(canonical).toEqual({
      ops: [
        { insert: "Before\n" },
        { insert: { image: PHOTO } },
        { insert: { audio: CLIP } },
        { insert: "After\n" },
      ],
    });
    expect(isDurableDraftDelta(canonical)).toBe(true);
  });

  it("reports media it cannot canonicalize as unsupported, never as a URL", () => {
    const { delta: canonical, unsupportedEmbeds } = canonicalizeDeltaForDraft(
      delta([
        { insert: "Imported\n" },
        // A legacy source the backend never mapped. It survives hydration
        // unchanged and still looks like a safe same-origin source.
        { insert: { image: "/media/legacy/holiday.jpg" } },
        { insert: "Kept writing\n" },
      ]),
    );

    // Durable content that cannot be represented. Not a partial success — the
    // caller must refuse to store this document at all.
    expect(unsupportedEmbeds).toBe(1);
    const serialized = JSON.stringify(canonical);
    expect(serialized).not.toContain("/media/");
    expect(serialized).not.toContain("legacy");
    expect(canonical).toEqual({
      ops: [{ insert: "Imported\nKept writing\n" }],
    });
  });

  it("stores no signature, uid, expiry or blob URL of any kind", () => {
    const { delta: canonical } = canonicalizeDeltaForDraft(
      delta([{ insert: { image: signed(PHOTO, "s3cr3t") } }, { insert: "\n" }]),
    );
    const serialized = JSON.stringify(canonical);
    for (const forbidden of [
      "sig=",
      "uid=",
      "exp=",
      "blob:",
      "http",
      "/api/",
    ]) {
      expect(serialized).not.toContain(forbidden);
    }
  });

  it("is idempotent, so re-saving an unchanged draft is a no-op", () => {
    const once = canonicalizeDeltaForDraft(
      delta([{ insert: { image: signed(PHOTO, "a") } }, { insert: "\n" }]),
    ).delta;
    const twice = canonicalizeDeltaForDraft(once).delta;
    expect(twice).toEqual(once);
  });

  it("keeps an in-flight upload placeholder out of the stored draft", () => {
    // Defence in depth: `getContents()` already strips these, but a draft must
    // never carry one even if a caller hands us a raw document. An interrupted
    // upload is lost and reattached by design (DESIGN.md §21.14).
    const {
      delta: canonical,
      omittedTransientUploads,
      unsupportedEmbeds,
    } = canonicalizeDeltaForDraft(
      delta([
        { insert: "Writing\n" },
        { insert: { "journiv-upload": { uploadId: "upload-1" } } },
        { insert: "more\n" },
      ]),
    );
    // Reported as a transient omission, NOT as damage and NOT as unsupported:
    // the writer needs to know the file must be attached again.
    expect(omittedTransientUploads).toBe(1);
    expect(unsupportedEmbeds).toBe(0);
    expect(JSON.stringify(canonical)).not.toContain("journiv-upload");
    expect(JSON.stringify(canonical)).not.toContain("upload-1");
    expect(canonical).toEqual({ ops: [{ insert: "Writing\nmore\n" }] });
  });

  it("reports an embed kind it does not understand as unsupported", () => {
    const {
      delta: canonical,
      omittedTransientUploads,
      unsupportedEmbeds,
    } = canonicalizeDeltaForDraft(
      delta([{ insert: { formula: "e=mc^2" } }, { insert: "\n" }]),
    );
    expect(unsupportedEmbeds).toBe(1);
    expect(omittedTransientUploads).toBe(0);
    expect(JSON.stringify(canonical)).not.toContain("formula");
  });

  it("keeps the two kinds of omission apart in one document", () => {
    const { omittedTransientUploads, unsupportedEmbeds } =
      canonicalizeDeltaForDraft(
        delta([
          { insert: "Words\n" },
          { insert: { image: signed(PHOTO, "a") } },
          { insert: { "journiv-upload": { uploadId: "u1" } } },
          { insert: { image: "/media/legacy/holiday.jpg" } },
          { insert: "\n" },
        ]),
      );
    expect(omittedTransientUploads).toBe(1);
    expect(unsupportedEmbeds).toBe(1);
  });
});

describe("rehydrateDraftDelta", () => {
  it("resolves media ids to fresh signed URLs", () => {
    const { delta: canonical } = canonicalizeDeltaForDraft(
      delta([
        { insert: "Before\n" },
        { insert: { image: signed(PHOTO, "stale") } },
        { insert: { audio: signed(CLIP, "stale") } },
        { insert: "After\n" },
      ]),
    );

    const { delta: live, unresolvedMediaCount } = rehydrateDraftDelta(
      canonical,
      new Map([
        [PHOTO, signed(PHOTO, "fresh-one")],
        [CLIP, signed(CLIP, "fresh-two")],
      ]),
    );

    expect(unresolvedMediaCount).toBe(0);
    expect(live).toEqual({
      ops: [
        { insert: "Before\n" },
        { insert: { image: signed(PHOTO, "fresh-one") } },
        { insert: { audio: signed(CLIP, "fresh-two") } },
        { insert: "After\n" },
      ],
    });
    expect(isEditableDocumentDelta(live)).toBe(true);
  });

  it("drops media the Moment no longer lists, and counts it", () => {
    const { delta: canonical } = canonicalizeDeltaForDraft(
      delta([
        { insert: { image: signed(PHOTO, "x") } },
        { insert: { audio: signed(CLIP, "y") } },
        { insert: "\n" },
      ]),
    );

    const { delta: live, unresolvedMediaCount } = rehydrateDraftDelta(
      canonical,
      // The audio is gone, and the server also reports one with no signed URL.
      new Map([[PHOTO, signed(PHOTO, "fresh")]]),
    );

    expect(unresolvedMediaCount).toBe(1);
    expect(live).toEqual({
      ops: [{ insert: { image: signed(PHOTO, "fresh") } }, { insert: "\n" }],
    });
  });

  it("treats media with no signed URL as unresolved rather than inserting null", () => {
    const { delta: canonical } = canonicalizeDeltaForDraft(
      delta([{ insert: { image: signed(PHOTO, "x") } }, { insert: "\n" }]),
    );
    const { delta: live, unresolvedMediaCount } = rehydrateDraftDelta(
      canonical,
      new Map([[PHOTO, null]]),
    );
    expect(unresolvedMediaCount).toBe(1);
    expect(JSON.stringify(live)).not.toContain("null");
  });
});

describe("draftMediaIds", () => {
  it("lists the durable ids a draft depends on, once each", () => {
    const { delta: canonical } = canonicalizeDeltaForDraft(
      delta([
        { insert: { image: signed(PHOTO, "a") } },
        { insert: { image: signed(PHOTO, "b") } },
        { insert: { audio: signed(CLIP, "c") } },
        { insert: "\n" },
      ]),
    );
    expect(draftMediaIds(canonical)).toEqual([PHOTO, CLIP]);
  });

  it("is empty for a text-only draft", () => {
    const { delta: canonical } = canonicalizeDeltaForDraft(
      delta([{ insert: "Just words\n" }]),
    );
    expect(draftMediaIds(canonical)).toEqual([]);
  });
});

describe("draftContentEquals", () => {
  it("ignores signature rotation, so an unchanged draft is not offered back", () => {
    const stored = delta([
      { insert: "Morning\n" },
      { insert: { image: signed(PHOTO, "signed-yesterday") } },
      { insert: "\n" },
    ]);
    const reloaded = delta([
      { insert: "Morning\n" },
      { insert: { image: signed(PHOTO, "signed-just-now") } },
      { insert: "\n" },
    ]);

    expect(stored).not.toEqual(reloaded);
    expect(draftContentEquals(stored, reloaded)).toBe(true);
  });

  it("still sees a real edit", () => {
    expect(
      draftContentEquals(
        delta([{ insert: "Morning\n" }]),
        delta([{ insert: "Morning and more\n" }]),
      ),
    ).toBe(false);
  });

  it("sees a different photo as a different document", () => {
    expect(
      draftContentEquals(
        delta([{ insert: { image: signed(PHOTO, "a") } }, { insert: "\n" }]),
        delta([{ insert: { image: signed(CLIP, "a") } }, { insert: "\n" }]),
      ),
    ).toBe(false);
  });

  it("does not throw on a media-bearing document", () => {
    // `deltasEqual` from deltaProfile would: it validates with the text-only
    // Gate-1 guard, which rejects every embed.
    expect(() =>
      draftComparisonKey(
        delta([{ insert: { image: signed(PHOTO, "a") } }, { insert: "\n" }]),
      ),
    ).not.toThrow();
  });

  it("compares a live document against its own stored canonical form", () => {
    const live = delta([
      { insert: "Kept\n" },
      { insert: { image: signed(PHOTO, "live") } },
      { insert: "\n" },
    ]);
    const { delta: stored } = canonicalizeDeltaForDraft(live);
    expect(draftContentEquals(live, stored)).toBe(true);
  });
});

describe("isDurableDraftDelta", () => {
  it("rejects a document still carrying signed URLs", () => {
    expect(
      isDurableDraftDelta(
        delta([{ insert: { image: signed(PHOTO, "a") } }, { insert: "\n" }]),
      ),
    ).toBe(false);
  });

  it("rejects a non-document", () => {
    expect(isDurableDraftDelta(null)).toBe(false);
    expect(isDurableDraftDelta({})).toBe(false);
    expect(isDurableDraftDelta({ ops: "nope" })).toBe(false);
  });

  it("accepts a canonical document", () => {
    expect(
      isDurableDraftDelta({
        ops: [{ insert: "Hi\n" }, { insert: { image: PHOTO } }],
      }),
    ).toBe(true);
  });
});
