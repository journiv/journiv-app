import { useEffect, useId, useState } from "react";
import type { JournalResponse } from "../../api/generated/types.gen";
import { Button } from "../../components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../../components/ui/dialog";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";

/**
 * Deleting a journal cascade-deletes every entry written in it — the writing is
 * gone for good; only the parent moments survive as quick logs. The destructive
 * button stays disabled until the exact title is typed, and archiving is offered
 * first as the reversible alternative.
 */
export function DeleteJournalDialog({
  open,
  onOpenChange,
  journal,
  onConfirm,
  onArchiveInstead,
  deleting,
  failed,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  journal: JournalResponse;
  onConfirm: () => Promise<unknown>;
  onArchiveInstead: () => void;
  deleting: boolean;
  failed: boolean;
}) {
  const inputId = useId();
  const [confirmText, setConfirmText] = useState("");
  useEffect(() => {
    if (open) setConfirmText("");
  }, [open]);

  const matches = confirmText.trim() === journal.title;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{`Delete “${journal.title}”?`}</DialogTitle>
          <DialogDescription>
            Every entry written in this journal is permanently removed. Photos,
            moods and other logged details are kept as standalone moments. This
            cannot be undone.
          </DialogDescription>
        </DialogHeader>

        <div className="jv-jdelete">
          <Button
            variant="secondary"
            onClick={onArchiveInstead}
            disabled={deleting}
          >
            Archive instead
          </Button>

          <Label htmlFor={inputId}>
            Type <strong>{journal.title}</strong> to confirm
          </Label>
          <Input
            id={inputId}
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
            autoComplete="off"
          />

          {failed && (
            <p className="text-sm text-destructive" role="alert">
              The journal couldn’t be deleted. Try again.
            </p>
          )}
        </div>

        <DialogFooter>
          <DialogClose render={<Button variant="ghost" />}>Cancel</DialogClose>
          <Button
            type="button"
            variant="danger"
            disabled={!matches || deleting}
            onClick={() => {
              void onConfirm();
            }}
          >
            {deleting ? "Deleting…" : "Delete journal"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
