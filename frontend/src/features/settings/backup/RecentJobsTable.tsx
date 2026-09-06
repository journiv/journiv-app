import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import {
  CircleStopIcon,
  DownloadIcon,
  InfoIcon,
  Trash2Icon,
} from "lucide-react";
import { useState } from "react";
import { api } from "../../../api/client/api";
import type {
  ExportJobStatusResponse,
  ImportJobStatusResponse,
  JobStatus,
} from "../../../api/generated/types.gen";
import { queryKeys } from "../../../api/query/keys";
import { exportJobsQuery, importJobsQuery } from "../../../api/query/options";
import { AppConfirmDialog } from "../../../components/journiv/AppConfirmDialog";
import { StatusView } from "../../../components/journiv/StatusView";
import { Button } from "../../../components/ui/button";
import { IconButton } from "../../../components/ui/icon-button";
import { Skeleton } from "../../../components/ui/skeleton";
import { Spinner } from "../../../components/ui/spinner";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../../components/ui/table";
import { formatBytes } from "../../../lib/formatBytes";
import { SettingsSection } from "../SettingsSection";
import { ExportDetailsDialog } from "./ExportDetailsDialog";
import { ImportDetailsDialog } from "./ImportDetailsDialog";

type AnyJob = ExportJobStatusResponse | ImportJobStatusResponse;

const STATUS_LABEL: Record<JobStatus, string> = {
  pending: "Queued",
  running: "Running",
  completed: "Completed",
  partial: "Partial",
  failed: "Failed",
  cancelled: "Cancelled",
};

const STATUS_TONE: Record<JobStatus, string> = {
  pending: "jv-backup-status--busy",
  running: "jv-backup-status--busy",
  completed: "jv-backup-status--ok",
  partial: "jv-backup-status--warn",
  failed: "jv-backup-status--bad",
  cancelled: "jv-backup-status--bad",
};

function dateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function isActive(status: JobStatus) {
  return status === "pending" || status === "running";
}

function importResult(job: ImportJobStatusResponse) {
  const created = Number(job.result_data?.entries_created);
  if (Number.isFinite(created) && created > 0) {
    return `${created.toLocaleString()} ${created === 1 ? "entry" : "entries"}`;
  }
  if (job.total_items > 0) {
    return `${job.processed_items.toLocaleString()} of ${job.total_items.toLocaleString()}`;
  }
  return "—";
}

/**
 * The "Recent exports" / "Recent imports" history — keyset-paginated jobs in
 * the settings content pane's own Table (the wide-pane
 * precedent set by Admin Users). A completed export re-downloads through a
 * fresh signed URL; a settled job of either kind can be removed after a typed
 * confirmation. A running job shows no destructive action (the API 409s it).
 */
