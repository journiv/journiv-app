import { useSearch } from "@tanstack/react-router";
import { lazy, Suspense, type ReactNode } from "react";
import { StatusView } from "../../components/journiv/StatusView";
import { Loader2 } from "lucide-react";
import { TimelinePage } from "../timeline/TimelinePage";

const CalendarPane = lazy(async () => ({
  default: (await import("../calendar/CalendarPane")).CalendarPane,
}));
const MediaPane = lazy(async () => ({
  default: (await import("../media/MediaPane")).MediaPane,
}));

function ListPaneLoading({ label }: { label: string }) {
  return (
    <section className="jv-shell__list" aria-label={label}>
      <div className="jv-pane-status" role="status">
        <StatusView
          icon={<Loader2 className="jv-spin" size={20} />}
          title={label}
        />
      </div>
    </section>
  );
}

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
        <Suspense fallback={<ListPaneLoading label="Loading calendar…" />}>
          <CalendarPane />
        </Suspense>
      ) : view === "media" ? (
        <Suspense fallback={<ListPaneLoading label="Loading media…" />}>
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
