import type { MomentResponse } from "../api/generated/types.gen";

/**
 * A Moment is a container. An Entry is optional, and so is everything else.
 * Journiv must never fabricate a title for a Moment that does not have one:
 * see DESIGN.md "Moment rendering semantics".
 */
export type MomentKind =
  | "titled-entry"
  | "untitled-entry"
  | "note-only"
  | "media-only"
  | "marker-only";

export function momentKind(moment: MomentResponse): MomentKind {
  if (moment.entry) {
    return moment.entry.title?.trim() ? "titled-entry" : "untitled-entry";
  }
  if (moment.note?.trim()) return "note-only";
  if ((moment.media_count ?? 0) > 0) return "media-only";
  return "marker-only";
}

/**
 * The Moment's own title, or null. Callers must handle null by falling back to
 * the date as the heading — never by inventing placeholder text.
 */
export function momentTitle(moment: MomentResponse): string | null {
  return moment.entry?.title?.trim() || null;
}

/**
 * The text a list row should show as its body. For a titled entry this is a
 * supporting excerpt; for the other kinds it is the Moment's actual content and
 * is therefore the row's primary content.
 */
export function momentLeadText(moment: MomentResponse): string | null {
  const kind = momentKind(moment);
  if (kind === "note-only") return moment.note?.trim() || null;
  return moment.entry?.content_plain_text?.trim() || null;
}

const MEDIA_NOUNS = {
  image: ["photo", "photos"],
  video: ["video", "videos"],
  audio: ["audio clip", "audio clips"],
} as const;

/**
 * Counts are type-aware: not every attachment is a photo. When the Moment
 * carries more than one kind — or when the thumbnail list is unavailable so the
 * kinds are unknown — fall back to the neutral "item" wording rather than
 * guessing.
 */
export function mediaCountLabel(moment: MomentResponse): string | null {
  const count = moment.media_count ?? 0;
  if (count === 0) return null;
  const kinds = new Set((moment.media ?? []).map((item) => item.media_type));
  const only = kinds.size === 1 ? [...kinds][0] : null;
  const nouns =
    only && only in MEDIA_NOUNS
      ? MEDIA_NOUNS[only as keyof typeof MEDIA_NOUNS]
      : null;
  const [singular, plural] = nouns ?? ["item", "items"];
  return `${count} ${count === 1 ? singular : plural}`;
}

/** Short human label for Moments that are not a written entry. */
export function momentKindLabel(
  moment: MomentResponse,
  kind = momentKind(moment),
): string | null {
  if (kind === "note-only") return "Note";
  if (kind === "media-only") return mediaCountLabel(moment);
  if (kind === "marker-only") return "No writing yet";
  return null;
}

export function truncate(value: string, max = 220) {
  if (max <= 0) return "";
  const text = value.trim();
  return text.length > max ? `${text.slice(0, max - 1).trimEnd()}…` : text;
}
