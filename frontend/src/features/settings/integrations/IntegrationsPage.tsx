import { useMutation, useQueries, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../../../api/client/api";
import { queryKeys } from "../../../api/query/keys";
import {
  instanceConfigQuery,
  integrationStatusQuery,
} from "../../../api/query/options";
import { Button } from "../../../components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "../../../components/ui/dialog";
import { Input } from "../../../components/ui/input";
import { Skeleton } from "../../../components/ui/skeleton";
import { StatusView } from "../../../components/journiv/StatusView";
import { useSettingsDirty } from "../SettingsModal";
import { SettingsRow, SettingsSection } from "../SettingsSection";

export function IntegrationsPage() {
  const qc = useQueryClient();
  const [config, status] = useQueries({
    queries: [instanceConfigQuery(), integrationStatusQuery()],
  });
  const [apiKey, setApiKey] = useState("");
  const [mode, setMode] = useState<"link_only" | "copy">("link_only");
  const [disconnectOpen, setDisconnectOpen] = useState(false);
  useEffect(() => {
    if (status.data?.import_mode) setMode(status.data.import_mode);
  }, [status.data]);
  const connected = status.data?.status === "connected";
  const dirty = connected ? mode !== status.data?.import_mode : Boolean(apiKey);
  useSettingsDirty(dirty);
  const refresh = () =>
    qc.invalidateQueries({ queryKey: queryKeys.integrationStatus("immich") });
  const save = useMutation({
    mutationFn: async () => {
      if (connected) await api.updateImmich({ import_mode: mode });
      else await api.connectImmich({ api_key: apiKey });
    },
    onSuccess: async () => {
      setApiKey("");
      await refresh();
    },
  });
  const disconnect = useMutation({
    mutationFn: api.disconnectImmich,
    onSuccess: async () => {
      setDisconnectOpen(false);
      await refresh();
    },
  });
  if (config.isLoading || status.isLoading)
    return <Skeleton className="jv-settings__skeleton" />;
  if (config.isError)
    return (
      <StatusView
        title="Integrations couldn’t be loaded"
        description="Instance capabilities are unavailable."
        action={<Button onClick={() => config.refetch()}>Try again</Button>}
      />
    );
  if (!config.data?.immich_base_url)
    return (
      <StatusView
        title="No integrations available"
        description="This instance has not enabled an integration provider."
      />
    );
  return (
    <div className="jv-settings__body">
      <SettingsSection
        title="Immich"
        intro="Connect Journiv to the Immich provider configured by this instance."
      >
        <SettingsRow label="Server">
          <p className="jv-settings-row__readonly">
            {config.data.immich_base_url}
          </p>
        </SettingsRow>
        <SettingsRow label="Status">
          <p className="jv-settings-row__readonly">
            {connected ? "Connected" : "Not connected"}
          </p>
          {status.data?.last_synced_at && (
            <p className="jv-caption">
              Last synced{" "}
              {new Date(status.data.last_synced_at).toLocaleString()}
            </p>
          )}
        </SettingsRow>
        {!connected && (
          <SettingsRow label="API key" htmlFor="immich-key">
            <Input
              id="immich-key"
              type="password"
              autoComplete="off"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
            />
          </SettingsRow>
        )}
        {connected && (
          <SettingsRow label="Import mode" htmlFor="immich-mode">
            <select
              id="immich-mode"
              className="jv-field"
              value={mode}
              onChange={(event) =>
                setMode(event.target.value as "link_only" | "copy")
              }
            >
              <option value="link_only">Link originals</option>
              <option value="copy">Copy into Journiv</option>
            </select>
          </SettingsRow>
        )}
      </SettingsSection>
      {status.data?.last_error && (
        <p className="jv-settings__alert" role="alert">
          Immich reported a connection problem. Check the provider and
          reconnect.
        </p>
      )}
      {save.isError && (
        <p className="jv-settings__alert" role="alert">
          The Immich connection couldn’t be saved. Your entered value is still
          here.
        </p>
      )}
      <div className="jv-settings__actions">
        {connected && (
          <Button variant="ghost" onClick={() => setDisconnectOpen(true)}>
            Disconnect
          </Button>
        )}
        <Button
          variant="primary"
          disabled={!dirty || save.isPending}
          onClick={() => save.mutate()}
        >
          {connected ? "Save settings" : "Connect"}
        </Button>
      </div>
      <Dialog open={disconnectOpen} onOpenChange={setDisconnectOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Disconnect Immich?</DialogTitle>
            <DialogDescription>
              Journiv will stop accessing this provider. Existing imported media
              stays in place.
            </DialogDescription>
          </DialogHeader>
          <div className="jv-dialog__actions">
            <DialogClose render={<Button>Cancel</Button>} />
            <Button variant="danger" onClick={() => disconnect.mutate()}>
              Disconnect
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
