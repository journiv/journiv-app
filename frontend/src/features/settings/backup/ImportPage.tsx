import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api } from "../../../api/client/api";
import { queryKeys } from "../../../api/query/keys";
import {
  importJobQuery,
  importJobsQuery,
  instanceConfigQuery,
} from "../../../api/query/options";
import { AppConfirmDialog } from "../../../components/journiv/AppConfirmDialog";
import { Button } from "../../../components/ui/button";
import { Dropzone } from "../../../components/ui/dropzone";
import { NativeSelect } from "../../../components/ui/native-select";
import { Spinner } from "../../../components/ui/spinner";
import { formatBytes } from "../../../lib/formatBytes";
import { SettingsRow, SettingsSection } from "../SettingsSection";
import { IMPORT_SOURCES, type ImportSourceOption } from "./importSources";
import { ImportResultSummary } from "./ImportResultSummary";
import { JobProgress } from "./JobProgress";
import { RecentJobsTable } from "./RecentJobsTable";
import "./backup.css";

const ACCEPT = ".zip,.daylio,application/zip";

export function ImportPage() {
  const queryClient = useQueryClient();
  const [source, setSource] = useState<ImportSourceOption["value"]>("journiv");
  const [file, setFile] = useState<File | null>(null);
  const [jobId, setJobId] = useState("");
  const [confirmingCancel, setConfirmingCancel] = useState(false);

  const config = useQuery(instanceConfigQuery());
  const history = useInfiniteQuery(importJobsQuery());

  const historyJobs = (history.data?.pages ?? []).flatMap((page) => page.items);
  const runningFromHistory = historyJobs.find(
    (job) => job.status === "pending" || job.status === "running",
  );
  const trackedId = jobId || runningFromHistory?.id || "";
  const tracked = useQuery({
    ...importJobQuery(trackedId),
    enabled: Boolean(trackedId),
  });

  const status = tracked.data?.status;
  const inProgress = status === "pending" || status === "running";
  const done = status === "completed" || status === "partial";
  const failed = status === "failed";
  const cancelled = status === "cancelled";
  // A failed or cancelled job is done with — its id lingers only so the notice
  // below has something to show. Treat it as "nothing tracked" so the form
  // reopens for another attempt without a separate reset click.
  const settled = failed || cancelled;
  const anotherRunning = Boolean(
    runningFromHistory && runningFromHistory.id !== jobId,
  );
  const busy = inProgress || anotherRunning;

  const maxBytes =
    (config.data?.import_export_max_file_size_mb ?? 0) * 1024 * 1024;
  const sourceHint = useMemo(
    () => IMPORT_SOURCES.find((item) => item.value === source)?.hint ?? "",
    [source],
  );

  const tooLarge = Boolean(file && maxBytes > 0 && file.size > maxBytes);
  const badExtension = Boolean(
    file &&
      !/\.(zip|daylio)$/i.test(file.name) &&
      file.type !== "application/zip",
  );
  const fileError = tooLarge
    ? `That file is ${formatBytes(file?.size)}. The maximum is ${config.data?.import_export_max_file_size_mb} MB.`
    : badExtension
      ? "Choose a .zip archive (or a .daylio file for Daylio)."
      : null;

  const upload = useMutation({
    mutationFn: () => api.uploadImport(file as File, source),
    onSuccess: async (job) => {
      setJobId(job.id);
      setFile(null);
      await queryClient.invalidateQueries({ queryKey: queryKeys.importJobs });
    },
  });

  const cancel = useMutation({
    mutationFn: () => api.cancelImport(trackedId),
    onSuccess: async (job) => {
      setConfirmingCancel(false);
      // Adopt a job that was only being tracked from history so the cancelled
      // notice below has something to show.
      setJobId(job.id);
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: queryKeys.importJob(job.id),
        }),
        queryClient.invalidateQueries({ queryKey: queryKeys.importJobs }),
      ]);
    },
  });

  const canStart =
    Boolean(file) &&
    !fileError &&
    !busy &&
    !upload.isPending &&
    (!jobId || settled);

  return (
    <div className="jv-settings__body">
      <SettingsSection
        title="Import"
        intro="Bring in an export from Journiv or another journalling app. The import runs as a background job and reports item progress."
        footer={
          jobId && !failed && !cancelled ? undefined : (
            <Button
              variant="default"
              disabled={!canStart}
              onClick={() => {
                setJobId("");
                upload.mutate();
              }}
            >
              {upload.isPending ? (
                <Spinner aria-hidden="true" data-icon="inline-start" />
              ) : null}
              {upload.isPending ? "Uploading…" : "Start import"}
            </Button>
          )
        }
      >
        <SettingsRow
          label="Source"
          htmlFor="import-source"
          description={sourceHint}
        >
          <NativeSelect
            id="import-source"
            value={source}
            disabled={(Boolean(jobId) && !settled) || busy}
            onChange={(event) =>
              setSource(event.target.value as ImportSourceOption["value"])
            }
          >
            {IMPORT_SOURCES.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </NativeSelect>
        </SettingsRow>

        <SettingsRow
          label="Archive"
          description={
            config.data?.import_export_max_file_size_mb
              ? `A .zip archive, up to ${config.data.import_export_max_file_size_mb} MB.`
              : "A .zip archive for the selected source."
          }
        >
          <Dropzone
            label="Import archive"
            value={file}
            onValueChange={setFile}
            accept={ACCEPT}
            disabled={(Boolean(jobId) && !settled) || busy}
            aria-invalid={Boolean(fileError)}
            aria-describedby={fileError ? "import-file-error" : undefined}
            hint="ZIP archive"
          />
          {fileError ? (
            <p
              id="import-file-error"
              className="jv-settings__alert"
              role="alert"
            >
              {fileError}
            </p>
          ) : null}
        </SettingsRow>
      </SettingsSection>

      {trackedId && inProgress && tracked.data ? (
        <div className="jv-backup-jobpanel">
          <JobProgress
            label="Importing"
            progress={tracked.data.progress}
            processed={tracked.data.processed_items}
            total={tracked.data.total_items}
          />
          <Button
            variant="secondary"
            disabled={cancel.isPending}
            onClick={() => setConfirmingCancel(true)}
          >
            {cancel.isPending ? "Cancelling…" : "Cancel"}
          </Button>
        </div>
      ) : null}

      <AppConfirmDialog
        open={confirmingCancel}
        onOpenChange={(open) => {
          if (!open && !cancel.isPending) {
            setConfirmingCancel(false);
            cancel.reset();
          }
        }}
        title="Cancel this import?"
        description="The job stops at its next checkpoint. Anything already imported is kept."
        confirmLabel="Cancel job"
        pending={cancel.isPending}
        onConfirm={() => cancel.mutate()}
      >
        {cancel.isError ? (
          <p className="jv-settings__alert" role="alert">
            It couldn’t be cancelled. Try again.
          </p>
        ) : undefined}
      </AppConfirmDialog>

      {jobId && done && tracked.data ? (
        <ImportResultSummary
          status={tracked.data.status}
          resultData={tracked.data.result_data ?? undefined}
          warnings={tracked.data.warnings ?? undefined}
          processed={tracked.data.processed_items}
          total={tracked.data.total_items}
        />
      ) : null}

      {jobId && failed ? (
        <p className="jv-settings__alert" role="alert">
          The import couldn’t be completed
          {tracked.data
            ? ` after ${tracked.data.processed_items} of ${tracked.data.total_items} items`
            : ""}
          . Your existing journal data was not removed.{" "}
          <Button variant="ghost" size="sm" onClick={() => setJobId("")}>
            Start another import
          </Button>
        </p>
      ) : null}

      {jobId && cancelled ? (
        <p className="jv-caption" role="status">
          {tracked.data && tracked.data.processed_items > 0
            ? `Import cancelled. ${tracked.data.processed_items.toLocaleString()} ${
                tracked.data.processed_items === 1 ? "item was" : "items were"
              } already imported before it stopped and ${
                tracked.data.processed_items === 1 ? "was" : "were"
              } kept — review them in your journals.`
            : "Import cancelled before anything was imported."}{" "}
          <Button variant="ghost" size="sm" onClick={() => setJobId("")}>
            Start another import
          </Button>
        </p>
      ) : null}

      {!jobId && anotherRunning ? (
        <p className="jv-caption" role="status">
          An import is already running. It will appear below when it finishes.
        </p>
      ) : null}

      <RecentJobsTable kind="import" />
    </div>
  );
}
