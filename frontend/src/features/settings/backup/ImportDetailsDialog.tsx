import { type ReactNode, useState } from "react";
import type {
  ImportJobStatusResponse,
  ImportSourceType,
} from "../../../api/generated/types.gen";
import { AppAdaptiveDialog } from "../../../components/journiv/AppAdaptiveDialog";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "../../../components/ui/card";

type ImportStat = {
  key: string;
  label: string;
  one: string;
  many: string;
};

const CONTENT_STATS: readonly ImportStat[] = [
  {
    key: "journals_created",
    label: "Journals",
    one: "journal",
    many: "journals",
  },
  { key: "entries_created", label: "Entries", one: "entry", many: "entries" },
  { key: "moments_created", label: "Moments", one: "moment", many: "moments" },
  {
    key: "media_files_imported",
    label: "Media files",
    one: "media file",
    many: "media files",
  },
  { key: "tags_created", label: "Tags", one: "tag", many: "tags" },
  { key: "people_created", label: "People", one: "person", many: "people" },
  {
    key: "person_groups_created",
    label: "People groups",
    one: "people group",
    many: "people groups",
  },
  { key: "moods_created", label: "Moods", one: "mood", many: "moods" },
  {
    key: "mood_groups_created",
    label: "Mood groups",
    one: "mood group",
    many: "mood groups",
  },
  {
    key: "activities_created",
    label: "Activities",
    one: "activity",
    many: "activities",
  },
  {
    key: "activity_groups_created",
    label: "Activity groups",
    one: "activity group",
    many: "activity groups",
  },
  { key: "goals_created", label: "Goals", one: "goal", many: "goals" },
  {
    key: "goal_categories_created",
    label: "Goal categories",
    one: "goal category",
    many: "goal categories",
  },
  {
    key: "goal_logs_created",
    label: "Goal logs",
    one: "goal log",
    many: "goal logs",
  },
  {
    key: "entries_skipped",
    label: "Entries skipped",
    one: "entry skipped",
    many: "entries skipped",
  },
  {
    key: "media_files_skipped",
    label: "Media skipped",
    one: "media file skipped",
    many: "media files skipped",
  },
];

const STATUS_LABEL = {
  pending: "Queued",
  running: "Running",
  completed: "Completed",
  partial: "Completed with warnings",
  failed: "Failed",
  cancelled: "Cancelled",
} as const;

const SOURCE_LABEL: Record<ImportSourceType, string> = {
  journiv: "Journiv",
  dayone: "Day One",
  daylio: "Daylio",
  markdown: "Markdown",
  immich: "Immich",
};

function numberValue(value: unknown): number | null {
  if (value == null || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function dateTime(value: string | null | undefined): string {
  if (!value) return "Not finished";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not available";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function countText(count: number, one: string, many: string): string {
  return `${count.toLocaleString()} ${count === 1 ? one : many}`;
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <dt className="jv-caption">{label}</dt>
      <dd className="jv-body m-0 font-medium text-foreground">{children}</dd>
    </div>
  );
}

/**
 * A read-only look at a past import job: the settings it ran with and the
 * per-category totals it recorded. Mirrors {@link ExportDetailsDialog} so the
 * history table offers the same "what did this job do?" affordance for both
 * kinds.
 */
export function ImportDetailsDialog({
  job: incoming,
  onClose,
}: {
  job: ImportJobStatusResponse | null;
  onClose: () => void;
}) {
  // Keep the last job around while the overlay plays its close transition, so
  // it does not vanish abruptly (the compact bottom sheet slides out).
  const [job, setJob] = useState(incoming);
  if (incoming && incoming !== job) setJob(incoming);
  const open = incoming !== null;

  if (!job) return null;

  const resultData = job.result_data ?? {};
  // Only surface totals the import actually recorded a non-zero value for — a
  // finished import reports every category, and a wall of "0 moods / 0 goals"
  // rows buries the counts that matter.
  const contentStats = CONTENT_STATS.flatMap((stat) => {
    const count = numberValue(resultData[stat.key]);
    return count == null || count === 0 ? [] : [{ ...stat, count }];
  });

  const categoryEntries = Object.entries(
    (resultData.warning_categories ?? {}) as Record<string, unknown>,
  ).flatMap(([label, raw]) => {
    const count = numberValue(raw);
    return count == null || count === 0 ? [] : [[label, count] as const];
  });
  const uniqueMessages = [...new Set(job.warnings ?? [])];
  const warningCount =
    uniqueMessages.length ||
    categoryEntries.reduce((sum, [, count]) => sum + count, 0);

  const statusVariant = job.status === "failed" ? "destructive" : "secondary";

  return (
    <AppAdaptiveDialog
      open={open}
      onOpenChange={(next) => !next && onClose()}
      title="Import details"
      description="The settings and recorded totals for this import."
      size="md"
      footer={
        <Button variant="secondary" onClick={onClose}>
          Close
        </Button>
      }
    >
      <div className="flex flex-col gap-4">
        <Card size="sm">
          <CardHeader>
            <CardTitle>Overview</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-2 gap-4" aria-label="Import overview">
              <Fact label="Status">
                <Badge variant={statusVariant}>
                  {STATUS_LABEL[job.status]}
                </Badge>
              </Fact>
              <Fact label="Source">
                {SOURCE_LABEL[job.source_type] ?? job.source_type}
              </Fact>
              <Fact label="Created">{dateTime(job.created_at)}</Fact>
              <Fact label="Finished">{dateTime(job.completed_at)}</Fact>
              <Fact label="Progress">
                {job.total_items > 0
                  ? `${job.processed_items.toLocaleString()} of ${job.total_items.toLocaleString()} items`
                  : `${Math.round(job.progress)}%`}
              </Fact>
              <Fact label="Warnings">
                {countText(warningCount, "warning", "warnings")}
              </Fact>
            </dl>
          </CardContent>
        </Card>

        <Card size="sm">
          <CardHeader>
            <CardTitle>What was imported</CardTitle>
          </CardHeader>
          <CardContent>
            {contentStats.length > 0 ? (
              <dl
                className="grid grid-cols-2 gap-4"
                aria-label="Import contents"
              >
                {contentStats.map((stat) => (
                  <Fact key={stat.key} label={stat.label}>
                    {countText(stat.count, stat.one, stat.many)}
                  </Fact>
                ))}
              </dl>
            ) : (
              <p className="jv-caption">
                Category totals are available after the import finishes.
              </p>
            )}
          </CardContent>
        </Card>

        {warningCount > 0 ? (
          <Card size="sm">
            <CardHeader>
              <CardTitle>Warnings</CardTitle>
            </CardHeader>
            <CardContent>
              {categoryEntries.length > 0 ? (
                <ul className="jv-backup-warnings__categories">
                  {categoryEntries.map(([label, count]) => (
                    <li key={label}>
                      {label} — {count.toLocaleString()}
                    </li>
                  ))}
                </ul>
              ) : null}
              {uniqueMessages.length > 0 ? (
                <ul className="jv-backup-warnings__messages">
                  {uniqueMessages.slice(0, 100).map((message) => (
                    <li key={message}>{message}</li>
                  ))}
                  {uniqueMessages.length > 100 ? (
                    <li className="jv-caption">
                      … and {(uniqueMessages.length - 100).toLocaleString()}{" "}
                      more.
                    </li>
                  ) : null}
                </ul>
              ) : null}
            </CardContent>
          </Card>
        ) : null}
      </div>
    </AppAdaptiveDialog>
  );
}
