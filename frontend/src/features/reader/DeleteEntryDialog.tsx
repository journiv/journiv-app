import { Trash2, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { AppConfirmDialog } from "../../components/journiv/AppConfirmDialog";
import { Alert, AlertDescription } from "../../components/ui/alert";
import { IconButton } from "../../components/ui/icon-button";

export function DeleteEntryDialog({
  entryTitle,
  deleting,
  failed,
  onConfirm,
  onReset,
}: {
  entryTitle?: string | null;
  deleting: boolean;
  failed: boolean;
  onConfirm: () => void;
  onReset: () => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <IconButton
        label="Delete entry"
        onClick={() => {
          onReset();
          setOpen(true);
        }}
      >
        <Trash2 aria-hidden="true" />
      </IconButton>
      <AppConfirmDialog
        open={open}
        onOpenChange={(next) => {
          // Never strand the user mid-delete with the surface gone.
          if (deleting) return;
          setOpen(next);
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
              The entry couldn’t be deleted. Check your connection and try
              again.
            </AlertDescription>
          </Alert>
        )}
      </AppConfirmDialog>
    </>
  );
}
