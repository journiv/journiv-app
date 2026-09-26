/**
 * The bars of a waveform, drawn as one stroked path in `currentColor`. Shared by
 * the stored-audio player and the live recording meter so the two look like the
 * same thing. Purely decorative: `aria-hidden`, and the owning control carries
 * the accessible name.
 */
const VIEW_WIDTH = 400;
const VIEW_HEIGHT = 48;
const MIN_BAR = 2;

export function WaveformBars({
  bars,
  className,
}: {
  /** Levels in 0..1. */
  bars: readonly number[];
  className?: string;
}) {
  if (bars.length === 0) return null;
  const step = VIEW_WIDTH / bars.length;
  const path = bars
    .map((level, index) => {
      const height = Math.max(MIN_BAR, level * VIEW_HEIGHT);
      const x = index * step + step / 2;
      const top = (VIEW_HEIGHT - height) / 2;
      return `M${x.toFixed(2)} ${top.toFixed(2)}v${height.toFixed(2)}`;
    })
    .join("");
  return (
    <svg
      className={className}
      viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
      preserveAspectRatio="none"
      aria-hidden="true"
      focusable="false"
    >
      <path
        d={path}
        fill="none"
        stroke="currentColor"
        strokeWidth={step * 0.55}
        strokeLinecap="butt"
      />
    </svg>
  );
}
