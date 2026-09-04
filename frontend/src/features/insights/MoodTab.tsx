import { useQuery } from "@tanstack/react-query";
import { moodStatisticsQuery, moodStreakQuery } from "../../api/query/options";
import { MoodDistributionBars } from "./charts/MoodDistributionBars";
import { MoodTrendChart } from "./charts/MoodTrendChart";
import { SectionCard } from "./SectionCard";

const NUMBER = new Intl.NumberFormat();

function moodName(raw: string) {
  return raw
    .replace(/_/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(" ");
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="jv-insights__stat">
      <span className="jv-caption">{label}</span>
      <span className="jv-insights__stat-value">{value}</span>
    </div>
  );
}

export function MoodTab({ start, end }: { start: string; end: string }) {
  const stats = useQuery(moodStatisticsQuery(start, end));
  const streak = useQuery(moodStreakQuery());

  return (
    <div className="jv-insights__panel">
      <SectionCard
        title="Mood overview"
        query={stats}
        isEmpty={(data) => (data.total_logs ?? 0) === 0}
        emptyMessage="No moods logged in this period yet."
      >
        {(data) => (
          <div className="jv-insights__metrics">
            <Metric
              label="Mood logs"
              value={NUMBER.format(data.total_logs ?? 0)}
            />
            <Metric
              label="Most frequent"
              value={
                data.most_frequent_mood
                  ? moodName(data.most_frequent_mood.name)
                  : "—"
              }
            />
            <Metric
              label="Current streak"
              value={
                streak.data
                  ? `${NUMBER.format(streak.data.current_streak)} ${
                      streak.data.current_streak === 1 ? "day" : "days"
                    }`
                  : "—"
              }
            />
            <Metric
              label="Days logged"
              value={
                streak.data ? NUMBER.format(streak.data.total_days_logged) : "—"
              }
            />
          </div>
        )}
      </SectionCard>

      <SectionCard
        title="Mood over time"
        query={stats}
        isEmpty={(data) => data.daily_trends.length === 0}
        emptyMessage="No moods logged in this period yet."
      >
        {(data) => <MoodTrendChart trends={data.daily_trends} />}
      </SectionCard>

      <SectionCard
        title="Mood balance"
        query={stats}
        isEmpty={(data) => (data.total_logs ?? 0) === 0}
        emptyMessage="No moods logged in this period yet."
      >
        {(data) => (
          <MoodDistributionBars distribution={data.mood_distribution} />
        )}
      </SectionCard>
    </div>
  );
}
