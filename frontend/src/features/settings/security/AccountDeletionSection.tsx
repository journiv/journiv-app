import { useId, useState } from "react";
import { sessionStore } from "../../../api/auth/session";
import { api } from "../../../api/client/api";
import {
  AppAdaptiveDialog,
  useOverlayAutoFocus,
} from "../../../components/journiv/AppAdaptiveDialog";
import { Alert, AlertDescription } from "../../../components/ui/alert";
import { Button } from "../../../components/ui/button";
import { Field, FieldLabel } from "../../../components/ui/field";
import { Input } from "../../../components/ui/input";
import { Spinner } from "../../../components/ui/spinner";
import { SettingsSection } from "../SettingsSection";

const DELETE_CONFIRMATION = "DELETE";

/**
 * Account deletion is deliberately a typed, adaptive dialog rather than a
 * yes/no confirmation. The server has no recovery window, so the client only
 * clears its session after receiving a successful deletion response.
 */
export function AccountDeletionSection() {
  const inputId = useId();
  const shouldAutoFocus = useOverlayAutoFocus();
  const [open, setOpen] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [failure, setFailure] = useState<string>();
  const matches = confirmation === DELETE_CONFIRMATION;

  function close(nextOpen: boolean) {
    if (!nextOpen) {
      setConfirmation("");
      setFailure(undefined);
    }
    setOpen(nextOpen);
  }

  async function deleteAccount() {
    if (!matches || deleting) return;
    setDeleting(true);
    setFailure(undefined);
    try {
      await api.deleteMe();
      sessionStore.clear();
      window.location.assign("/login");
    } catch {
      // A failed response is not proof the account survived; the backend may
      // have completed deletion before an infrastructure failure was reported.
      setFailure(
        "We couldn’t confirm that your account was deleted. Try signing in again before retrying.",
      );
    } finally {
      setDeleting(false);
    }
  }

  return (
    <>
      <SettingsSection
        title="Delete account"
        intro="Permanently remove your account and everything stored in Journiv."
        footer={
          <Button
            type="button"
            variant="destructive"
            onClick={() => setOpen(true)}
          >
            Delete account
          </Button>
        }
      >
        <p className="jv-body text-muted-foreground">
          This deletes your journals, entries, media, tags, moods, prompts, and
          settings. This action cannot be undone.
        </p>
      </SettingsSection>

      <AppAdaptiveDialog
        open={open}
        onOpenChange={close}
        title="Delete your account?"
        description="This permanently deletes your Journiv account and everything stored in it. This action cannot be undone."
        size="md"
        dismissible={!deleting}
        footer={
          <>
            <Button
              type="button"
              variant="ghost"
              disabled={deleting}
              onClick={() => close(false)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="destructive"
              disabled={!matches || deleting}
              onClick={() => void deleteAccount()}
            >
              {deleting && (
                <Spinner data-icon="inline-start" aria-hidden="true" />
              )}
              {deleting ? "Deleting…" : "Delete account"}
            </Button>
          </>
        }
      >
        <Field>
          <FieldLabel htmlFor={inputId}>
            Type <strong>{DELETE_CONFIRMATION}</strong> to confirm
          </FieldLabel>
          <Input
            id={inputId}
            value={confirmation}
            autoComplete="off"
            autoFocus={shouldAutoFocus}
            onChange={(event) => setConfirmation(event.target.value)}
          />
        </Field>
        {failure && (
          <Alert variant="destructive" role="alert">
            <AlertDescription>{failure}</AlertDescription>
          </Alert>
        )}
      </AppAdaptiveDialog>
    </>
  );
}