export function RecentJobsTable({ kind }: { kind: "export" | "import" }) {
  const queryClient = useQueryClient();
  const listKey =
    kind === "export" ? queryKeys.exportJobs : queryKeys.importJobs;
  // Both queries mount, but only the one for this table's `kind` fetches. This
  // keeps the two result types separate rather than collapsing them into an
  // incompatible union.
  const exportJobs = useInfiniteQuery({
    ...exportJobsQuery(),
    enabled: kind === "export",
  });
  const importJobs = useInfiniteQuery({
    ...importJobsQuery(),
    enabled: kind === "import",
  });
  const jobs = kind === "export" ? exportJobs : importJobs;
  const [pendingDelete, setPendingDelete] = useState<AnyJob | null>(null);
  const [pendingCancel, setPendingCancel] = useState<AnyJob | null>(null);
  const [detailsId, setDetailsId] = useState<string | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const remove = useMutation({
    mutationFn: (id: string) =>
      kind === "export" ? api.deleteExport(id) : api.deleteImport(id),
    onSuccess: async () => {
      setPendingDelete(null);
      await queryClient.invalidateQueries({ queryKey: listKey });
    },
  });

  const cancel = useMutation<AnyJob, Error, string>({
    mutationFn: (id: string) =>
      kind === "export" ? api.cancelExport(id) : api.cancelImport(id),
    onSuccess: async () => {
      setPendingCancel(null);
      await queryClient.invalidateQueries({ queryKey: listKey });
    },
  });

  const download = useMutation({
    mutationFn: (id: string) => api.signExportUrl(id),
    onMutate: (id: string) => setDownloadingId(id),
    onSettled: () => setDownloadingId(null),
    onSuccess: (result) => {
      // A completed export's `download_url` needs the Authorization header a
      // browser navigation can't send, so the signed URL is what actually
      // pulls the file (ExportPage.tsx).
      window.location.assign(result.signed_url);
    },
  });

  const title = kind === "export" ? "Recent exports" : "Recent imports";
  const intro =
    kind === "export"
      ? "Your export jobs, newest first. View what each archive contains, re-download it, or remove it."
      : "Your import jobs, newest first. View what each run brought in, or remove a record.";

  if (jobs.isLoading) {
    return (
      <SettingsSection title={title} intro={intro}>
        <Skeleton className="jv-settings__skeleton" />
      </SettingsSection>
    );
  }

  if (jobs.isError) {
    return (
      <SettingsSection title={title} intro={intro}>
        <StatusView
          title="History couldn’t be loaded"
          description="Check your connection and try again."
          tone="danger"
          role="alert"
          action={
            <Button variant="secondary" onClick={() => void jobs.refetch()}>
              Try again
            </Button>
          }
        />
      </SettingsSection>
    );
  }

  const rows: AnyJob[] =
    kind === "export"
      ? (exportJobs.data?.pages ?? []).flatMap((page) => page.items)
      : (importJobs.data?.pages ?? []).flatMap((page) => page.items);
  const detailsJob = detailsId
    ? (rows.find((job) => job.id === detailsId) ?? null)
    : null;
  const detailsExport =
    kind === "export"
      ? ((detailsJob as ExportJobStatusResponse | null) ?? null)
      : null;
  const detailsImport =
    kind === "import"
      ? ((detailsJob as ImportJobStatusResponse | null) ?? null)
      : null;

  return (
    <SettingsSection title={title} intro={intro}>
      {rows.length === 0 ? (
        <StatusView
          title={kind === "export" ? "No exports yet" : "No imports yet"}
          description={
            kind === "export"
              ? "Exports you create appear here."
              : "Imports you run appear here."
          }
        />
      ) : (
        <Table className="jv-backup-table">
          <TableHeader>
            <TableRow>
              <TableHead>Created</TableHead>
              <TableHead>{kind === "export" ? "Scope" : "Source"}</TableHead>
              <TableHead>{kind === "export" ? "Size" : "Result"}</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((job) => {
              const status = job.status as JobStatus;
              const active = isActive(status);
              const isExport = kind === "export";
              const exportJob = job as ExportJobStatusResponse;
              const canDownload =
                isExport && (status === "completed" || status === "partial");
              return (
                <TableRow key={job.id}>
                  <TableCell>{dateTime(job.created_at)}</TableCell>
                  <TableCell>
                    {isExport
                      ? exportJob.export_type === "journal"
                        ? "Selected journals"
                        : "Everything"
                      : sourceLabel(
                          (job as ImportJobStatusResponse).source_type,
                        )}
                  </TableCell>
                  <TableCell>
                    {isExport
                      ? exportJob.file_size
                        ? formatBytes(exportJob.file_size)
                        : "—"
                      : importResult(job as ImportJobStatusResponse)}
                  </TableCell>
                  <TableCell>
                    <span className={`jv-backup-status ${STATUS_TONE[status]}`}>
                      {active ? (
                        <Spinner aria-hidden="true" className="size-3.5" />
                      ) : null}
                      {STATUS_LABEL[status] ?? status}
                      {active && job.progress > 0
                        ? ` · ${Math.round(job.progress)}%`
                        : ""}
                    </span>
                  </TableCell>
                  <TableCell className="jv-backup-table__actions">
                    <IconButton
                      label={
                        isExport ? "View export details" : "View import details"
                      }
                      size="sm"
                      onClick={() => setDetailsId(job.id)}
                    >
                      <InfoIcon aria-hidden="true" />
                    </IconButton>
                    {canDownload ? (
                      <IconButton
                        label="Download archive"
                        size="sm"
                        disabled={downloadingId === job.id}
                        onClick={() => download.mutate(job.id)}
                      >
                        <DownloadIcon aria-hidden="true" className="size-4" />
                      </IconButton>
                    ) : null}
                    {active ? (
                      <IconButton
                        label={isExport ? "Cancel export" : "Cancel import"}
                        size="sm"
                        onClick={() => setPendingCancel(job)}
                      >
                        <CircleStopIcon aria-hidden="true" className="size-4" />
                      </IconButton>
                    ) : null}
                    {!active ? (
                      <IconButton
                        label={
                          isExport ? "Delete export" : "Delete import record"
                        }
                        size="sm"
                        onClick={() => setPendingDelete(job)}
                      >
                        <Trash2Icon aria-hidden="true" className="size-4" />
                      </IconButton>
                    ) : null}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}

      {jobs.hasNextPage ? (
        <Button
          className="jv-backup-loadmore"
          variant="secondary"
          disabled={jobs.isFetchingNextPage}
          onClick={() => void jobs.fetchNextPage()}
        >
          {jobs.isFetchingNextPage ? "Loading…" : "Load older jobs"}
        </Button>
      ) : null}

      {download.isError ? (
        <p className="jv-settings__alert" role="alert">
          The download link couldn’t be prepared. Try again.
        </p>
      ) : null}

      <ExportDetailsDialog
        job={detailsExport}
        onClose={() => setDetailsId(null)}
      />

      <ImportDetailsDialog
        job={detailsImport}
        onClose={() => setDetailsId(null)}
      />

      <AppConfirmDialog
        open={pendingCancel !== null}
        onOpenChange={(open) => {
          if (!open && !cancel.isPending) {
            setPendingCancel(null);
            cancel.reset();
          }
        }}
        title={
          kind === "export" ? "Cancel this export?" : "Cancel this import?"
        }
        description={
          kind === "export"
            ? "The job stops and no archive is produced."
            : "The job stops at its next checkpoint. Anything already written by an import is kept."
        }
        confirmLabel="Cancel job"
        pending={cancel.isPending}
        onConfirm={() => {
          if (pendingCancel) cancel.mutate(pendingCancel.id);
        }}
      >
        {cancel.isError ? (
          <p className="jv-settings__alert" role="alert">
            It couldn’t be cancelled. Try again.
          </p>
        ) : undefined}
      </AppConfirmDialog>

      <AppConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open && !remove.isPending) {
            setPendingDelete(null);
            remove.reset();
          }
        }}
        title={
          kind === "export"
            ? "Delete this export?"
            : "Delete this import record?"
        }
        description={
          kind === "export"
            ? "The archive file and this job record are removed. Your journal data is untouched."
            : "The job record is removed. The entries this import created are kept."
        }
        confirmLabel="Delete"
        destructive
        pending={remove.isPending}
        onConfirm={() => {
          if (pendingDelete) remove.mutate(pendingDelete.id);
        }}
      >
        {remove.isError ? (
          <p className="jv-settings__alert" role="alert">
            It couldn’t be deleted. Try again.
          </p>
        ) : undefined}
      </AppConfirmDialog>
    </SettingsSection>
  );
}

function sourceLabel(source: string) {
  if (source === "dayone") return "Day One";
  if (source === "journiv") return "Journiv";
  if (source === "daylio") return "Daylio";
  return source;
}
