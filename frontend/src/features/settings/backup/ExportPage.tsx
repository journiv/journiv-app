import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useMemo, useState } from "react";
import type { ExportType } from "../../../api/generated/types.gen";
import { api } from "../../../api/client/api";
import { queryKeys } from "../../../api/query/keys";
import {
  exportDownloadQuery,
  exportJobQuery,
  exportJobsQuery,
  journalsQuery,
} from "../../../api/query/options";
import { Button } from "../../../components/ui/button";
import { Checkbox } from "../../../components/ui/checkbox";
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldLabel,
  FieldSet,
  FieldTitle,
} from "../../../components/ui/field";
import { RadioGroup, RadioGroupItem } from "../../../components/ui/radio-group";
import { Spinner } from "../../../components/ui/spinner";
import { Switch } from "../../../components/ui/switch";
import { AppConfirmDialog } from "../../../components/journiv/AppConfirmDialog";
import { groupJournals } from "../../../lib/journalOrder";
import { formatBytes } from "../../../lib/formatBytes";
import { SettingsRow, SettingsSection } from "../SettingsSection";
import { JobProgress } from "./JobProgress";
import { RecentJobsTable } from "./RecentJobsTable";
import "./backup.css";

function num(value: unknown): number | null {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

export function ExportPage() {
  const queryClient = useQueryClient();
  const [scope, setScope] = useState<ExportType>("full");
  const [journalIds, setJournalIds] = useState<Set<string>>(new Set());
  const [includeMedia, setIncludeMedia] = useState(true);
  const [jobId, setJobId] = useState("");
  const [confirmingCancel, setConfirmingCancel] = useState(false);

  const journals = useQuery(journalsQuery());
  const history = useInfiniteQuery(exportJobsQuery());

  // A job may already be running from an earlier visit or another tab; the
  // history list is the source of truth for "is an export in flight".
  const historyJobs = (history.data?.pages ?? []).flatMap((page) => page.items);
  const runningFromHistory = historyJobs.find(
    (job) => job.status === "pending" || job.status === "running",
  );
  const trackedId = jobId || runningFromHistory?.id || "";
  const tracked = useQuery({
    ...exportJobQuery(trackedId),
    enabled: Boolean(trackedId),
  });

  const status = tracked.data?.status;
  const inProgress = status === "pending" || status === "running";
  const ready = status === "completed" || status === "partial";
  const failed = status === "failed";
  const cancelled = status === "cancelled";
  // Disable "Create export" while any export job is still in flight — the one
  // this session started, or one already running from an earlier visit.
  const anotherRunning = Boolean(
    runningFromHistory && runningFromHistory.id !== jobId,
  );
  const busy = inProgress || anotherRunning;

  const groups = useMemo(
    () => groupJournals(journals.data ?? []),
    [journals.data],
  );

  const valid = scope === "full" || journalIds.size > 0;

  const create = useMutation({
    mutationFn: () =>
      api.createExport({
        export_type: scope,
        include_media: includeMedia,
        ...(scope === "journal" ? { journal_ids: [...journalIds] } : {}),
      }),
    onSuccess: async (job) => {
      setJobId(job.id);
      await queryClient.invalidateQueries({ queryKey: queryKeys.exportJobs });
    },
  });

  const cancel = useMutation({
    mutationFn: () => api.cancelExport(trackedId),
    onSuccess: async (job) => {
      setConfirmingCancel(false);
      // Adopt a job that was only being tracked from history so the cancelled
      // notice below has something to show.
      setJobId(job.id);
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: queryKeys.exportJob(job.id),
        }),
        queryClient.invalidateQueries({ queryKey: queryKeys.exportJobs }),
      ]);
    },
  });

  // Only sign a download for a job the user started this session; older
  // completed exports are re-downloaded from the history table.
  const link = useQuery({
    ...exportDownloadQuery(jobId),
    enabled: Boolean(jobId) && ready,
  });

  const stats = tracked.data?.result_data ?? undefined;
  const entryCount = num(stats?.entry_count);
  const mediaCount = num(stats?.media_count);
  const journalCount = num(stats?.journal_count);
  const missingMedia = num(stats?.missing_media_count);

  function toggleJournal(id: string, on: boolean) {
    setJournalIds((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  return (
    <div className="jv-settings__body">
      <SettingsSection
        title="Export"
        intro="Create a portable archive in the background. Nothing downloads until you choose the download action."
        footer={
          jobId && !failed && !cancelled && !ready ? undefined : (
            <Button
              variant="default"
              // Hold the action until history loads: only then is it known
              // whether an export is already running from another visit or tab.
              disabled={create.isPending || busy || !valid || history.isLoading}
              onClick={() => {
                setJobId("");
                create.mutate();
              }}
            >
              {create.isPending ? (
                <Spinner aria-hidden="true" data-icon="inline-start" />
              ) : null}
              {create.isPending ? "Starting…" : "Create export"}
            </Button>
          )
        }
      >
        <SettingsRow label="Scope">
          <FieldSet>
            <RadioGroup
              name="export-scope"
              value={scope}
              onValueChange={(next) => setScope(next as ExportType)}
              disabled={Boolean(jobId) || busy}
            >
              <FieldLabel htmlFor="export-scope-full">
                <Field orientation="horizontal">
                  <RadioGroupItem id="export-scope-full" value="full" />
                  <FieldContent>
                    <FieldTitle>Everything</FieldTitle>
                    <FieldDescription>
                      Every journal, entry, and its metadata.
                    </FieldDescription>
                  </FieldContent>
                </Field>
              </FieldLabel>
              <FieldLabel htmlFor="export-scope-journal">
                <Field orientation="horizontal">
                  <RadioGroupItem id="export-scope-journal" value="journal" />
                  <FieldContent>
                    <FieldTitle>Choose journals</FieldTitle>
                    <FieldDescription>
                      Export only the journals you select.
                    </FieldDescription>
                  </FieldContent>
                </Field>
              </FieldLabel>
            </RadioGroup>
          </FieldSet>

          {scope === "journal" ? (
            journals.isLoading ? (
              <p className="jv-caption">Loading journals…</p>
            ) : groups.active.length + groups.archived.length === 0 ? (
              <p className="jv-caption">You have no journals to export.</p>
            ) : (
              <FieldSet className="jv-backup-journals">
                {[...groups.active, ...groups.archived].map((journal) => (
                  <FieldLabel
                    key={journal.id}
                    htmlFor={`export-journal-${journal.id}`}
                  >
                    <Field orientation="horizontal">
                      <Checkbox
                        id={`export-journal-${journal.id}`}
                        checked={journalIds.has(journal.id)}
                        disabled={Boolean(jobId) || busy}
                        onCheckedChange={(on) =>
                          toggleJournal(journal.id, on === true)
                        }
                      />
                      <FieldContent>
                        <FieldTitle>
                          {journal.title}
                          {journal.is_archived ? (
                            <span className="jv-backup-journals__archived">
                              {" "}
                              · Archived
                            </span>
                          ) : null}
                        </FieldTitle>
                      </FieldContent>
                    </Field>
                  </FieldLabel>
                ))}
              </FieldSet>
            )
          ) : null}
        </SettingsRow>

        <SettingsRow
          label="Include media"
          htmlFor="export-media"
          description="Adds original photos and files to the archive."
        >
          <Switch
            id="export-media"
            checked={includeMedia}
            onCheckedChange={(checked) => setIncludeMedia(checked === true)}
            disabled={Boolean(jobId) || busy}
          />
        </SettingsRow>
      </SettingsSection>

      {create.isError ? (
        <p className="jv-settings__alert" role="alert">
          The export couldn’t be started. Use Create export to try again.
        </p>
      ) : null}

      {trackedId && inProgress && tracked.data ? (
        <div className="jv-backup-jobpanel">
          <JobProgress
            label="Preparing export"
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
        title="Cancel this export?"
        description="The job stops and no archive is produced."
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

      {jobId && ready ? (
        <div className="jv-backup-result" role="status">
          <p className="jv-backup-result__headline">
            {status === "partial"
              ? "Your export is ready — some items were skipped."
              : "Your export is ready."}
          </p>
          <ul className="jv-backup-result__stats">
            {journalCount != null ? (
              <li>
                {journalCount.toLocaleString()}{" "}
                {journalCount === 1 ? "journal" : "journals"}
              </li>
            ) : null}
            {entryCount != null ? (
              <li>
                {entryCount.toLocaleString()}{" "}
                {entryCount === 1 ? "entry" : "entries"}
              </li>
            ) : null}
            {includeMedia && mediaCount != null ? (
              <li>
                {mediaCount.toLocaleString()}{" "}
                {mediaCount === 1 ? "media file" : "media files"}
              </li>
            ) : null}
            {tracked.data?.file_size ? (
              <li>{formatBytes(tracked.data.file_size)}</li>
            ) : null}
            {missingMedia != null && missingMedia > 0 ? (
              <li className="jv-backup-result__warn">
                {missingMedia.toLocaleString()} media missing
              </li>
            ) : null}
          </ul>
          {link.data?.signed_url ? (
            <Button
              variant="default"
              nativeButton={false}
              render={<a href={link.data.signed_url} />}
            >
              Download archive
            </Button>
          ) : link.isError ? (
            <p className="jv-settings__alert" role="alert">
              The download link couldn’t be prepared.{" "}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => void link.refetch()}
              >
                Try again
              </Button>
            </p>
          ) : (
            <p className="jv-caption">Preparing download…</p>
          )}
        </div>
      ) : null}

      {jobId && failed ? (
        <p className="jv-settings__alert" role="alert">
          The export couldn’t be completed.{" "}
          <Button variant="ghost" size="sm" onClick={() => setJobId("")}>
            Create a new export
          </Button>
        </p>
      ) : null}

      {jobId && cancelled ? (
        <p className="jv-caption" role="status">
          Export cancelled.{" "}
          <Button variant="ghost" size="sm" onClick={() => setJobId("")}>
            Create a new export
          </Button>
        </p>
      ) : null}

      {!jobId && runningFromHistory && tracked.data && inProgress ? (
        <p className="jv-caption" role="status">
          An export is already running. It will appear below when it finishes.
        </p>
      ) : null}

      <RecentJobsTable kind="export" />
    </div>
  );
}
