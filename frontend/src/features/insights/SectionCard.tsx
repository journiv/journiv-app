import type { UseQueryResult } from "@tanstack/react-query";
import { TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import { StatusView } from "../../components/journiv/StatusView";
import { Button } from "../../components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from "../../components/ui/card";
import { Skeleton } from "../../components/ui/skeleton";

/**
 * A titled Insights block: a stock `Card` that renders the section's own
 * loading skeleton, a pane-level error `StatusView` with retry, or the loaded
 * content. Every Insights section uses this so the empty / loading / error
 * contract (DESIGN.md) is identical across them.
 */
export function SectionCard<T>({
  title,
  action,
  query,
  children,
  isEmpty,
  emptyMessage = "Nothing to show yet.",
}: {
  title: string;
  action?: ReactNode;
  query: UseQueryResult<T>;
  children: (data: T) => ReactNode;
  isEmpty?: (data: T) => boolean;
  emptyMessage?: string;
}) {
  return (
    <Card role="region" aria-label={title}>
      <CardHeader>
        <CardTitle>
          <h2 className="jv-label">{title}</h2>
        </CardTitle>
        {action && <CardAction>{action}</CardAction>}
      </CardHeader>
      <CardContent>
        {query.isLoading && (
          <div
            className="jv-insights__figure"
            role="status"
            aria-label={`Loading ${title.toLowerCase()}`}
          >
            <Skeleton height="10rem" width="100%" />
            <Skeleton height="0.9rem" width="40%" />
          </div>
        )}

        {!query.isLoading && (query.isError || !query.data) && (
          <StatusView
            role="alert"
            tone="danger"
            icon={<TriangleAlert size={20} />}
            title={`${title} could not be loaded`}
            description="Check your connection and try again."
            action={
              <Button variant="secondary" onClick={() => query.refetch()}>
                Try again
              </Button>
            }
          />
        )}

        {!query.isLoading &&
          !query.isError &&
          query.data !== undefined &&
          query.data !== null &&
          (isEmpty?.(query.data) ? (
            <p className="jv-body jv-insights__all-time">{emptyMessage}</p>
          ) : (
            children(query.data)
          ))}
      </CardContent>
    </Card>
  );
}
