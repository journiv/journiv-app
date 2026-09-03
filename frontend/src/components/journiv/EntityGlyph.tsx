import type { CSSProperties } from "react";
import { colorFromArgb } from "../../lib/color";
import { cx } from "../../lib/cx";
import { resolveJournalIcon } from "../../lib/journalIcons";

/**
 * A Library entity's identity mark, mirroring `JournalDot` (DESIGN.md) for
 * the entities whose colour arrives as either a Flutter ARGB integer (person,
 * activity, mood and goal groups) or a validated six-digit hex string
 * (activities).
 *
 * When the entity carries a recognised icon key (the curated Lucide set in
 * `journalIcons.ts`, which is a generic vocabulary despite the name), the glyph
 * is drawn in the entity's own hue in place of the dot. An unrecognised value —
 * notably a Material Symbols name written by the Flutter client — falls back to
 * the plain dot. Colour is the one hue allowed into the chrome.
 *
 * The hue enters as an inline `--entity-accent`, exactly as `--journal-accent`
 * and `--mood-accent` do (DESIGN.md); it is never written to a stylesheet.
 */
export function EntityGlyph({
  colorValue,
  color,
  icon,
  size = 10,
  className,
}: {
  colorValue?: number | null;
  /** Hex colour used by Activity responses. Invalid values fall back to the
   *  neutral identity mark instead of entering an inline style. */
  color?: string | null;
  icon?: string | null;
  /** Glyph size in px. Ignored for the plain dot, which is fixed by CSS. */
  size?: number;
  className?: string;
}) {
  const hex = /^#[0-9a-f]{6}$/i.test(color ?? "")
    ? (color as string)
    : colorFromArgb(colorValue);
  const tint = hex ? ({ "--entity-accent": hex } as CSSProperties) : undefined;
  const Icon = resolveJournalIcon(icon);
  if (Icon) {
    return (
      <span
        className={cx("jv-entity-glyph", className)}
        style={tint}
        aria-hidden="true"
      >
        <Icon size={size} />
      </span>
    );
  }
  return (
    <span
      className={cx("jv-entity-dot", className)}
      style={tint}
      aria-hidden="true"
    />
  );
}
