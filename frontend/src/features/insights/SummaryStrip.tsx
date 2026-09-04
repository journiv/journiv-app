import { useQuery } from "@tanstack/react-query";
import { TriangleAlert } from "lucide-react";
import { writingStreakQuery } from "../../api/query/options";
import { StatusView } from "../../components/journiv/StatusView";
import { Button } from "../../components/ui/button";
import { Skeleton } from "../../components/ui/skeleton";

const NUMBER = new Intl.NumberFormat();

function dayLabel(n: number) {
  return `${NUMBER.format(n)} ${n === 1 ? "day" : "days"}`;
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="jv-insights__stat">
      <dt className="jv-caption">{label}</dt>
      <dd className="jv-insights__stat-value">{value}</dd>
    </div>
  );
}

/**
 * The non-sticky headline row at the top of Insights. Four all-time figures
 * straight from `GET /analytics/writing-streak` — deliberately outside any tab
 * and unaffected by the Trend period control.
 */
export function SummaryStrip() {
  const streak = useQuery(writingStreakQuery());

  if (streak.isLoading) {
    return (
      <div
        className="jv-insights__summary"
        role="status"
        aria-label="Loading summary"
      >
        {["a", "b", "c", "d"].map((key) => (
          <div className="jv-insights__stat" key={key}>
            <Skeleton height="0.75rem" width="60%" />
            <Skeleton height="1.25rem" width="45%" />
          </div>
        ))}
      </div>
    );
  }

  if (streak.isError || !streak.data) {
    return (
      <StatusView
        role="alert"
        tone="danger"
        icon={<TriangleAlert size={20} />}
        title="Summary could not be loaded"
        description="Check your connection and try again."
        action={
          <Button variant="secondary" onClick={() => streak.refetch()}>
            Try again
          </Button>
        }
      />
    );
  }

  const data = streak.data;
  return (
    <dl className="jv-insights__summary" aria-label="Writing summary">
      <Stat label="Writing streak" value={dayLabel(data.current_streak ?? 0)} />
      <Stat
        label="Total entries"
        value={NUMBER.format(data.total_entries ?? 0)}
      />
      <Stat label="Total words" value={NUMBER.format(data.total_words ?? 0)} />
      <Stat
        label="Avg words / entry"
        value={NUMBER.format(Math.round(data.average_words_per_entry ?? 0))}
      />
    </dl>
  );
}
