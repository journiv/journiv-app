import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../../../api/client/api";
import type {
  ImportMode,
  IntegrationStatusResponse,
} from "../../../api/generated/types.gen";
import { queryKeys } from "../../../api/query/keys";
import { AppConfirmDialog } from "../../../components/journiv/AppConfirmDialog";
import { Button } from "../../../components/ui/button";
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldLabel,
  FieldLegend,
  FieldSet,
  FieldTitle,
} from "../../../components/ui/field";
import { Input } from "../../../components/ui/input";
import { RadioGroup, RadioGroupItem } from "../../../components/ui/radio-group";
import { useSettingsDirty } from "../SettingsModal";
import { SettingsRow, SettingsSection } from "../SettingsSection";
import { immichConnectionState } from "./immichStatus";
import "./integrations.css";
import { Alert, AlertDescription } from "../../../components/ui/alert";

const MODE_OPTIONS: {
  value: ImportMode;
  label: string;
  description: string;
}[] = [
  {
    value: "link_only",
    label: "Link originals",
    description:
      "Journiv stores a reference. Photos and videos stay in Immich and are streamed on demand.",
  },
  {
    value: "copy",
    label: "Copy into Journiv",
    description:
      "Journiv downloads a copy of each attached file into its own storage.",
  },
];

