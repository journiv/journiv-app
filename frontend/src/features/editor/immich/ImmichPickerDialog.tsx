import { useEffect, useMemo, useRef, useState } from "react";
import type {
  ImportMode,
  IntegrationAssetResponse,
} from "../../../api/generated/types.gen";
import { AppAdaptiveDialog } from "../../../components/journiv/AppAdaptiveDialog";
import { Button } from "../../../components/ui/button";
import { StatusView } from "../../../components/journiv/StatusView";
import { Spinner } from "../../../components/ui/spinner";
import {
  AssetGridPicker,
  AssetGridPickerFooter,
} from "../../media/AssetGridPicker";
import { useImmichAssetSource } from "./immichAssetSource";
import "./immichPicker.css";

export type ImmichConnectionState =
  | "connected"
  | "disconnected"
  | "error"
  | "loading";

type Tab = "device" | "immich";

export function ImmichPickerDialog({
  open,
  onOpenChange,
  connection,
  importMode,
  onPickDevice,
  onPickImmich,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  connection: ImmichConnectionState;
  importMode: ImportMode;
  onPickDevice: () => void;
  onPickImmich: (assets: IntegrationAssetResponse[]) => void;
}) {
  const usable = connection === "connected";
  const loading = connection === "loading";
  const [tab, setTab] = useState<Tab>(usable || loading ? "immich" : "device");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const bodyRef = useRef<HTMLDivElement>(null);
  // Only reach for the library once it can actually be shown.
  const { source, resolve } = useImmichAssetSource(
    open && usable && tab === "immich",
  );

  // Re-seed the tab each time the dialog opens; drop any stale selection.
  useEffect(() => {
    if (open) {
      setTab(usable || loading ? "immich" : "device");
      setSelectedIds([]);
    }
  }, [open, usable, loading]);

  const confirmLabel = useMemo(() => {
    const n = selectedIds.length;
    if (n === 0) return "Add";
    return `Add ${n} ${n === 1 ? "item" : "items"}`;
  }, [selectedIds.length]);

  const chooseDevice = () => {
    onOpenChange(false);
    onPickDevice();
  };

  const confirmImmich = () => {
    const assets = resolve(selectedIds);
    onOpenChange(false);
    setSelectedIds([]);
    if (assets.length) onPickImmich(assets);
  };

  const description =
    tab === "immich"
      ? importMode === "copy"
        ? "Files you add are copied into Journiv."
        : "Files stay in Immich; Journiv links to them."
      : "Choose photos, videos or audio from this device.";

  const tabs = (
    <div
      className="jv-immich-picker__tabs"
      role="tablist"
      aria-label="Media source"
    >
      <button
        type="button"
        role="tab"
        aria-selected={tab === "device"}
        className="jv-immich-picker__tab"
        onClick={() => setTab("device")}
      >
        This device
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={tab === "immich"}
        className="jv-immich-picker__tab"
        onClick={() => setTab("immich")}
      >
        Immich
      </button>
    </div>
  );

  const footer =
    tab === "device" ? (
      <Button variant="default" onClick={chooseDevice}>
        Choose files
      </Button>
    ) : usable ? (
      <AssetGridPickerFooter
        selectedCount={selectedIds.length}
        confirmLabel={confirmLabel}
        onClear={() => setSelectedIds([])}
        onConfirm={confirmImmich}
      />
    ) : undefined;

  return (
    <AppAdaptiveDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Add media"
      description={description}
      headerExtra={tabs}
      footer={footer}
      size="lg"
      bodyRef={bodyRef}
    >
      {tab === "device" ? (
        <p className="jv-body">
          Photos, videos and audio on this device attach directly.
        </p>
      ) : usable ? (
        <AssetGridPicker
          source={source}
          selectedIds={selectedIds}
          onToggle={(id) =>
            setSelectedIds((current) =>
              current.includes(id)
                ? current.filter((existing) => existing !== id)
                : [...current, id],
            )
          }
          onClear={() => setSelectedIds([])}
          onConfirm={confirmImmich}
          confirmLabel={confirmLabel}
          scrollRef={bodyRef}
          hideFooter
        />
      ) : loading ? (
        <StatusView
          role="status"
          icon={<Spinner />}
          title="Loading Immich connection…"
        />
      ) : (
        <StatusView
          title={
            connection === "error"
              ? "Immich needs reconnecting"
              : "Immich isn’t connected"
          }
          description="Connect it in Settings → Integrations, then reopen this picker."
        />
      )}
    </AppAdaptiveDialog>
  );
}
