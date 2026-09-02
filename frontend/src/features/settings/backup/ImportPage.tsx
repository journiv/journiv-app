import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type { ImportSourceType } from "../../../api/generated/types.gen";
import { api } from "../../../api/client/api";
import { importJobQuery } from "../../../api/query/options";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { StatusView } from "../../../components/journiv/StatusView";
import { SettingsRow, SettingsSection } from "../SettingsSection";
import { NativeSelect } from "../../../components/ui/native-select";
import { Alert, AlertDescription } from "../../../components/ui/alert";

const SOURCES: Array<{ value: ImportSourceType; label: string }> = [
  { value: "journiv", label: "Journiv" },
  { value: "dayone", label: "Day One" },
  { value: "daylio", label: "Daylio" },
];

export function ImportPage() {
  const [file, setFile] = useState<File>();
  const [source, setSource] = useState<ImportSourceType>("journiv");
  const [jobId, setJobId] = useState("");
  const upload = useMutation({
    mutationFn: () => api.uploadImport(file as File, source),
    onSuccess: (job) => setJobId(job.id),
  });
  const job = useQuery({ ...importJobQuery(jobId), enabled: Boolean(jobId) });
  const status = job.data?.status;
  const inProgress = status === "pending" || status === "running";
  const done = status === "completed" || status === "partial";
  const failed =
    upload.isError ||
    job.isError ||
    status === "failed" ||
    status === "cancelled";
  const canStart = !jobId || failed;
  const warningCount = job.data?.warnings?.length ?? 0;
  return (
    <div className="jv-settings__body">
      <SettingsSection
        title="Import"
        intro="Choose an export archive and its source. Import runs as a background job and reports item progress."
        footer={
          canStart ? (
            <Button
              variant="default"
              disabled={!file || upload.isPending}
              onClick={() => upload.mutate()}
            >
              {upload.isPending ? "Uploading…" : "Start import"}
            </Button>
          ) : undefined
        }
      >
        <SettingsRow label="Source" htmlFor="import-source">
          <NativeSelect
            id="import-source"
            value={source}
            onChange={(event) =>
              setSource(event.target.value as ImportSourceType)
            }
            disabled={!canStart}
          >
            {SOURCES.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </NativeSelect>
        </SettingsRow>
        <SettingsRow
          label="Archive"
          htmlFor="import-file"
          description="The API accepts a ZIP archive for the selected source."
        >
          <Input
            id="import-file"
            type="file"
            accept=".zip,application/zip"
            onChange={(event) => setFile(event.target.files?.[0])}
            disabled={!canStart}
          />
        </SettingsRow>
      </SettingsSection>
      {inProgress && job.data && (
        <div role="status">
          <StatusView
            title={`Importing · ${job.data.progress}%`}
            description={`${job.data.processed_items} of ${job.data.total_items} items processed.`}
          />
        </div>
      )}
      {done && job.data && (
        <>
          <Alert role="status">
            <AlertDescription>
              {status === "partial"
                ? "Import finished with some items skipped. "
                : "Import complete. "}
              {job.data.processed_items} of {job.data.total_items} items
              processed.
            </AlertDescription>
          </Alert>
          {warningCount > 0 && (
            <p className="jv-settings__alert" role="status">
              {warningCount} imported{" "}
              {warningCount === 1 ? "item needs" : "items need"} attention.
            </p>
          )}
        </>
      )}
      {failed && (
        <p className="jv-settings__alert" role="alert">
          The import couldn’t be completed
          {job.data
            ? ` after ${job.data.processed_items} of ${job.data.total_items} items`
            : ""}
          . Your existing journal data was not removed.
        </p>
      )}
    </div>
  );
}
