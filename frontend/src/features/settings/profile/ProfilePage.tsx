import { useId } from "react";
import { UserRound } from "lucide-react";
import { Button } from "../../../components/ui/button";
import { FieldError } from "../../../components/ui/field";
import { Input } from "../../../components/ui/input";
import { Skeleton } from "../../../components/ui/skeleton";
import { StatusView } from "../../../components/journiv/StatusView";
import { useSettingsDirty } from "../SettingsModal";
import { SettingsRow, SettingsSection } from "../SettingsSection";
import { TimezoneField } from "./TimezoneField";
import { useProfileForm } from "./useProfileForm";
import {
  Avatar,
  AvatarFallback,
  AvatarImage,
} from "../../../components/ui/avatar";
import { Alert, AlertDescription } from "../../../components/ui/alert";

function initials(name: string, email: string): string {
  const source = name.trim() || email.trim();
  if (!source) return "";
  const parts = source.split(/\s+/).filter(Boolean);
  const letters =
    parts.length > 1
      ? `${parts[0][0]}${parts[parts.length - 1][0]}`
      : source.slice(0, 2);
  return letters.toUpperCase();
}

function ProfileSkeleton() {
  return (
    <div
      className="jv-settings__skeleton"
      role="status"
      aria-label="Loading profile"
    >
      {[0, 1, 2].map((row) => (
        <div className="jv-settings__skeleton-row" key={row}>
          <Skeleton width="30%" height="0.8rem" />
          <Skeleton height="2.5rem" />
        </div>
      ))}
    </div>
  );
}

export function ProfilePage() {
  const form = useProfileForm();
  useSettingsDirty(form.dirty);

  const nameId = useId();
  const timezoneId = useId();
  const nameErrorId = `${nameId}-error`;
  const showNameError = form.touched && form.invalid;

  if (form.status === "loading") return <ProfileSkeleton />;
  if (form.status === "error")
    return (
      <StatusView
        tone="danger"
        role="alert"
        title="We couldn’t load your profile"
        description="Something went wrong reaching the server."
        action={
          <Button variant="secondary" onClick={form.retry}>
            Try again
          </Button>
        }
      />
    );

  return (
    <form
      className="jv-settings__body"
      onSubmit={(event) => {
        event.preventDefault();
        form.save();
      }}
    >
      <SettingsSection
        title="Personal information"
        intro="How you appear in Journiv, and the timezone new moments are stamped with."
        footer={
          <Button type="submit" variant="default" disabled={!form.canSave}>
            {form.saving ? "Saving…" : "Save changes"}
          </Button>
        }
      >
        <div className="jv-settings__identity">
          <Avatar className="jv-settings__avatar" aria-hidden="true">
            {form.user?.profile_picture_url && (
              <AvatarImage src={form.user.profile_picture_url} alt="" />
            )}
            <AvatarFallback>
              {initials(form.name, form.email) || (
                <UserRound aria-hidden="true" />
              )}
            </AvatarFallback>
          </Avatar>
          <div className="jv-settings__identity-text">
            <p className="jv-settings__identity-name jv-label jv-truncate">
              {form.name || "—"}
            </p>
            <p className="jv-settings__identity-email jv-caption jv-truncate">
              {form.email}
            </p>
          </div>
        </div>

        <SettingsRow
          label="Display name"
          htmlFor={nameId}
          description="Shown in the sidebar and against this account."
        >
          <Input
            id={nameId}
            value={form.name}
            autoComplete="name"
            onChange={(event) => form.setName(event.target.value)}
            aria-invalid={showNameError}
            aria-describedby={showNameError ? nameErrorId : undefined}
          />
          {showNameError && (
            <FieldError id={nameErrorId} role="alert">
              Enter a display name.
            </FieldError>
          )}
        </SettingsRow>

        <SettingsRow
          label="Email"
          description="Email can’t be changed from here."
        >
          <p className="jv-settings-row__readonly jv-body">{form.email}</p>
        </SettingsRow>

        <SettingsRow
          label="Timezone"
          htmlFor={timezoneId}
          description="Used for new moments unless your device reports a different one."
        >
          <TimezoneField
            id={timezoneId}
            value={form.timezone}
            onChange={form.setTimezone}
            disabled={form.saving}
          />
        </SettingsRow>
      </SettingsSection>

      {form.failed && (
        <p role="alert" className="jv-settings__alert jv-body">
          Your changes couldn’t be saved. Check your connection and try again.
        </p>
      )}
      {form.saved && (
        <Alert role="status">
          <AlertDescription>Profile saved.</AlertDescription>
        </Alert>
      )}
    </form>
  );
}
