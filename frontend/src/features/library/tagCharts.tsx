/**
 * Small, tokened data marks for the Tags workspace (DESIGN.md §24). Journiv has
 * no chart library and does not want one — these are the minimum needed to make
 * tag analytics legible: a stat-tile row, a horizontal distribution bar set and
 * a single-series sparkline. One series only, drawn in `--chart-1`; tracks in
 * `--border`; every label a typographic role. Feature-local until a second
 * surface needs them (DESIGN.md §18).
 */
import { useId } from "react";

export function StatTiles({
  items,
}: {
  items: { label: string; value: string }[];
}) {
  return (
    <dl className="jv-tag-stats">
      {items.map((item) => (
        <div className="jv-tag-stats__tile" key={item.label}>
          <dt className="jv-caption">{item.label}</dt>
          <dd className="jv-tag-stats__value">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * Horizontal bars for a small labelled distribution (e.g. tag usage buckets).
 * Each row is label · track · count; the widest bar fills the track.
 */
export function DistributionBars({
  data,
  ariaLabel,
}: {
  data: { label: string; value: number }[];
  ariaLabel: string;
}) {
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <ul className="jv-tag-bars" aria-label={ariaLabel}>
      {data.map((row) => (
        <li className="jv-tag-bars__row" key={row.label}>
          <span className="jv-tag-bars__label jv-meta">{row.label}</span>
          <span className="jv-tag-bars__track" aria-hidden="true">
            <span
              className="jv-tag-bars__fill"
              style={{ inlineSize: `${(row.value / max) * 100}%` }}
            />
          </span>
          <span className="jv-tag-bars__value jv-meta">{row.value}</span>
        </li>
      ))}
    </ul>
  );
}

/**
 * A single-series sparkline over an ordered set of points. `labels` are the
 * x-axis keys (month strings); only the first and last are printed. Renders
 * nothing meaningful below two points — the caller guards that.
 */
export function Sparkline({
  points,
  labels,
  ariaLabel,
}: {
  points: number[];
  labels: string[];
  ariaLabel: string;
}) {
  const gradientId = useId();
  const width = 100;
  const height = 32;
  const max = Math.max(1, ...points);
  const step = points.length > 1 ? width / (points.length - 1) : 0;
  const coords = points.map((value, index) => {
    const x = index * step;
    const y = height - (value / max) * height;
    return [x, y] as const;
  });
  const line = coords.map(([x, y]) => `${x},${y}`).join(" ");
  const area = `${line} ${width},${height} 0,${height}`;

  return (
    <figure className="jv-tag-spark">
      <svg
        className="jv-tag-spark__svg"
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={ariaLabel}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="var(--chart-1)" stopOpacity="0.24" />
            <stop offset="100%" stopColor="var(--chart-1)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <polygon points={area} fill={`url(#${gradientId})`} />
        <polyline
          points={line}
          fill="none"
          stroke="var(--chart-1)"
          strokeWidth="1.5"
          strokeLinejoin="round"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
      {labels.length > 1 && (
        <figcaption className="jv-tag-spark__axis jv-caption">
          <span>{labels[0]}</span>
          <span>{labels[labels.length - 1]}</span>
        </figcaption>
      )}
    </figure>
  );
}
