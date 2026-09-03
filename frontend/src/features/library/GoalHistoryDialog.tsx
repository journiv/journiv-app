import { useQuery } from "@tanstack/react-query";
import { Check, History, Minus, TriangleAlert, X } from "lucide-react";
import type { ComponentType } from "react";
import type {
  GoalFrequency,
  GoalLogResponse,
  GoalLogStatus,
  GoalWithProgressResponse,
} from "../../api/generated/types.gen";
import { goalLogsQuery } from "../../api/query/options";
import { AppAdaptiveDialog } from "../../components/journiv/AppAdaptiveDialog";
import { StatusView } from "../../components/journiv/StatusView";
import { Button } from "../../components/ui/button";
import { Skeleton } from "../../components/ui/skeleton";

/**
 * Read-only completion history for one goal — the `GET /goals/{id}/logs`
 * response the directory rows never surfaced. Opened from a goal's ⋯ menu.
 * Each row is one evaluated period, newest first: a status mark, the period
 * label (shaped by the goal's cadence), and the count / target plus whether the
 * period was logged automatically or by hand. No primary action — the surface's
 * one primary stays "Add goal" on the page behind it (docs/features/library.md, and the
 * Details-popover precedent in docs/features/editor.md).
 */

type StatusTone = {
  label: string;
  Icon: ComponentType<{ size?: number; "aria-hidden"?: boolean }>;
  badge: string;
};

const STATUS_META: Record<GoalLogStatus, StatusTone> = {
  success: {
    label: "Completed",
    Icon: Check,
    badge: "bg-primary/10 text-primary",
  },
  fail: {
    label: "Missed",
    Icon: X,
    badge: "bg-destructive/10 text-destructive",
  },
  skipped: {
    label: "Skipped",
    Icon: Minus,
    badge: "bg-muted text-muted-foreground",
  },
};

/** Format a bare `YYYY-MM-DD` as a calendar date, no timezone shift — these
 *  fields have no zone of their own, so they are read in UTC verbatim. */
function formatBareDate(date: string, opts: Intl.DateTimeFormatOptions) {
  const [y, m, d] = date.split("-").map(Number);
  if (!y || !m || !d) return date;
  return new Intl.DateTimeFormat(undefined, {
    ...opts,
    timeZone: "UTC",
  }).format(new Date(Date.UTC(y, m - 1, d)));
}

function periodLabel(log: GoalLogResponse, frequency: GoalFrequency) {
  if (frequency === "monthly") {
    return formatBareDate(log.period_start, { month: "long", year: "numeric" });
  }
  if (frequency === "weekly") {
    const start = formatBareDate(log.period_start, {
      day: "numeric",
      month: "short",
    });
    const end = formatBareDate(log.period_end, {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
    return `${start} – ${end}`;
  }
  return formatBareDate(log.period_start, {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function sourceLabel(source: string) {
  if (source === "auto") return "Logged automatically";
  if (source === "manual") return "Logged by you";
  return null;
}

function metaLine(log: GoalLogResponse, target: number) {
  const status = STATUS_META[log.status]?.label ?? log.status;
  return [status, `${log.count}/${target}`, sourceLabel(log.source)]
    .filter(Boolean)
    .join(" · ");
}

function HistorySkeleton() {
  return (
    <ul
      className="divide-y divide-border"
      role="status"
      aria-label="Loading history"
    >
      {["a", "b", "c", "d"].map((row) => (
        <li key={row} className="flex items-center gap-3 py-3">
          <Skeleton height="1.75rem" width="1.75rem" />
          <span className="flex flex-col gap-1.5">
            <Skeleton height="0.9rem" width="9rem" />
            <Skeleton height="0.75rem" width="12rem" />
          </span>
        </li>
      ))}
    </ul>
  );
}

export function GoalHistoryDialog({
  goal,
  onClose,
}: {
  goal: GoalWithProgressResponse;
  onClose: () => void;
}) {
  const logsResult = useQuery(goalLogsQuery(goal.id));
  const logs = logsResult.data ?? [];
  const target = goal.target_count ?? 1;
  const frequency = goal.frequency_type ?? "daily";

  return (
    <AppAdaptiveDialog
      open
      onOpenChange={(open) => !open && onClose()}
      title={`${goal.title} history`}
      description="Completion for each recent period."
      footer={
        <Button variant="secondary" onClick={onClose}>
          Close
        </Button>
      }
    >
      {/* The overlay body is already the scroll owner (DESIGN.md), so this
          section only names the region — it must not scroll on its own. */}
      <section aria-label="Goal completion history">
        {logsResult.isLoading && <HistorySkeleton />}

        {logsResult.isError && (
          <StatusView
            role="alert"
            tone="danger"
            icon={<TriangleAlert size={20} />}
            title="History could not be loaded"
            description="Check your connection and try again."
            action={
              <Button variant="secondary" onClick={() => logsResult.refetch()}>
                Try again
              </Button>
            }
          />
        )}

        {!logsResult.isLoading && !logsResult.isError && logs.length === 0 && (
          <StatusView
            icon={<History size={20} />}
            title="No history yet"
            description="This goal has not been evaluated for a completed period yet."
          />
        )}

        {!logsResult.isLoading && !logsResult.isError && logs.length > 0 && (
          <ul className="divide-y divide-border">
            {logs.map((log) => {
              const meta = STATUS_META[log.status];
              const Icon = meta?.Icon ?? Minus;
              return (
                <li key={log.id} className="flex items-center gap-3 py-3">
                  <span
                    className={`inline-flex size-7 flex-none items-center justify-center rounded-md ${
                      meta?.badge ?? "bg-muted text-muted-foreground"
                    }`}
                    aria-hidden="true"
                  >
                    <Icon size={15} aria-hidden={true} />
                  </span>
                  <span className="flex min-w-0 flex-col gap-0.5">
                    <span className="jv-body font-medium text-foreground">
                      {periodLabel(log, frequency)}
                    </span>
                    <span className="jv-caption">{metaLine(log, target)}</span>
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </AppAdaptiveDialog>
  );
}
