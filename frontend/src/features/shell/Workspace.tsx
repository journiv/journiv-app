import { useSearch } from "@tanstack/react-router";
import { lazy, Suspense, type ReactNode } from "react";
import { ListPaneFallback } from "../../components/journiv/RouteFallback";
import { TimelinePage } from "../timeline/TimelinePage";

const CalendarPane = lazy(async () => ({
  default: (await import("../calendar/CalendarPane")).CalendarPane,
}));
const MediaPane = lazy(async () => ({
  default: (await import("../media/MediaPane")).MediaPane,
}));

/**
 * The middle "list" pane plus the detail pane beside it.
 *
 * The list pane has three modes, chosen by the `view` search param (validated in
 * the router): the chronological Timeline (default), a month Calendar, or a
 * Media grid. All three are the same moments seen differently, and the detail
 * pane on the right is untouched — opening a moment from any mode keeps that
 * mode mounted.
 */
export function Workspace({ children }: { children: ReactNode }) {
  const { view } = useSearch({ strict: false }) as {
    view?: "calendar" | "media";
  };
  return (
    <>
      {view === "calendar" ? (
        <Suspense fallback={<ListPaneFallback label="Loading calendar…" />}>
          <CalendarPane />
        </Suspense>
      ) : view === "media" ? (
        <Suspense fallback={<ListPaneFallback label="Loading media…" />}>
          <MediaPane />
        </Suspense>
      ) : (
        <TimelinePage />
      )}
      <section className="jv-shell__page" aria-label="Moment detail">
        {children}
      </section>
    </>
  );
}
