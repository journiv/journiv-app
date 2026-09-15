import { useQueryClient } from "@tanstack/react-query";
import { formatDistance } from "date-fns";
import { useEffect, useState } from "react";

const RELATIVE_TIME_REFRESH_MS = 60_000;

/**
 * Persistent chrome for offline-restricted mode (docs/features/pwa.md), not
 * a toast: being offline is standing state for as long as it lasts. States
 * plainly that this is cached content from the last sync, with a timestamp,
 * so nothing here is mistaken for live data.
 */
export function OfflineBar() {
  const queryClient = useQueryClient();
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const interval = window.setInterval(
      () => setNow(Date.now()),
      RELATIVE_TIME_REFRESH_MS,
    );
    return () => window.clearInterval(interval);
  }, []);
  const mostRecentSync = Math.max(
    0,
    ...queryClient
      .getQueryCache()
      .getAll()
      .map((query) => query.state.dataUpdatedAt),
  );

  return (
    <div className="jv-offline-bar" role="status">
      <span className="text-sm text-foreground">
        You&rsquo;re offline. Showing cached content
        {mostRecentSync > 0
          ? ` from ${formatDistance(mostRecentSync, now, { addSuffix: true })}`
          : ""}
        . New entries and edits are unavailable until you&rsquo;re back online.
      </span>
    </div>
  );
}
