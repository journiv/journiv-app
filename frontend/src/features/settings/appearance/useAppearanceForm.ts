import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../../../api/client/api";
import { queryKeys } from "../../../api/query/keys";
import { userSettingsQuery } from "../../../api/query/options";

export function useAppearanceForm() {
  const qc = useQueryClient();
  const query = useQuery(userSettingsQuery());
  const server = query.data;
  const [theme, setTheme] = useState(server?.theme ?? "system");
  const [timeFormat, setTimeFormat] = useState(server?.time_format ?? "system");
  const [weekStart, setWeekStart] = useState(server?.start_of_week_day ?? 0);
  useEffect(() => {
    if (!server) return;
    setTheme(server.theme ?? "system");
    setTimeFormat(server.time_format ?? "system");
    setWeekStart(server.start_of_week_day ?? 0);
  }, [server]);
  const dirty = Boolean(
    server &&
      (theme !== (server.theme ?? "system") ||
        timeFormat !== (server.time_format ?? "system") ||
        weekStart !== (server.start_of_week_day ?? 0)),
  );
  const mutation = useMutation({
    mutationFn: () =>
      api.updateUserSettings({
        theme,
        time_format: timeFormat,
        start_of_week_day: weekStart,
      }),
    onSuccess: async () =>
      qc.invalidateQueries({ queryKey: queryKeys.userSettings }),
  });
  return {
    query,
    theme,
    setTheme,
    timeFormat,
    setTimeFormat,
    weekStart,
    setWeekStart,
    dirty,
    mutation,
  };
}
