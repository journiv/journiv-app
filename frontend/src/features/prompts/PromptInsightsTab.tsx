import { useQuery } from "@tanstack/react-query";
import { TriangleAlert } from "lucide-react";
import { promptAnalyticsQuery } from "../../api/query/options";
import { StatusView } from "../../components/journiv/StatusView";
import { Button } from "../../components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "../../components/ui/card";
import { Skeleton } from "../../components/ui/skeleton";
import { PromptCompletionTrendChart } from "./charts/PromptCompletionTrendChart";
import { categoryLabel } from "./promptDisplay";

const NUMBER = new Intl.NumberFormat();

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="jv-prompts__stat">
      <dt className="jv-caption">{label}</dt>
      <dd className="jv-prompts__stat-value">{value}</dd>
    </div>
  );
}

/** The signed-in writer's prompt history. This panel is only mounted while the
 * Insights tab is active, keeping the Discover route's request footprint small. */
export function PromptInsightsTab() {
  const analytics = useQuery(promptAnalyticsQuery());

  if (analytics.isLoading) {
    return (
      <div
        className="jv-prompts__analytics"
        role="status"
        aria-label="Loading prompt insights"
      >
        <div className="jv-prompts__summary">
          {["a", "b", "c"].map((key) => (
            <div className="jv-prompts__stat" key={key}>
              <Skeleton height="0.75rem" width="60%" />
              <Skeleton height="1.25rem" width="45%" />
            </div>
          ))}
        </div>
        <Skeleton height="14rem" width="100%" />
      </div>
    );
  }

  if (analytics.isError || !analytics.data) {
    return (
      <StatusView
        role="alert"
        tone="danger"
        icon={<TriangleAlert size={20} />}
        title="Prompt insights could not be loaded"
        description="Check your connection and try again."
        action={
          <Button variant="secondary" onClick={() => analytics.refetch()}>
            Try again
          </Button>
        }
      />
    );
  }

  const data = analytics.data;
  if (data.total_answers === 0) {
    return (
      <StatusView
        title="No prompt entries yet"
        description="Write from a prompt to begin seeing your progress here."
      />
    );
  }

  return (
    <div className="jv-prompts__analytics">
      <dl className="jv-prompts__summary" aria-label="Prompt summary">
        <Stat
          label="Prompts answered"
          value={NUMBER.format(data.prompts_answered)}
        />
        <Stat label="Total answers" value={NUMBER.format(data.total_answers)} />
        <Stat
          label="Prompt-day streak"
          value={`${NUMBER.format(data.current_streak)} ${
            data.current_streak === 1 ? "day" : "days"
          }`}
        />
      </dl>

      <Card role="region" aria-label="Completion trend">
        <CardHeader>
          <CardTitle>
            <h2 className="jv-label">Completion trend</h2>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <PromptCompletionTrendChart data={data.completion_trend} />
        </CardContent>
      </Card>

      <Card role="region" aria-label="Favourite categories">
        <CardHeader>
          <CardTitle>
            <h2 className="jv-label">Favourite categories</h2>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ul
            className="jv-prompts__categories"
            aria-label="Favourite categories"
          >
            {data.favorite_categories.map((category) => (
              <li key={category.category}>
                <span>{categoryLabel(category.category)}</span>
                <span className="jv-caption">
                  {NUMBER.format(category.answered_count)}{" "}
                  {category.answered_count === 1 ? "answer" : "answers"}
                </span>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
