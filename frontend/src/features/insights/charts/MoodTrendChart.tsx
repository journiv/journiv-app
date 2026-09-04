import { useMemo } from "react";
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts";
import type { MoodDailyTrend } from "../../../api/generated/types.gen";
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "../../../components/ui/chart";
import { MOOD_CATEGORY_ORDER, moodCategoryMeta } from "../moodCategories";
import { usePrefersReducedMotion } from "../usePrefersReducedMotion";

const CONFIG: ChartConfig = MOOD_CATEGORY_ORDER.reduce((config, category) => {
  const meta = moodCategoryMeta(category);
  config[category] = { label: meta.label, color: meta.cssVar };
  return config;
}, {} as ChartConfig);

const SHORT_DATE = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});

function shortDate(iso: string) {
  return SHORT_DATE.format(new Date(`${iso}T00:00:00Z`));
}

type Row = { date: string; label: string } & Record<string, number | string>;

/** Pivot the flat `[{date, category, count}]` trend into one row per day with a
 *  column per mood category, zero-filled so the stack is continuous. */
function pivot(trends: MoodDailyTrend[]): Row[] {
  const byDate = new Map<string, Row>();
  for (const trend of trends) {
    let row = byDate.get(trend.date);
    if (!row) {
      row = { date: trend.date, label: shortDate(trend.date) };
      for (const category of MOOD_CATEGORY_ORDER) row[category] = 0;
      byDate.set(trend.date, row);
    }
    const key = MOOD_CATEGORY_ORDER.includes(
      trend.category as (typeof MOOD_CATEGORY_ORDER)[number],
    )
      ? trend.category
      : "neutral";
    row[key] = ((row[key] as number) ?? 0) + trend.count;
  }
  return [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
}

/**
 * Mood logs per day, stacked by category over the selected Trend period. Honest
 * volume + composition, no invented mood scale. A visually-hidden table mirrors
 * the values.
 */
export function MoodTrendChart({ trends }: { trends: MoodDailyTrend[] }) {
  const reduceMotion = usePrefersReducedMotion();
  const rows = useMemo(() => pivot(trends), [trends]);

  if (rows.length === 0) {
    return <p className="jv-caption">No mood logs in this period yet.</p>;
  }

  return (
    <figure className="jv-insights__figure">
      <ChartContainer
        config={CONFIG}
        className="jv-insights__chart aspect-auto"
      >
        <AreaChart data={rows} margin={{ left: 4, right: 8, top: 4 }}>
          <CartesianGrid vertical={false} />
          <XAxis
            dataKey="label"
            tickLine={false}
            axisLine={false}
            tickMargin={8}
            minTickGap={24}
          />
          <YAxis
            width={28}
            tickLine={false}
            axisLine={false}
            allowDecimals={false}
          />
          <ChartTooltip content={<ChartTooltipContent />} />
          <ChartLegend content={<ChartLegendContent />} />
          {MOOD_CATEGORY_ORDER.map((category) => (
            <Area
              key={category}
              dataKey={category}
              name={moodCategoryMeta(category).label}
              type="monotone"
              stackId="mood"
              stroke={`var(--color-${category})`}
              fill={`var(--color-${category})`}
              fillOpacity={0.2}
              strokeWidth={2}
              isAnimationActive={!reduceMotion}
            />
          ))}
        </AreaChart>
      </ChartContainer>
      <figcaption className="sr-only">
        <table>
          <caption>Mood logs per day by category</caption>
          <thead>
            <tr>
              <th scope="col">Date</th>
              {MOOD_CATEGORY_ORDER.map((category) => (
                <th key={category} scope="col">
                  {moodCategoryMeta(category).label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.date}>
                <td>{row.label}</td>
                {MOOD_CATEGORY_ORDER.map((category) => (
                  <td key={category}>{row[category] as number}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </figcaption>
    </figure>
  );
}
