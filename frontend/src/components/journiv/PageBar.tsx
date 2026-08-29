import type { ReactNode } from "react";
import { cx } from "../../lib/cx";

/**
 * The single navigation/action bar for every pane.
 *
 * `leading` is rendered only below the desktop breakpoint (CSS, not JS) so the
 * compact layouts always expose navigation — Back on a detail view, the menu on
 * a top-level list — while the desktop layout relies on the persistent panes.
 */
export function PageBar({
  leading,
  title,
  actions,
  className,
}: {
  leading?: ReactNode;
  title?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cx("jv-page-bar", className)}>
      {leading && <div className="jv-page-bar__leading">{leading}</div>}
      <div className="jv-page-bar__title">{title}</div>
      {actions && <div className="jv-page-bar__actions">{actions}</div>}
    </div>
  );
}
