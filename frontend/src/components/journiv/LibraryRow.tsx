import { cloneElement, type ReactElement, type ReactNode } from "react";
import { cx } from "../../lib/cx";

/**
 * The shared Library list unit: a leading mark (avatar, colour dot or nothing),
 * a title, an optional secondary line, and a trailing action slot. People uses
 * it for person rows; Activities, Goals and Moods use it for their grouped
 * directories; Tags uses it for its flat card grid. It carries a radius and no
 * divider — never both (DESIGN.md §5) — and the caller supplies the `<ul>`.
 *
 * `rowLink` makes the whole row open a route (Library push-navigation,
 * DESIGN.md §24): pass a router `<Link>` and the leading + text become a
 * stretched link; the `actions` slot stays clickable on top of it.
 */
export function LibraryRow({
  leading,
  title,
  meta,
  actions,
  className,
  rowLink,
}: {
  leading?: ReactNode;
  title: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
  className?: string;
  rowLink?: ReactElement<{ className?: string }>;
}) {
  const body = (
    <>
      {leading != null && (
        <span className="jv-lib-row__leading">{leading}</span>
      )}
      <span className="jv-lib-row__text">
        <span className="jv-lib-row__title jv-truncate">{title}</span>
        {meta != null && (
          <span className="jv-lib-row__meta jv-caption jv-truncate">
            {meta}
          </span>
        )}
      </span>
    </>
  );

  return (
    <li className={cx("jv-lib-row", rowLink && "jv-lib-row--link", className)}>
      {rowLink
        ? cloneElement(
            rowLink,
            {
              className: cx("jv-lib-row__hit", rowLink.props.className),
            },
            body,
          )
        : body}
      {actions != null && (
        <span className="jv-lib-row__actions">{actions}</span>
      )}
    </li>
  );
}
