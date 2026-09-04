import { MOOD_CATEGORY_ORDER, moodCategoryMeta } from "../moodCategories";

/**
 * Share of mood logs by category, as a small labelled bar set (not a chart
 * library mark). `mood_distribution` is already a percentage per category.
 */
export function MoodDistributionBars({
  distribution,
}: {
  distribution: Record<string, number>;
}) {
  const rows = MOOD_CATEGORY_ORDER.filter(
    (category) => (distribution[category] ?? 0) > 0,
  );

  if (rows.length === 0) {
    return <p className="jv-caption">No mood logs in this period yet.</p>;
  }

  return (
    <ul className="jv-insights__bars" aria-label="Mood distribution">
      {rows.map((category) => {
        const meta = moodCategoryMeta(category);
        const pct = Math.round(distribution[category] ?? 0);
        return (
          <li className="jv-insights__bar-row" key={category}>
            <span className="jv-insights__bar-label jv-meta">{meta.label}</span>
            <span className="jv-insights__bar-track" aria-hidden="true">
              <span
                className="jv-insights__bar-fill"
                style={{ inlineSize: `${pct}%`, background: meta.cssVar }}
              />
            </span>
            <span className="jv-insights__bar-value jv-meta">{pct}%</span>
          </li>
        );
      })}
    </ul>
  );
}
