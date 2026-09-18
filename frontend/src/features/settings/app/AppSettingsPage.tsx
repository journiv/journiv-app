import { useEffect, useState } from "react";
import {
  isOfflineReadingEnabled,
  purgeOfflineCache,
  setOfflineReadingEnabled,
} from "../../../app/offline/offlineCache";
import {
  hasDeferredInstallPrompt,
  isIosSafari,
  isStandalone,
  promptInstall,
  subscribeToInstallPrompt,
} from "../../../app/pwa/installPrompt";
import { sessionStore } from "../../../api/auth/session";
import { AppConfirmDialog } from "../../../components/journiv/AppConfirmDialog";
import { Button } from "../../../components/ui/button";
import { Switch } from "../../../components/ui/switch";
import { SettingsRow, SettingsSection } from "../SettingsSection";

function useInstallAvailability() {
  const [standalone, setStandalone] = useState(isStandalone);
  const [canPrompt, setCanPrompt] = useState(hasDeferredInstallPrompt);

  useEffect(
    () =>
      subscribeToInstallPrompt(() => {
        setCanPrompt(hasDeferredInstallPrompt());
        setStandalone(isStandalone());
      }),
    [],
  );

  return { standalone, canPrompt };
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(1)} ${units[unitIndex]}`;
}

function useStorageEstimate() {
  const [usageBytes, setUsageBytes] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (typeof navigator === "undefined" || !navigator.storage?.estimate) {
      return;
    }
    void navigator.storage.estimate().then((estimate) => {
      if (!cancelled) setUsageBytes(estimate.usage ?? 0);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // Ask the browser to protect this device's storage from eviction under
  // pressure -- but only once there is something worth protecting.
  // Unprompted on a blank app is a bad first impression, and browsers weigh
  // the prompt's context.
  useEffect(() => {
    if (
      usageBytes &&
      usageBytes > 0 &&
      typeof navigator !== "undefined" &&
      navigator.storage?.persist
    ) {
      void navigator.storage.persist();
    }
  }, [usageBytes]);

  return usageBytes;
}

/**
 * Settings → Install & offline (docs/features/pwa.md). Install is a one-time
 * setup action, never an unsolicited banner or interstitial (DESIGN.md
 * product character) -- this page is the only place it appears.
 */
export function AppSettingsPage() {
  const { standalone, canPrompt } = useInstallAvailability();
  const [prompting, setPrompting] = useState(false);
  const [readingEnabled, setReadingEnabled] = useState(isOfflineReadingEnabled);
  const [updatingReading, setUpdatingReading] = useState(false);
  const [clearOpen, setClearOpen] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [storageError, setStorageError] = useState<string | null>(null);
  const usageBytes = useStorageEstimate();
  const ios = isIosSafari();
  const secureContext =
    typeof window !== "undefined" ? window.isSecureContext : true;

  async function install() {
    setPrompting(true);
    try {
      await promptInstall();
    } finally {
      setPrompting(false);
    }
  }

  async function toggleReading(checked: boolean) {
    const previous = readingEnabled;
    setReadingEnabled(checked);
    setUpdatingReading(true);
    setStorageError(null);
    try {
      await setOfflineReadingEnabled(checked);
    } catch {
      setReadingEnabled(previous);
      setStorageError(
        `Offline reading couldn’t be ${checked ? "enabled" : "disabled"}. Check that this browser allows site storage, then try again.`,
      );
    } finally {
      setUpdatingReading(false);
    }
  }

  async function clearOfflineData() {
    setClearing(true);
    setStorageError(null);
    try {
      await purgeOfflineCache(sessionStore.readHint()?.userId);
      setClearOpen(false);
    } catch {
      setStorageError(
        "Offline data couldn’t be cleared. Check that this browser allows site storage, then try again.",
      );
    } finally {
      setClearing(false);
    }
  }

  const installDescription = standalone
    ? "Journiv is installed on this device."
    : ios
      ? secureContext
        ? "On iPhone or iPad: tap Share, then Add to Home Screen."
        : "On iPhone or iPad: tap Share, then Add to Home Screen. This connection isn't secure because it doesn't use HTTPS, so the installed app won't work offline — only the online-only shortcut."
      : canPrompt
        ? "Add Journiv to this device's home screen or app list for a faster launch and no browser chrome."
        : secureContext
          ? "This browser doesn't currently offer installing Journiv."
          : "Installing needs a secure (HTTPS) connection to this Journiv instance.";

  return (
    <div className="jv-settings__body">
      <SettingsSection
        title="Install & offline"
        intro="Add Journiv to this device for a faster launch, its own icon, and no browser chrome."
      >
        <SettingsRow label="Install" description={installDescription}>
          {!standalone && !ios && canPrompt ? (
            <Button
              variant="default"
              disabled={prompting}
              onClick={() => void install()}
            >
              Install Journiv
            </Button>
          ) : null}
        </SettingsRow>
      </SettingsSection>

      <SettingsSection
        title="Offline reading"
        intro="Recently viewed entries are kept on this device so you can read them without a connection. Turning this off erases them."
      >
        <SettingsRow label="Offline reading" htmlFor="offline-reading" inline>
          <Switch
            id="offline-reading"
            checked={readingEnabled}
            disabled={updatingReading}
            onCheckedChange={(checked) => void toggleReading(checked === true)}
          />
        </SettingsRow>
        <SettingsRow
          label="Storage used"
          description={
            usageBytes === null
              ? "This browser doesn't report storage usage."
              : formatBytes(usageBytes)
          }
        >
          <Button
            variant="destructive"
            disabled={!readingEnabled}
            onClick={() => setClearOpen(true)}
          >
            Clear offline data
          </Button>
        </SettingsRow>
      </SettingsSection>

      {storageError && (
        <p className="jv-settings__alert" role="alert">
          {storageError}
        </p>
      )}

      <AppConfirmDialog
        open={clearOpen}
        onOpenChange={setClearOpen}
        title="Clear offline data?"
        description="Removes every entry cached on this device for offline reading. This does not affect your journal on the server."
        confirmLabel="Clear"
        destructive
        pending={clearing}
        onConfirm={clearOfflineData}
      >
        {storageError && (
          <p className="jv-settings__alert" role="alert">
            {storageError}
          </p>
        )}
      </AppConfirmDialog>
    </div>
  );
}
