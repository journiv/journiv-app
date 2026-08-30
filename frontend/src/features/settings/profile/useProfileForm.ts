import { useMutation, useQueries, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api } from "../../../api/client/api";
import { queryKeys } from "../../../api/query/keys";
import {
  currentUserQuery,
  userSettingsQuery,
} from "../../../api/query/options";

export type ProfileFormState = ReturnType<typeof useProfileForm>;

/**
 * Profile edit state. Initialises from the shared current-user and user-settings
 * queries (no private copy of either — DESIGN.md §23), tracks dirtiness, and on
 * save writes only what changed: `name` via `PUT /users/me`, `time_zone` via
 * `PUT /users/me/settings`. Entered values survive a failed save; a successful
 * save re-seeds from the server and updates the sidebar via cache invalidation.
 */
export function useProfileForm() {
  const qc = useQueryClient();
  const [{ data: user, isLoading: userLoading, isError: userError }, settings] =
    useQueries({
      queries: [currentUserQuery(), userSettingsQuery()],
    });

  const serverName = user?.name ?? "";
  // The settings row is the editable source of truth; `user.time_zone` mirrors
  // it and is the fallback until settings load.
  const serverTimezone = settings.data?.time_zone ?? user?.time_zone ?? "UTC";

  const [name, setName] = useState(serverName);
  const [timezone, setTimezone] = useState(serverTimezone);
  const [touched, setTouched] = useState(false);
  const [saved, setSaved] = useState(false);

  // Re-seed when the server values change under us — after a save, or a refetch.
  const lastServer = useRef({ name: serverName, timezone: serverTimezone });
  useEffect(() => {
    if (
      lastServer.current.name === serverName &&
      lastServer.current.timezone === serverTimezone
    )
      return;
    lastServer.current = { name: serverName, timezone: serverTimezone };
    setName(serverName);
    setTimezone(serverTimezone);
  }, [serverName, serverTimezone]);

  const trimmedName = name.trim();
  const nameChanged = trimmedName !== serverName.trim();
  const timezoneChanged = timezone !== serverTimezone;
  const dirty = nameChanged || timezoneChanged;
  const invalid = trimmedName.length === 0;

  const mutation = useMutation({
    mutationFn: async () => {
      if (nameChanged) await api.updateMe({ name: trimmedName });
      if (timezoneChanged)
        await api.updateUserSettings({ time_zone: timezone });
    },
    onSuccess: async () => {
      setSaved(true);
    },
    onSettled: async () => {
      await Promise.all([
        qc.invalidateQueries({ queryKey: queryKeys.me }),
        qc.invalidateQueries({ queryKey: queryKeys.userSettings }),
      ]);
    },
  });

  function save() {
    setTouched(true);
    setSaved(false);
    if (invalid || !dirty || mutation.isPending) return;
    mutation.mutate();
  }

  const status: "loading" | "error" | "ready" =
    userLoading || settings.isLoading
      ? "loading"
      : userError
        ? "error"
        : "ready";

  return {
    status,
    user,
    email: user?.email ?? "",
    name,
    setName: (value: string) => {
      setSaved(false);
      setName(value);
    },
    timezone,
    setTimezone: (value: string) => {
      setSaved(false);
      setTimezone(value);
    },
    dirty,
    invalid,
    touched,
    saving: mutation.isPending,
    // Invalid does not disable Save — clicking it surfaces the field error
    // instead, the same pattern as the journal form (DESIGN.md §16).
    canSave: dirty && !mutation.isPending,
    saved: saved && !dirty,
    failed: mutation.isError,
    save,
    retry: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.me });
      void qc.invalidateQueries({ queryKey: queryKeys.userSettings });
    },
  };
}
