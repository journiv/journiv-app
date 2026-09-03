import type { CSSProperties } from "react";
import type { JournalResponse } from "../../api/generated/types.gen";
import { resolveJournalIcon } from "../../lib/journalIcons";
import { cx } from "../../lib/cx";

/**
 * A Journal's colour is the one place hue is allowed into the chrome.
 * `color` is a preset from the backend `JournalColor` enum and may be null —
 * fall back to the neutral line colour rather than inventing one.
 *
 * When the Journal also carries a recognised `icon` (see `journalIcons`), the
 * glyph is drawn in that same hue in place of the dot. An unrecognised icon
 * value (for example a Material Symbols name written by the Flutter client)
 * falls back to the plain dot. See DESIGN.md.
 */
export function JournalDot({
  journal,
  className,
  size = 15,
}: {
  journal?: JournalResponse;
  className?: string;
  /** Glyph size in px. Ignored for the plain dot, which is fixed by CSS. */
  size?: number;
}) {
  const tint = journal?.color
    ? ({ "--journal-accent": journal.color } as CSSProperties)
    : undefined;
  const Icon = resolveJournalIcon(journal?.icon);
  if (Icon) {
    return (
      <span
        className={cx("jv-journal-glyph", className)}
        style={tint}
        aria-hidden="true"
      >
        <Icon size={size} />
      </span>
    );
  }
  return (
    <span
      className={cx("jv-journal-dot", className)}
      style={tint}
      aria-hidden="true"
    />
  );
}

export function JournalBadge({
  journal,
  className,
}: {
  journal?: JournalResponse;
  className?: string;
}) {
  if (!journal) return null;
  return (
    <span className={cx("jv-journal-badge", className)}>
      <JournalDot journal={journal} size={13} />
      <span className="jv-truncate">{journal.title}</span>
    </span>
  );
}
