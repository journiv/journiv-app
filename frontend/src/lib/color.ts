import { JOURNAL_COLORS } from "./journalColors";

/**
 * The Flutter client stores colours as ARGB integers (`primary_mood_id`,
 * `PersonGroup.color_value`, …). Journiv's chrome needs a CSS hex string, and
 * only the low 24 bits carry the hue — the alpha byte is ignored. This is the
 * one translation; `MomentMeta` re-exports it as `moodColor` for its callers.
 * Returns `undefined` (not a guessed colour) when there is no usable value, so
 * `JournalDot`-style fallbacks (`var(--entity-accent, var(--line-strong))`)
 * take over. See DESIGN.md §3.
 */
export function colorFromArgb(value?: number | null): string | undefined {
  if (typeof value !== "number" || !Number.isFinite(value)) return undefined;
  return `#${(value & 0xffffff).toString(16).padStart(6, "0")}`;
}

/**
 * Inverse of {@link colorFromArgb}: a `#rrggbb` preset back to a full-opacity
 * ARGB integer for `color_value` writes. Returns `null` for anything that is not
 * a six-digit hex string.
 */
export function argbFromHex(hex: string): number | null {
  const match = /^#?([0-9a-fA-F]{6})$/.exec(hex.trim());
  if (!match) return null;
  return (0xff000000 | Number.parseInt(match[1], 16)) >>> 0;
}

/**
 * The colour presets offered when a Library entity (a person group, later a
 * mood or activity) carries a `color_value`. The palette is shared with the
 * journal picker so the product reads as one system; the values are plain
 * hues here, not an API enum contract.
 */
export const ENTITY_COLOR_PRESETS: ReadonlyArray<{
  hex: string;
  label: string;
}> = JOURNAL_COLORS.map((color) => ({ hex: color.value, label: color.label }));
