import { useId, useState } from "react";
import type { AdminUserListResponse } from "../../../api/generated/types.gen";
import { Alert, AlertDescription } from "../../../components/ui/alert";
import { AppAdaptiveDialog } from "../../../components/journiv/AppAdaptiveDialog";
import { Button } from "../../../components/ui/button";
import { Field, FieldLabel } from "../../../components/ui/field";
import { Input } from "../../../components/ui/input";
import { Spinner } from "../../../components/ui/spinner";

export function DeleteUserDialog({
  user,
  currentUserId,
  deleting,
  failure,
  onOpenChange,
  onConfirm,
}: {
  user: AdminUserListResponse;
  currentUserId?: string;
  deleting: boolean;
  /** Server-supplied reason the delete was refused, shown verbatim. */
  failure?: string;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => Promise<void>;
}) {
  const inputId = useId();
  const [confirmation, setConfirmation] = useState("");
  const matches = confirmation.trim() === user.email;
  const deletingSelf = user.id === currentUserId;

  return (
    // Not an AppConfirmDialog: the account's email must be typed back, which
    // makes this a deliberate workflow rather than a yes/no question.
    <AppAdaptiveDialog
      open
      onOpenChange={onOpenChange}
      title={`Delete ${user.name}?`}
      description={`Journals, entries, media, tags, mood logs, prompts, settings and writing streaks owned by this account are permanently deleted. This cannot be undone.${deletingSelf ? " You will be signed out." : ""}`}
      size="md"
      footer={
        <>
          <Button
            variant="ghost"
            disabled={deleting}
            onClick={() => onOpenChange(false)}
          >
            Cancel
          </Button>
          <Button
            type="button"
            variant="destructive"
            disabled={!matches || deleting}
            onClick={() => void onConfirm()}
          >
            {deleting && (
              <Spinner data-icon="inline-start" aria-hidden="true" />
            )}
            {deleting ? "Deleting…" : "Delete user"}
          </Button>
        </>
      }
    >
      <Field>
        <FieldLabel htmlFor={inputId}>
          Type <strong>{user.email}</strong> to confirm
        </FieldLabel>
        <Input
          id={inputId}
          value={confirmation}
          autoComplete="off"
          onChange={(event) => setConfirmation(event.target.value)}
        />
      </Field>

      {failure && (
        <Alert variant="destructive">
          <AlertDescription>{failure}</AlertDescription>
        </Alert>
      )}
    </AppAdaptiveDialog>
  );
}
