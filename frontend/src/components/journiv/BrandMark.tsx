import { cx } from "../../lib/cx";

/**
 * The Journiv identity mark: a Georgia-Italic `j` in an asymmetric rounded
 * tile (the mark v0 invented, re-drawn as a vector so it needs no font).
 *
 * The mark is fixed brand identity, not chrome: the tile is literal Journiv
 * blue `#405DE6` and the glyph is white, regardless of theme or a user's
 * accent personalization. That is deliberate — `--brand` in `tokens.css` is
 * the *customisable* UI accent; the logo must not follow it (DESIGN.md, "The
 * identity mark"). The same geometry ships as `public/favicon.svg`,
 * `public/favicon.ico` and `public/apple-touch-icon.png`.
 *
 * Accessibility: the mark is decorative (`aria-hidden`) by default — pair it
 * with visible text that names it. `wordmark` renders that text ("Journiv")
 * itself. When the mark stands alone (no adjacent brand text), pass `title`
 * so it exposes an accessible name instead of vanishing from the a11y tree.
 */
export function BrandMark({
  size = 28,
  wordmark = false,
  title,
  className,
}: {
  /** Tile edge length in px. */
  size?: number;
  /** Render the mark followed by the "Journiv" wordmark as one lockup. */
  wordmark?: boolean;
  /** Accessible name for a standalone mark. Ignored when `wordmark` is set
   *  (the visible text carries the name then). */
  title?: string;
  className?: string;
}) {
  const labelled = !wordmark && Boolean(title);
  const mark = (
    <svg
      className="jv-brand-mark"
      width={size}
      height={size}
      viewBox="0 0 32 32"
      role={labelled ? "img" : undefined}
      aria-label={labelled ? title : undefined}
      aria-hidden={labelled ? undefined : true}
    >
      <path
        d="M11.5 0H20.5A11.5 11.5 0 0 1 32 11.5V20.5A11.5 11.5 0 0 1 20.5 32H3.5A3.5 3.5 0 0 1 0 28.5V11.5A11.5 11.5 0 0 1 11.5 0Z"
        fill="#405DE6"
      />
      <path
        d="M20.05 12.23Q20.05 12.46 20 12.83Q19.94 13.19 19.88 13.5Q19.48 15.49 19.08 17.4Q18.69 19.31 18.18 21.44Q17.58 23.98 15.91 25.59Q14.25 27.2 12.38 27.2Q11.37 27.2 10.89 26.82Q10.42 26.43 10.42 25.85Q10.42 25.36 10.72 24.98Q11.01 24.6 11.57 24.6Q11.93 24.6 12.2 24.76Q12.47 24.92 12.67 25.16Q12.83 25.36 13.03 25.69Q13.23 26.02 13.38 26.26Q14.19 26.22 14.84 25.12Q15.49 24.03 15.97 21.87Q16.43 19.76 16.78 18.18Q17.13 16.61 17.52 14.59Q17.61 14.12 17.68 13.7Q17.75 13.28 17.75 12.95Q17.75 12.31 17.54 12.1Q17.33 11.89 16.67 11.89Q16.38 11.89 15.93 11.99Q15.47 12.08 15.27 12.14L15.44 11.41Q16.33 11.01 17.08 10.8Q17.83 10.59 18.26 10.59Q19.2 10.59 19.62 11.03Q20.05 11.48 20.05 12.23ZM21.58 6.26Q21.58 6.92 21.16 7.4Q20.73 7.89 20.1 7.89Q19.52 7.89 19.1 7.42Q18.68 6.96 18.68 6.37Q18.68 5.74 19.1 5.27Q19.52 4.8 20.1 4.8Q20.76 4.8 21.17 5.24Q21.58 5.68 21.58 6.26Z"
        fill="#fff"
      />
    </svg>
  );

  if (!wordmark) return <span className={className}>{mark}</span>;

  return (
    <span className={cx("jv-brand-lockup", className)}>
      {mark}
      <span className="jv-brand-lockup__text">Journiv</span>
    </span>
  );
}