export function ImmichConnectForm({
  baseUrl,
  status,
}: {
  baseUrl: string;
  status: IntegrationStatusResponse;
}) {
  const qc = useQueryClient();
  const state = immichConnectionState(status);
  const [apiKey, setApiKey] = useState("");
  const [mode, setMode] = useState<ImportMode>(state.mode);
  const [disconnectOpen, setDisconnectOpen] = useState(false);

  // Re-seed the mode from the server only when the connection identity changes
  // (connect, disconnect, reconnect) — not on a background status refetch that
  // would otherwise discard a pending edit.
  // biome-ignore lint/correctness/useExhaustiveDependencies: keyed on identity by design.
  useEffect(() => {
    setMode(state.mode);
    setApiKey("");
  }, [state.identity]);

  const trimmedApiKey = apiKey.trim();
  const dirty = state.connected
    ? mode !== state.mode || (state.hasError && trimmedApiKey.length > 0)
    : trimmedApiKey.length > 0;
  useSettingsDirty(dirty);

  const refreshStatus = () =>
    qc.invalidateQueries({
      queryKey: queryKeys.integrationStatus("immich"),
    });

  const save = useMutation({
    mutationFn: async () => {
      if (state.connected && !state.hasError) {
        await api.updateImmich({ import_mode: mode });
      } else {
        await api.connectImmich({ api_key: trimmedApiKey }, mode);
      }
    },
    onSuccess: async () => {
      setApiKey("");
      await refreshStatus();
    },
  });

  const disconnect = useMutation({
    mutationFn: api.disconnectImmich,
    onSuccess: async () => {
      setDisconnectOpen(false);
      await refreshStatus();
    },
  });

  const sync = useMutation({
    mutationFn: api.syncImmich,
    onSuccess: () => refreshStatus(),
  });

  const showKeyField = !state.connected || state.hasError;

  return (
    <div className="jv-settings__body">
      <SettingsSection
        title="Immich"
        intro="Connect Journiv to the Immich server this instance provides. Once connected you can attach photos and videos from your Immich library while writing."
        footer={
          <>
            {state.connected && (
              <Button
                variant="ghost"
                onClick={() => sync.mutate()}
                disabled={sync.isPending || !state.active}
              >
                {sync.isPending ? "Syncing…" : "Sync now"}
              </Button>
            )}
            {state.connected && (
              <Button variant="ghost" onClick={() => setDisconnectOpen(true)}>
                Disconnect
              </Button>
            )}
            <Button
              variant="default"
              disabled={
                save.isPending ||
                (state.connected
                  ? !dirty || (state.hasError && trimmedApiKey.length === 0)
                  : trimmedApiKey.length === 0)
              }
              onClick={() => save.mutate()}
            >
              {save.isPending
                ? state.connected
                  ? "Saving…"
                  : "Connecting…"
                : state.connected
                  ? "Save settings"
                  : "Connect"}
            </Button>
          </>
        }
      >
        <SettingsRow label="Server">
          <p className="jv-settings-row__readonly">{baseUrl}</p>
        </SettingsRow>

        <SettingsRow label="Status">
          <p className="jv-settings-row__readonly">
            {state.connected
              ? state.active
                ? "Connected"
                : "Connected (paused)"
              : "Not connected"}
          </p>
          {state.connected && status.external_user_id && (
            <p className="jv-caption">Immich user {status.external_user_id}</p>
          )}
          {status.last_synced_at && (
            <p className="jv-caption">
              Last synced {new Date(status.last_synced_at).toLocaleString()}
            </p>
          )}
        </SettingsRow>

        {showKeyField && (
          <SettingsRow
            label="API key"
            htmlFor="immich-key"
            description={
              state.hasError
                ? "Re-enter an Immich API key to restore the connection."
                : "Create a key in Immich under Account Settings → API Keys."
            }
          >
            <Input
              id="immich-key"
              type="password"
              autoComplete="off"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
            />
          </SettingsRow>
        )}

        <SettingsRow label="Import mode">
          {/* A generic exclusive choice with descriptions: the registry's own
              `RadioGroup` inside a `FieldSet`, not a hand-skinned native
              radio (DESIGN.md §18, composition table). */}
          <FieldSet>
            <FieldLegend className="sr-only">Import mode</FieldLegend>
            <RadioGroup
              name="immich-import-mode"
              value={mode}
              onValueChange={(next) =>
                setMode(next as (typeof MODE_OPTIONS)[number]["value"])
              }
            >
              {MODE_OPTIONS.map((option) => (
                <FieldLabel
                  key={option.value}
                  htmlFor={`immich-${option.value}`}
                >
                  <Field orientation="horizontal">
                    <RadioGroupItem
                      id={`immich-${option.value}`}
                      value={option.value}
                    />
                    <FieldContent>
                      <FieldTitle>{option.label}</FieldTitle>
                      <FieldDescription>{option.description}</FieldDescription>
                    </FieldContent>
                  </Field>
                </FieldLabel>
              ))}
            </RadioGroup>
          </FieldSet>
          {status.album_error && (
            <p className="jv-caption jv-immich-mode__album-error">
              Immich album for linked media couldn’t be prepared:{" "}
              {status.album_error}
            </p>
          )}
        </SettingsRow>
      </SettingsSection>

      {state.hasError && (
        <p className="jv-settings__alert" role="alert">
          Immich reported a connection problem. Re-enter your API key and
          reconnect.
        </p>
      )}
      {save.isError && (
        <p className="jv-settings__alert" role="alert">
          The Immich connection couldn’t be saved. Your entered value is still
          here.
        </p>
      )}
      {sync.isError && (
        <p className="jv-settings__alert" role="alert">
          Couldn’t start a sync. Try again.
        </p>
      )}
      {sync.isSuccess && !sync.isPending && (
        <Alert role="status">
          <AlertDescription>
            Sync started. New Immich items appear as it runs.
          </AlertDescription>
        </Alert>
      )}

      <AppConfirmDialog
        open={disconnectOpen}
        onOpenChange={setDisconnectOpen}
        title="Disconnect Immich?"
        description="Journiv will stop accessing this provider. Entries that already link Immich media keep working; copied media is unaffected."
        confirmLabel="Disconnect"
        destructive
        pending={disconnect.isPending}
        onConfirm={() => disconnect.mutateAsync()}
      >
        {disconnect.isError && (
          <p className="jv-settings__alert" role="alert">
            Immich couldn’t be disconnected. Try again.
          </p>
        )}
      </AppConfirmDialog>
    </div>
  );
}
