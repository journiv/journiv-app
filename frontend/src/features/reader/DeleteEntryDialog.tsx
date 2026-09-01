import { Trash2, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { Alert, AlertDescription } from "../../components/ui/alert";
import { Button } from "../../components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "../../components/ui/dialog";
import { IconButton } from "../../components/ui/icon-button";
import { Spinner } from "../../components/ui/spinner";

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
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (deleting) return;
        if (nextOpen) onReset();
        setOpen(nextOpen);
      }}
    >
      <DialogTrigger render={<IconButton label="Delete entry" />}>
        <Trash2 aria-hidden="true" />
      </DialogTrigger>
      <DialogContent showCloseButton={!deleting}>
        <DialogHeader>
          <DialogTitle>
            {entryTitle ? `Delete “${entryTitle}”?` : "Delete entry?"}
          </DialogTitle>
          <DialogDescription>
            The writing in this entry will be permanently removed. Photos,
            moods, tags, people and other logged details will stay with this
            moment. If no other details remain, the moment will be removed from
            the Timeline. This cannot be undone.
          </DialogDescription>
        </DialogHeader>

        {failed && (
          <Alert variant="destructive">
            <TriangleAlert aria-hidden="true" />
            <AlertDescription>
              The entry couldn’t be deleted. Check your connection and try
              again.
            </AlertDescription>
          </Alert>
        )}

        <DialogFooter>
          <DialogClose render={<Button variant="ghost" disabled={deleting} />}>
            Cancel
          </DialogClose>
          <Button variant="danger" disabled={deleting} onClick={onConfirm}>
            {deleting && (
              <Spinner data-icon="inline-start" aria-hidden="true" />
            )}
            {deleting ? "Deleting…" : "Delete entry"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
