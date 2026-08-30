import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../../api/client/api";
import {
  exportDownloadQuery,
  exportJobQuery,
} from "../../../api/query/options";
import { StatusView } from "../../../components/journiv/StatusView";
import { Button } from "../../../components/ui/button";
import { SettingsRow, SettingsSection } from "../SettingsSection";

export function ExportPage() {
  const [jobId, setJobId] = useState("");
  const [includeMedia, setIncludeMedia] = useState(true);
  const create = useMutation({
    mutationFn: () =>
      api.createExport({ export_type: "full", include_media: includeMedia }),
    onSuccess: (job) => setJobId(job.id),
  });
  const job = useQuery({ ...exportJobQuery(jobId), enabled: Boolean(jobId) });
  const status = job.data?.status;
  const inProgress = status === "pending" || status === "running";
  const ready = status === "completed" || status === "partial";
  const failed =
    create.isError ||
    job.isError ||
    status === "failed" ||
    status === "cancelled";

  // The `download_url` on the status response needs the Authorization header,
  // which a browser navigation cannot send — so a completed export is downloaded
  // through a short-lived signed URL instead.
  const link = useQuery({ ...exportDownloadQuery(jobId), enabled: ready });

  return (
    <div className="jv-settings__body">
      <SettingsSection
        title="Export"
        intro="Create a portable archive in the background. Nothing downloads until you choose the download action."
      >
        <SettingsRow
          label="Include media"
          htmlFor="export-media"
          description="Adds original photos and files to the archive."
        >
          <input
            id="export-media"
            type="checkbox"
            className="jv-settings-checkbox"
            checked={includeMedia}
            onChange={(event) => setIncludeMedia(event.target.checked)}
            disabled={Boolean(jobId)}
          />
        </SettingsRow>
      </SettingsSection>
      {!jobId && (
        <div className="jv-settings__actions">
          <Button
            variant="primary"
            disabled={create.isPending}
            onClick={() => create.mutate()}
          >
            {create.isPending ? "Starting…" : "Create export"}
          </Button>
        </div>
      )}
      {inProgress && (
        <div role="status">
          <StatusView
            title={`Preparing export · ${job.data?.progress}%`}
            description={`${job.data?.processed_items} of ${job.data?.total_items} items processed.`}
          />
        </div>
      )}
      {ready && (
        <div className="jv-settings__success">
          <p>
            Your export is ready.
            {status === "partial"
              ? " Some items were skipped — check the archive."
              : ""}
          </p>
          {link.data?.signed_url ? (
            <Button
              variant="primary"
              nativeButton={false}
              render={<a href={link.data.signed_url} />}
            >
              Download export
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
      )}
      {failed && (
        <p className="jv-settings__alert" role="alert">
          The export couldn’t be completed.{" "}
          <Button variant="ghost" size="sm" onClick={() => setJobId("")}>
            Create a new export
          </Button>
        </p>
      )}
    </div>
  );
}
