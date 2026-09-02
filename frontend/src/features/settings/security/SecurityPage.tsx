import { useId } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "../../../components/ui/button";
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "../../../components/ui/field";
import { Input } from "../../../components/ui/input";
import { Skeleton } from "../../../components/ui/skeleton";
import { StatusView } from "../../../components/journiv/StatusView";
import {
  currentUserQuery,
  instanceConfigQuery,
} from "../../../api/query/options";
import { useSettingsDirty } from "../SettingsModal";
import { SettingsSection } from "../SettingsSection";
import { usePasswordForm } from "./usePasswordForm";
import { Alert, AlertDescription } from "../../../components/ui/alert";

function SecuritySkeleton() {
  return (
    <div
      className="jv-settings__skeleton"
      role="status"
      aria-label="Loading security settings"
    >
      {[0, 1, 2].map((row) => (
        <div className="jv-settings__skeleton-row" key={row}>
          <Skeleton width="35%" height="0.8rem" />
          <Skeleton height="2.5rem" />
        </div>
      ))}
    </div>
  );
}

function PasswordForm({ email }: { email: string }) {
  const form = usePasswordForm();
  useSettingsDirty(form.dirty);

  const currentId = useId();
  const nextId = useId();
  const confirmId = useId();
  const ruleId = useId();

  const fieldError = (id: string, issue: string | null) =>
    form.touched && issue ? (
      <FieldError id={`${id}-error`} role="alert">
        {issue}
      </FieldError>
    ) : null;

  return (
    <form
      className="jv-settings__body"
      onSubmit={(event) => {
        event.preventDefault();
        form.submit();
      }}
    >
      <SettingsSection
        title="Password"
        intro="Change the password you use to sign in to Journiv."
        footer={
          <Button type="submit" variant="default" disabled={!form.canSubmit}>
            {form.submitting ? "Changing…" : "Change password"}
          </Button>
        }
      >
        {form.succeeded && (
          <Alert role="status">
            <AlertDescription>Your password has been changed.</AlertDescription>
          </Alert>
        )}

        {/* Helps password managers attach the new credential to this account. */}
        <input
          type="text"
          name="username"
          autoComplete="username"
          value={email}
          readOnly
          tabIndex={-1}
          aria-hidden="true"
          className="sr-only"
        />

        <FieldGroup className="jv-settings-form">
          <Field data-invalid={form.touched && Boolean(form.issues.current)}>
            <FieldLabel htmlFor={currentId}>Current password</FieldLabel>
            <Input
              id={currentId}
              type="password"
              name="current-password"
              autoComplete="current-password"
              value={form.fields.current}
              onChange={(event) => form.set("current", event.target.value)}
              aria-invalid={form.touched && Boolean(form.issues.current)}
              aria-describedby={
                form.touched && form.issues.current
                  ? `${currentId}-error`
                  : undefined
              }
            />
            {fieldError(currentId, form.issues.current)}
          </Field>

          <Field data-invalid={form.touched && Boolean(form.issues.next)}>
            <FieldLabel htmlFor={nextId}>New password</FieldLabel>
            <Input
              id={nextId}
              type="password"
              name="new-password"
              autoComplete="new-password"
              value={form.fields.next}
              onChange={(event) => form.set("next", event.target.value)}
              aria-invalid={form.touched && Boolean(form.issues.next)}
              aria-describedby={
                form.touched && form.issues.next ? `${nextId}-error` : ruleId
              }
            />
            <FieldDescription id={ruleId}>
              At least 8 characters, including a letter and a number.
            </FieldDescription>
            {fieldError(nextId, form.issues.next)}
          </Field>

          <Field data-invalid={form.touched && Boolean(form.issues.confirm)}>
            <FieldLabel htmlFor={confirmId}>Confirm new password</FieldLabel>
            <Input
              id={confirmId}
              type="password"
              name="confirm-password"
              autoComplete="new-password"
              value={form.fields.confirm}
              onChange={(event) => form.set("confirm", event.target.value)}
              aria-invalid={form.touched && Boolean(form.issues.confirm)}
              aria-describedby={
                form.touched && form.issues.confirm
                  ? `${confirmId}-error`
                  : undefined
              }
            />
            {fieldError(confirmId, form.issues.confirm)}
          </Field>
        </FieldGroup>

        {form.failed && (
          <p role="alert" className="jv-settings__alert jv-body">
            Your password couldn’t be changed. Check your current password and
            try again.
          </p>
        )}
      </SettingsSection>

      {/* Danger zone — account deletion (`DELETE /users/me`) belongs here in a
          later iteration behind a typed confirmation. Deliberately not built
          now (out of scope); this is only the reserved location. */}
    </form>
  );
}

function OidcNotice({ ssoEnabled }: { ssoEnabled: boolean }) {
  return (
    <div className="jv-settings__body">
      <SettingsSection title="Password">
        <Alert>
          <AlertDescription>
            {ssoEnabled
              ? "You sign in to Journiv through your identity provider. Manage your password with that provider."
              : "This account signs in through an external identity provider, so there is no Journiv password to change."}
          </AlertDescription>
        </Alert>
      </SettingsSection>
    </div>
  );
}

export function SecurityPage() {
  const user = useQuery(currentUserQuery());
  const instance = useQuery(instanceConfigQuery());

  if (user.isLoading) return <SecuritySkeleton />;
  if (user.isError || !user.data)
    return (
      <StatusView
        tone="danger"
        role="alert"
        title="We couldn’t load your security settings"
        description="Something went wrong reaching the server."
        action={
          <Button variant="secondary" onClick={() => user.refetch()}>
            Try again
          </Button>
        }
      />
    );

  if (user.data.is_oidc_user)
    return <OidcNotice ssoEnabled={instance.data?.oidc_enabled ?? true} />;

  return <PasswordForm email={user.data.email} />;
}
