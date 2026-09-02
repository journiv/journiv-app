import { useEffect, useId, useMemo, useState } from "react";
import type {
  AdminUserCreate,
  AdminUserListResponse,
  AdminUserUpdate,
  UserRole,
} from "../../../api/generated/types.gen";
import { Alert, AlertDescription } from "../../../components/ui/alert";
import { Button } from "../../../components/ui/button";
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "../../../components/ui/field";
import { Input } from "../../../components/ui/input";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../../components/ui/select";
import { Spinner } from "../../../components/ui/spinner";
import { SettingsSection } from "../SettingsSection";

const ROLE_ITEMS: Array<{ label: string; value: UserRole }> = [
  { label: "User", value: "user" },
  { label: "Administrator", value: "admin" },
];

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function passwordError(password: string, required: boolean) {
  if (!password && !required) return "";
  if (!password) return "Enter a temporary password.";
  if (password.length < 8)
    return "Use at least 8 characters with a letter and a number.";
  if (!/[A-Za-z]/.test(password) || !/\d/.test(password))
    return "Use at least 8 characters with a letter and a number.";
  return "";
}

export type UserFormValues = AdminUserCreate | AdminUserUpdate;

export function UserForm({
  user,
  saving,
  failedMessage,
  onCancel,
  onDirtyChange,
  onSubmit,
}: {
  user?: AdminUserListResponse;
  saving: boolean;
  failedMessage?: string;
  onCancel: () => void;
  onDirtyChange: (dirty: boolean) => void;
  onSubmit: (values: UserFormValues) => Promise<void>;
}) {
  const editing = Boolean(user);
  const nameId = useId();
  const emailId = useId();
  const roleId = useId();
  const passwordId = useId();
  const [name, setName] = useState(user?.name ?? "");
  const [email, setEmail] = useState(user?.email ?? "");
  const [role, setRole] = useState<UserRole>(user?.role ?? "user");
  const [password, setPassword] = useState("");
  const [touched, setTouched] = useState(false);

  const trimmedName = name.trim();
  const trimmedEmail = email.trim().toLowerCase();
  const nameError = trimmedName ? "" : "Enter a display name.";
  const emailError = EMAIL_PATTERN.test(trimmedEmail)
    ? ""
    : "Enter a valid email address.";
  const canEditPassword = !user || user.login_type === "local";
  const currentPasswordError = canEditPassword
    ? passwordError(password, !editing)
    : "";
  const invalid = Boolean(nameError || emailError || currentPasswordError);

  const dirty = useMemo(() => {
    if (!user) return Boolean(name || email || password || role !== "user");
    return (
      trimmedName !== user.name ||
      trimmedEmail !== user.email.toLowerCase() ||
      role !== user.role ||
      Boolean(password)
    );
  }, [email, name, password, role, trimmedEmail, trimmedName, user]);

  useEffect(() => {
    onDirtyChange(dirty);
    return () => onDirtyChange(false);
  }, [dirty, onDirtyChange]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setTouched(true);
    if (invalid || saving) return;
    if (user) {
      // Send only what actually changed so an untouched field never routes
      // through the backend's role / email protections.
      const patch: AdminUserUpdate = {};
      if (trimmedName !== user.name) patch.name = trimmedName;
      if (trimmedEmail !== user.email.toLowerCase()) patch.email = trimmedEmail;
      if (role !== user.role) patch.role = role;
      if (password) patch.password = password;
      await onSubmit(patch);
    } else {
      await onSubmit({
        name: trimmedName,
        email: trimmedEmail,
        password,
        role,
      });
    }
  }

  return (
    <form className="jv-settings__body" noValidate onSubmit={submit}>
      <SettingsSection
        title={editing ? "Edit user" : "Add user"}
        titleId="user-form-title"
        intro={
          editing
            ? "Update this account without leaving Settings."
            : "Create a local account that signs in with email and password."
        }
        footer={
          <>
            <Button
              type="button"
              variant="ghost"
              disabled={saving}
              onClick={onCancel}
            >
              Cancel
            </Button>
            <Button type="submit" variant="default" disabled={saving}>
              {saving && (
                <Spinner data-icon="inline-start" aria-hidden="true" />
              )}
              {saving ? "Saving…" : editing ? "Save changes" : "Create user"}
            </Button>
          </>
        }
      >
        <FieldGroup>
          <Field data-invalid={touched && Boolean(nameError)}>
            <FieldLabel htmlFor={nameId}>Display name</FieldLabel>
            <Input
              id={nameId}
              value={name}
              autoComplete="name"
              autoFocus
              aria-invalid={touched && Boolean(nameError)}
              onChange={(event) => setName(event.target.value)}
            />
            {touched && <FieldError>{nameError}</FieldError>}
          </Field>

          <Field data-invalid={touched && Boolean(emailError)}>
            <FieldLabel htmlFor={emailId}>Email</FieldLabel>
            <Input
              id={emailId}
              type="email"
              value={email}
              autoComplete="email"
              aria-invalid={touched && Boolean(emailError)}
              onChange={(event) => setEmail(event.target.value)}
            />
            {touched && <FieldError>{emailError}</FieldError>}
          </Field>

          <Field>
            <FieldLabel htmlFor={roleId}>Role</FieldLabel>
            <Select
              items={ROLE_ITEMS}
              value={role}
              onValueChange={(value) => setRole(value as UserRole)}
            >
              <SelectTrigger id={roleId} className="jv-users-form__select">
                <SelectValue />
              </SelectTrigger>
              <SelectContent alignItemWithTrigger={false} align="start">
                <SelectGroup>
                  {ROLE_ITEMS.map((item) => (
                    <SelectItem key={item.value} value={item.value}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
            <FieldDescription>
              Administrators can manage every Journiv account.
            </FieldDescription>
          </Field>

          {canEditPassword ? (
            <Field data-invalid={touched && Boolean(currentPasswordError)}>
              <FieldLabel htmlFor={passwordId}>
                {editing ? "New password" : "Temporary password"}
              </FieldLabel>
              <Input
                id={passwordId}
                type="password"
                value={password}
                autoComplete="new-password"
                aria-invalid={touched && Boolean(currentPasswordError)}
                onChange={(event) => setPassword(event.target.value)}
              />
              <FieldDescription>
                {editing
                  ? "Leave blank to keep the existing password."
                  : "The user can change it later from Security."}
              </FieldDescription>
              {touched && <FieldError>{currentPasswordError}</FieldError>}
            </Field>
          ) : (
            <Alert>
              <AlertDescription>
                This account signs in through OIDC. Password reset is not
                available here.
              </AlertDescription>
            </Alert>
          )}
        </FieldGroup>

        {failedMessage && (
          <Alert variant="destructive">
            <AlertDescription>{failedMessage}</AlertDescription>
          </Alert>
        )}
      </SettingsSection>
    </form>
  );
}
