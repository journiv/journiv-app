import { PageBar } from "./PageBar";
import { Skeleton } from "../ui/skeleton";

/**
 * Route-level Suspense fallbacks (DESIGN.md "Navigation loading").
 *
 * A fallback owns geometry only — the pane element, its grid placement, its
 * surface and its bar — never a feature's data skeleton. Shapes here are
 * deliberately less detailed than the feature skeleton that replaces them, so
 * the handoff reads as refinement rather than a second, different screen.
 *
 * None of these may reuse a lazy-loaded feature's own root class
 * (`.jv-library`, `.jv-reader`, `.jv-editor`, …): that class ships in the same
 * chunk the fallback exists to stand in for, so at fallback-paint time it is
 * not loaded yet. `.jv-route-workspace` / `.jv-route-detail` in journiv.css
 * mirror just the geometry those classes need, and journiv.css is always
 * loaded (src/styles/index.css). Shell pane classes are the exception —
 * shell.css is never lazy — so `ListPaneFallback` wears `.jv-shell__list`
 * directly to get its grid placement.
 *
 * Every root here also carries `.jv-route-fallback`, which is what excludes
 * these from the pane-enter animation (journiv.css). Without it the pane
 * whose class a fallback borrows would fade in twice: once as the
 * placeholder, once as the real thing replacing it.
 */

const ROW_KEYS = ["a", "b", "c", "d"] as const;

/** Pane-owning: stands in for the pane element itself (`JournalsIndex`, and
 *  the `CalendarPane` / `MediaPane` boundaries, which already render inside
 *  `jv-shell__list` correctly today). */
export function ListPaneFallback({ label }: { label: string }) {
  return (
    <section
      className="jv-shell__list jv-route-fallback"
      role="status"
      aria-label={label}
    >
      <PageBar
        className="jv-page-bar--compact-only"
        title={<Skeleton height="0.9rem" width="6rem" />}
      />
      <div className="jv-route-fallback__rows">
        {ROW_KEYS.map((key) => (
          <Skeleton key={key} height="3.25rem" />
        ))}
      </div>
    </section>
  );
}

/** Pane-content: `Workspace` already rendered `jv-shell__page` around the
 *  detail column (ReaderDetail, EditorDetail) — this fills its interior only
 *  and must not re-declare a pane element. */
export function DetailPaneFallback({ label }: { label: string }) {
  return (
    <div
      className="jv-route-detail jv-route-fallback"
      role="status"
      aria-label={label}
    >
      <PageBar title={<Skeleton height="0.9rem" width="6rem" />} />
    </div>
  );
}

/** Pane-owning, span-two: stands in for a Library-style workspace (Tags,
 *  People, Moods, Activities, Goals, Insights, Prompts) before its chunk has
 *  loaded. Carries the compact-only PageBar too, matching `LibraryWorkspace`,
 *  so the compact/desktop split does not itself introduce a height shift. */
export function WorkspacePaneFallback({ label }: { label: string }) {
  return (
    <section
      className="jv-route-workspace jv-route-fallback"
      role="status"
      aria-label={label}
    >
      <PageBar
        className="jv-page-bar--compact-only"
        title={<Skeleton height="0.9rem" width="6rem" />}
      />
      <div className="jv-route-workspace__header">
        <Skeleton
          className="jv-route-workspace__heading"
          height="1.5rem"
          width="9rem"
        />
      </div>
    </section>
  );
}
