import { describe, expect, it } from "vitest";
import type { MomentResponse } from "../api/generated/types.gen";
import {
  mediaCountLabel,
  momentKind,
  momentKindLabel,
  momentLeadText,
  momentTitle,
  truncate,
} from "./moment";

const base = {
  id: "m1",
  user_id: "u1",
  logged_at_utc: "2026-08-17T18:04:00Z",
  logged_date_tz: "2026-08-17",
  logged_timezone: "America/Los_Angeles",
  is_pinned: false,
  mood_activity: [],
  tags: [],
  people: [],
  media: [],
} as unknown as MomentResponse;

const withMedia = (count: number, types: string[]) =>
  ({
    ...base,
    media_count: count,
    media: types.map((media_type, index) => ({ id: `m${index}`, media_type })),
  }) as unknown as MomentResponse;

const withEntry = (title: string | null, text = "Some writing.") =>
  ({
    ...base,
    entry: { id: "e1", title, content_plain_text: text },
  }) as unknown as MomentResponse;

describe("Moment rendering semantics", () => {
  it("classifies each kind of Moment", () => {
    expect(momentKind(withEntry("Kyoto"))).toBe("titled-entry");
    expect(momentKind(withEntry(null))).toBe("untitled-entry");
    expect(
      momentKind({ ...base, note: "Saw a heron." } as MomentResponse),
    ).toBe("note-only");
    expect(momentKind({ ...base, media_count: 2 } as MomentResponse)).toBe(
      "media-only",
    );
    expect(momentKind({ ...base, is_pinned: true } as MomentResponse)).toBe(
      "marker-only",
    );
  });

  it("never invents a title", () => {
    expect(momentTitle(withEntry("Kyoto"))).toBe("Kyoto");
    expect(momentTitle(withEntry(null))).toBeNull();
    expect(momentTitle(withEntry("   "))).toBeNull();
    expect(
      momentTitle({ ...base, note: "Saw a heron." } as MomentResponse),
    ).toBeNull();
  });

  it("does not promote a note into the title slot", () => {
    const noteOnly = { ...base, note: "Saw a heron." } as MomentResponse;
    expect(momentTitle(noteOnly)).toBeNull();
    expect(momentLeadText(noteOnly)).toBe("Saw a heron.");
    expect(momentKindLabel(noteOnly)).toBe("Note");
  });

  it("labels media-only Moments by their real count and type", () => {
    expect(momentKindLabel(withMedia(1, ["image"]))).toBe("1 photo");
    expect(momentKindLabel(withMedia(3, ["image", "image", "image"]))).toBe(
      "3 photos",
    );
    expect(momentKindLabel(withEntry("Kyoto"))).toBeNull();
  });

  it("never assumes an attachment is a photo", () => {
    expect(mediaCountLabel(withMedia(1, ["video"]))).toBe("1 video");
    expect(mediaCountLabel(withMedia(2, ["video", "video"]))).toBe("2 videos");
    expect(mediaCountLabel(withMedia(1, ["audio"]))).toBe("1 audio clip");
    // Mixed kinds, and unknown kinds, both fall back to neutral wording.
    expect(mediaCountLabel(withMedia(2, ["image", "video"]))).toBe("2 items");
    expect(mediaCountLabel({ ...base, media_count: 4 } as MomentResponse)).toBe(
      "4 items",
    );
    expect(mediaCountLabel(base)).toBeNull();
  });

  it("returns no text for a non-positive truncation limit", () => {
    expect(truncate("Some writing.", 0)).toBe("");
    expect(truncate("Some writing.", -1)).toBe("");
    expect(truncate("Some writing.", 5)).toBe("Some…");
  });
});
