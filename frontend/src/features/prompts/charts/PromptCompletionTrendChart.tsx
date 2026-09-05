import { useMemo } from "react";
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts";
import type { PromptCompletionWeek } from "../../../api/generated/types.gen";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "../../../components/ui/chart";
import { usePrefersReducedMotion } from "../../insights/usePrefersReducedMotion";

const CONFIG: ChartConfig = {
  answered_count: { label: "Prompt answers", color: "var(--chart-1)" },
};

const WEEK = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});

function weekLabel(iso: string) {
  return WEEK.format(new Date(`${iso}T00:00:00Z`));
}

/** Prompt-linked Moments completed by calendar week. The hidden table provides
 * the same values to assistive technology as the visual chart. */
export function PromptCompletionTrendChart({
  data,
}: {
  data: PromptCompletionWeek[];
}) {
  const reduceMotion = usePrefersReducedMotion();
  const rows = useMemo(
    () =>
      data.map((point) => ({
        ...point,
        label: weekLabel(point.week_start),
      })),
    [data],
  );

  return (
    <figure className="jv-prompts__figure">
      <ChartContainer config={CONFIG} className="jv-prompts__chart aspect-auto">
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
            dataKey="answered_count"
            name="Prompt answers"
            type="monotone"
            stroke="var(--color-answered_count)"
            fill="var(--color-answered_count)"
            fillOpacity={0.18}
            strokeWidth={2}
            isAnimationActive={!reduceMotion}
          />
        </AreaChart>
      </ChartContainer>
      <figcaption className="sr-only">
        <table>
          <caption>Prompt answers by week</caption>
          <thead>
            <tr>
              <th scope="col">Week beginning</th>
              <th scope="col">Prompt answers</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.week_start}>
                <td>{row.label}</td>
                <td>{row.answered_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </figcaption>
    </figure>
  );
}
