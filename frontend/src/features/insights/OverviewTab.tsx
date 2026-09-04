import { useQuery } from "@tanstack/react-query";
import {
  productivityQuery,
  writingPatternsQuery,
} from "../../api/query/options";
import { cx } from "../../lib/cx";
import { WritingFrequencyChart } from "./charts/WritingFrequencyChart";
import type { InsightsPeriod } from "./PeriodControl";
import { SectionCard } from "./SectionCard";

const NUMBER = new Intl.NumberFormat();

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="jv-insights__stat">
      <span className="jv-caption">{label}</span>
      <span className="jv-insights__stat-value">{value}</span>
    </div>
  );
}

export function OverviewTab({ period }: { period: InsightsPeriod }) {
  const patterns = useQuery(writingPatternsQuery(period));
  const productivity = useQuery(productivityQuery());

  return (
    <div className="jv-insights__panel">
      <SectionCard
        title="Writing frequency"
        query={patterns}
        isEmpty={(data) => data.entries_by_day.length === 0}
        emptyMessage="No entries in this period yet."
      >
        {(data) => <WritingFrequencyChart data={data.entries_by_day} />}
      </SectionCard>

      <SectionCard title="This month" query={productivity}>
        {(data) => {
          const growth = data.entry_growth_percentage ?? 0;
          const growthLabel =
            growth === 0
              ? "No change vs last month"
              : `${growth > 0 ? "+" : ""}${NUMBER.format(
                  Math.round(growth),
                )}% vs last month`;
          return (
            <div className="jv-insights__figure">
              <div className="jv-insights__metrics">
                <Metric
                  label="Entries this month"
                  value={NUMBER.format(data.current_month_entries ?? 0)}
                />
                <Metric
                  label="Words this month"
                  value={NUMBER.format(data.current_month_words ?? 0)}
                />
                <Metric
                  label="Avg entries / day"
                  value={(data.average_daily_entries ?? 0).toFixed(1)}
                />
                <Metric
                  label="Avg words / day"
                  value={NUMBER.format(
                    Math.round(data.average_words_per_day ?? 0),
                  )}
                />
              </div>
              <p
                className={cx(
                  "jv-meta",
                  growth > 0 && "jv-insights__delta--up",
                  growth < 0 && "jv-insights__delta--down",
                )}
              >
                {growthLabel}
              </p>
            </div>
          );
        }}
      </SectionCard>
    </div>
  );
}
