import type { QuillDelta } from "../../../api/generated/types.gen";
import blockquote from "./blockquote.json";
import combined from "./combined.json";
import empty from "./empty.json";
import headings from "./headings.json";
import inlineAudio from "./inline-audio.json";
import inlineImage from "./inline-image.json";
import inlineMarks from "./inline-marks.json";
import inlineMediaCombined from "./inline-media-combined.json";
import inlineVideo from "./inline-video.json";
import links from "./links.json";
import lists from "./lists.json";
import multipleParagraphs from "./multiple-paragraphs.json";
import plainParagraph from "./plain-paragraph.json";
import unicode from "./unicode.json";

export const CANONICAL_DELTA_FIXTURES = [
  ["empty", empty],
  ["plain paragraph", plainParagraph],
  ["multiple paragraphs", multipleParagraphs],
  ["Unicode", unicode],
  ["inline marks", inlineMarks],
  ["links", links],
  ["headings", headings],
  ["lists", lists],
  ["blockquote", blockquote],
  ["combined", combined],
] as const satisfies readonly (readonly [string, QuillDelta])[];

/**
 * Inline media fixtures.
 *
 * Deliberately a SEPARATE registry: these are not Gate-1 documents. The editor
 * profile still rejects every embed, so `CANONICAL_DELTA_FIXTURES` must keep
 * asserting that. These prove the reader and the cross-runtime round trip.
 *
 * Persisted form is a bare media id — never a signed URL. See DESIGN.md §13.
 */
export const CANONICAL_MEDIA_FIXTURES = [
  ["inline image", inlineImage],
  ["inline video", inlineVideo],
  ["inline audio", inlineAudio],
  ["inline media combined", inlineMediaCombined],
] as const satisfies readonly (readonly [string, QuillDelta])[];
