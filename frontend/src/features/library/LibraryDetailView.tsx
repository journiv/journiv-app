import type { ReactElement, ReactNode } from "react";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "../../components/ui/breadcrumb";
import "./library.css";

/**
 * The shared Library detail shell (DESIGN.md §24). Opening an item from a
 * `LibraryWorkspace` pushes to this view on the same route area — a wide page,
 * not a third pane. A breadcrumb bar (`Section / Item`) is the title and the
 * back affordance at every width, matching a marketplace-style push flow; the
 * surface's actions sit at the bar's end. One scroll owner below it.
 *
 * The scoped Timeline (`View moments`) is deliberately NOT this view — it stays
 * the three-pane Timeline so a Library item's moments are browsable beside the
 * reader.
 */
export function LibraryDetailView({
  parentLabel,
  parentLink,
  current,
  actions,
  children,
}: {
  parentLabel: string;
  /** A router `<Link>` to the parent list; its children are supplied here. */
  parentLink: ReactElement;
  current: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <main className="jv-library jv-library--detail" aria-label={parentLabel}>
      <div className="jv-library__bar">
        <Breadcrumb className="jv-library__crumb">
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink render={parentLink}>{parentLabel}</BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage className="jv-truncate">{current}</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        {actions && <div className="jv-library__bar-actions">{actions}</div>}
      </div>
      <div className="jv-library__scroll">
        <div className="jv-library__body jv-library__body--detail">
          {children}
        </div>
      </div>
    </main>
  );
}
