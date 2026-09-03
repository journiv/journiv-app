import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../../api/client/api";

/** Mirrors the backend rule (`UserUpdate.validate_new_password`): at least 8
 *  characters, with at least one letter and one digit. The server stays
 *  authoritative — this only spares the user a round trip. */
export function newPasswordIssue(value: string): string | null {
  if (value.length < 8) return "Use at least 8 characters.";
  if (!/[A-Za-z]/.test(value) || !/\d/.test(value))
    return "Include at least one letter and one number.";
  return null;
}

const EMPTY = { current: "", next: "", confirm: "" };

/**
 * Change-password state for accounts that authenticate with a password.
 * Nothing is persisted anywhere: the three fields live only in component state
 * and are cleared on success. The request is `PUT /users/me` with
 * `current_password` + `new_password`.
 */
export function usePasswordForm() {
  const [fields, setFields] = useState(EMPTY);
  const [touched, setTouched] = useState(false);
  const [succeeded, setSucceeded] = useState(false);

  const nextIssue = newPasswordIssue(fields.next);
  const confirmIssue =
    fields.confirm.length === 0
      ? "Confirm your new password."
      : fields.confirm !== fields.next
        ? "This doesn’t match the new password."
        : null;
  const currentIssue =
    fields.current.length === 0 ? "Enter your current password." : null;
  const valid =
    !nextIssue && !confirmIssue && !currentIssue && fields.confirm.length > 0;
  const dirty =
    fields.current.length > 0 ||
    fields.next.length > 0 ||
    fields.confirm.length > 0;

  const mutation = useMutation({
    mutationFn: () =>
      api.updateMe({
        current_password: fields.current,
        new_password: fields.next,
      }),
    onSuccess: () => {
      setFields(EMPTY);
      setTouched(false);
      setSucceeded(true);
    },
  });

  function set(key: keyof typeof fields, value: string) {
    setSucceeded(false);
    setFields((prev) => ({ ...prev, [key]: value }));
  }

  function submit() {
    setTouched(true);
    setSucceeded(false);
    if (!valid || mutation.isPending) return;
    mutation.mutate();
  }

  return {
    fields,
    set,
    touched,
    issues: {
      current: currentIssue,
      next: nextIssue,
      confirm: confirmIssue,
    },
    dirty,
    // Invalid input does not disable the button — submitting surfaces the field
    // errors instead (DESIGN.md), as in the journal form.
    canSubmit: dirty && !mutation.isPending,
    submitting: mutation.isPending,
    failed: mutation.isError,
    succeeded,
    submit,
  };
}
