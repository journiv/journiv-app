import { TriangleAlert } from "lucide-react";
import { AppConfirmDialog } from "../../components/journiv/AppConfirmDialog";
import { Alert, AlertDescription } from "../../components/ui/alert";

export function DeleteEntryDialog({
  open,
  onOpenChange,
  entryTitle,
  deleting,
  failed,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  entryTitle?: string | null;
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
      title={entryTitle ? `Delete “${entryTitle}”?` : "Delete entry?"}
      description="The writing in this entry will be permanently removed. Photos, moods, tags, people and other logged details will stay with this moment. If no other details remain, the moment will be removed from the Timeline. This cannot be undone."
      confirmLabel={deleting ? "Deleting…" : "Delete entry"}
      destructive
      pending={deleting}
      onConfirm={onConfirm}
    >
      {failed && (
        <Alert variant="destructive">
          <TriangleAlert aria-hidden="true" />
          <AlertDescription>
            The entry couldn’t be deleted. Check your connection and try again.
          </AlertDescription>
        </Alert>
      )}
    </AppConfirmDialog>
  );
}
