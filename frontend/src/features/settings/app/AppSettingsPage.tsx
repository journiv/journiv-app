import { useEffect, useState } from "react";
import {
  hasDeferredInstallPrompt,
  isIosSafari,
  isStandalone,
  promptInstall,
  subscribeToInstallPrompt,
} from "../../../app/pwa/installPrompt";
import { Button } from "../../../components/ui/button";
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

/**
 * Settings → Install & offline (docs/features/pwa.md). Install is a one-time
 * setup action, never an unsolicited banner or interstitial (DESIGN.md
 * product character) -- this page is the only place it appears.
 */
export function AppSettingsPage() {
  const { standalone, canPrompt } = useInstallAvailability();
  const [prompting, setPrompting] = useState(false);
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

  const installDescription = standalone
    ? "Journiv is installed on this device."
    : ios
      ? "On iPhone or iPad: tap Share, then Add to Home Screen."
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
    </div>
  );
}
