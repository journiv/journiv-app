import { useMemo } from "react";
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts";
import type { EntriesByDayPoint } from "../../../api/generated/types.gen";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "../../../components/ui/chart";
import { usePrefersReducedMotion } from "../usePrefersReducedMotion";

const CONFIG: ChartConfig = {
  entry_count: { label: "Entries", color: "var(--chart-1)" },
};

const SHORT_DATE = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});

function shortDate(iso: string) {
  return SHORT_DATE.format(new Date(`${iso}T00:00:00Z`));
}

/**
 * Daily entry count over the selected Trend period. One series, `--chart-1`,
 * area fill. A visually-hidden table carries the same numbers for assistive
 * technology.
 */
export function WritingFrequencyChart({ data }: { data: EntriesByDayPoint[] }) {
  const reduceMotion = usePrefersReducedMotion();
  const rows = useMemo(
    () => data.map((point) => ({ ...point, label: shortDate(point.date) })),
    [data],
  );

  if (rows.length === 0) {
    return <p className="jv-caption">No entries in this period yet.</p>;
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
          <Area
            dataKey="entry_count"
            name="Entries"
            type="monotone"
            stroke="var(--color-entry_count)"
            fill="var(--color-entry_count)"
            fillOpacity={0.18}
            strokeWidth={2}
            isAnimationActive={!reduceMotion}
          />
        </AreaChart>
      </ChartContainer>
      <figcaption className="sr-only">
        <table>
          <caption>Entries written per day</caption>
          <thead>
            <tr>
              <th scope="col">Date</th>
              <th scope="col">Entries</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.date}>
                <td>{row.label}</td>
                <td>{row.entry_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </figcaption>
    </figure>
  );
}
