import { TriangleAlert } from "lucide-react";
import { AppConfirmDialog } from "../../components/journiv/AppConfirmDialog";
import { Alert, AlertDescription } from "../../components/ui/alert";

export function DeleteAudioDialog({
  open,
  onOpenChange,
  deleting,
  failed,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  deleting: boolean;
  failed: boolean;
  onConfirm: () => void;
}) {
  return (
    <AppConfirmDialog
      open={open}
      onOpenChange={(next) => {
        // Never strand the user mid-delete with the surface gone.
        if (deleting) return;
        onOpenChange(next);
      }}
      title="Delete this audio clip?"
      description="The recording is removed from this moment and permanently deleted. The writing and everything else logged here stay as they are. This cannot be undone."
      confirmLabel={deleting ? "Deleting…" : "Delete audio clip"}
      cancelLabel="Keep audio clip"
      destructive
      pending={deleting}
      onConfirm={onConfirm}
    >
      {failed && (
        <Alert variant="destructive">
          <TriangleAlert aria-hidden="true" />
          <AlertDescription>
            The audio clip couldn’t be deleted. Check your connection and try
            again.
          </AlertDescription>
        </Alert>
      )}
    </AppConfirmDialog>
  );
}
