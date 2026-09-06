import { type ReactNode, useState } from "react";
import type { ExportJobStatusResponse } from "../../../api/generated/types.gen";
import { AppAdaptiveDialog } from "../../../components/journiv/AppAdaptiveDialog";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "../../../components/ui/card";
import { formatBytes } from "../../../lib/formatBytes";

type ExportStat = {
  key: string;
  label: string;
  one: string;
  many: string;
};

const CONTENT_STATS: readonly ExportStat[] = [
  { key: "journal_count", label: "Journals", one: "journal", many: "journals" },
  { key: "entry_count", label: "Entries", one: "entry", many: "entries" },
  {
    key: "media_count",
    label: "Media files",
    one: "media file",
    many: "media files",
  },
  {
    key: "missing_media_count",
    label: "Missing media",
    one: "media file missing",
    many: "media files missing",
  },
  { key: "people_count", label: "People", one: "person", many: "people" },
  {
    key: "person_group_count",
    label: "People groups",
    one: "people group",
    many: "people groups",
  },
  { key: "mood_count", label: "Moods", one: "mood", many: "moods" },
  {
    key: "mood_group_count",
    label: "Mood groups",
    one: "mood group",
    many: "mood groups",
  },
  {
    key: "activity_count",
    label: "Activities",
    one: "activity",
    many: "activities",
  },
  {
    key: "activity_group_count",
    label: "Activity groups",
    one: "activity group",
    many: "activity groups",
  },
  { key: "goal_count", label: "Goals", one: "goal", many: "goals" },
  {
    key: "goal_category_count",
    label: "Goal categories",
    one: "goal category",
    many: "goal categories",
  },
  {
    key: "goal_log_count",
    label: "Goal logs",
    one: "goal log",
    many: "goal logs",
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

export function ExportDetailsDialog({
  job: incoming,
  onClose,
}: {
  job: ExportJobStatusResponse | null;
  onClose: () => void;
}) {
  // Keep the last job around while the overlay plays its close transition, so
  // it does not vanish abruptly (the compact bottom sheet slides out).
  const [job, setJob] = useState(incoming);
  if (incoming && incoming !== job) setJob(incoming);
  const open = incoming !== null;

  if (!job) return null;

  const resultData = job.result_data ?? {};
  // Only surface totals the export actually recorded a non-zero value for — a
  // finished export reports every category, and a wall of "0 moods / 0 goals"
  // rows buries the counts that matter.
  const contentStats = CONTENT_STATS.flatMap((stat) => {
    const count = numberValue(resultData[stat.key]);
    return count == null || count === 0 ? [] : [{ ...stat, count }];
  });
  const resultSize = numberValue(resultData.file_size);
  const fileSize = job.file_size ?? resultSize;
  const warningCount = new Set(job.warnings ?? []).size;
  const statusVariant = job.status === "failed" ? "destructive" : "secondary";

  return (
    <AppAdaptiveDialog
      open={open}
      onOpenChange={(next) => !next && onClose()}
      title="Export details"
      description="The contents and settings recorded for this export."
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
            <dl className="grid grid-cols-2 gap-4" aria-label="Export overview">
              <Fact label="Status">
                <Badge variant={statusVariant}>
                  {STATUS_LABEL[job.status]}
                </Badge>
              </Fact>
              <Fact label="Scope">
                {job.export_type === "journal"
                  ? "Selected journals"
                  : "Everything"}
              </Fact>
              <Fact label="Created">{dateTime(job.created_at)}</Fact>
              <Fact label="Finished">{dateTime(job.completed_at)}</Fact>
              <Fact label="Media">
                {job.include_media ? "Included" : "Not included"}
              </Fact>
              <Fact label="Archive size">
                {fileSize == null ? "Not available" : formatBytes(fileSize)}
              </Fact>
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
            <CardTitle>Contents</CardTitle>
          </CardHeader>
          <CardContent>
            {contentStats.length > 0 ? (
              <dl
                className="grid grid-cols-2 gap-4"
                aria-label="Export contents"
              >
                {contentStats.map((stat) => (
                  <Fact key={stat.key} label={stat.label}>
                    {countText(stat.count, stat.one, stat.many)}
                  </Fact>
                ))}
              </dl>
            ) : (
              <p className="jv-caption">
                Content totals are available after the export finishes.
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </AppAdaptiveDialog>
  );
}
