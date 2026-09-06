import {
  Progress,
  ProgressLabel,
  ProgressValue,
} from "../../../components/ui/progress";

/**
 * The live state of a running import/export job: a labelled progress bar and,
 * when the backend reports item counts, an "N of M" line beneath it. Replaces
 * the earlier pattern of stuffing a percentage into a `StatusView` title.
 *
 * Rendered only while a job is `pending`/`running`; the settled states are the
 * result panel and the history table.
 */
export function JobProgress({
  label,
  progress,
  processed,
  total,
}: {
  label: string;
  progress: number;
  processed: number;
  total: number;
}) {
  const pct = Math.max(0, Math.min(100, Math.round(progress)));
  return (
    <div className="jv-backup-progress" role="status">
      <Progress value={pct} aria-label={label}>
        <ProgressLabel>{label}</ProgressLabel>
        <ProgressValue />
      </Progress>
      {total > 0 ? (
        <p className="jv-backup-progress__count">
          {processed.toLocaleString()} of {total.toLocaleString()} items
        </p>
      ) : null}
    </div>
  );
}
