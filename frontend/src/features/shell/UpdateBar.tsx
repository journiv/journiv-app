import { X } from "lucide-react";
import { useState } from "react";
import { usePwaUpdate } from "../../app/pwa/usePwaUpdate";
import { AppConfirmDialog } from "../../components/journiv/AppConfirmDialog";
import { Button } from "../../components/ui/button";
import { IconButton } from "../../components/ui/icon-button";
import { useShell } from "./shellContext";

/**
 * Persistent chrome, not a toast (DESIGN.md): "a new version is waiting" is
 * standing state, not a one-shot outcome. Never calls applyUpdate() without
 * explicit confirmation, and never auto-reloads.
 */
export function UpdateBar() {
  const { updateReady, applyUpdate } = usePwaUpdate();
  const { hasUnsavedDraft } = useShell();
  const [dismissed, setDismissed] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  if (!updateReady || dismissed) return null;

  function restart() {
    if (hasUnsavedDraft) {
      setConfirmOpen(true);
      return;
    }
    void applyUpdate();
  }

  return (
    <>
      <div className="jv-update-bar" role="status">
        <span className="text-sm text-foreground">
          A new version of Journiv is ready.
        </span>
        <div className="jv-update-bar__actions">
          <Button variant="outline" size="sm" onClick={restart}>
            Restart to update
          </Button>
          <IconButton
            label="Dismiss"
            variant="ghost"
            size="sm"
            onClick={() => setDismissed(true)}
          >
            <X aria-hidden="true" size={16} />
          </IconButton>
        </div>
      </div>
      <AppConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Restart to update?"
        description="Your unsaved draft is already saved on this device and will be restored after the restart."
        confirmLabel="Restart"
        onConfirm={() => {
          setConfirmOpen(false);
          void applyUpdate();
        }}
      />
    </>
  );
}
