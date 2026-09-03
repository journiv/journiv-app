import { cloneElement, type ReactElement, type ReactNode } from "react";
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemMedia,
  ItemTitle,
} from "../ui/item";
import { cx } from "../../lib/cx";

/**
 * The shared Library list unit: a leading mark (avatar, colour dot or nothing),
 * a title, an optional secondary line, and a trailing action slot. People uses
 * it for person rows; Activities, Goals and Moods use it for their grouped
 * directories; Tags uses it for its flat card grid.
 *
 * The row itself is a stock `Item`. What is Journiv's is `rowLink` (Library
 * push-navigation, docs/features/library.md): pass a router `<Link>` and the leading +
 * text become one stretched link, with the `actions` slot staying clickable on
 * top of it — and the `⋯` resting hidden until hover or focus, so a list at
 * rest is just people.
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
      {leading != null && <ItemMedia>{leading}</ItemMedia>}
      {/* `min-w-0` so a long title or blurb ellipsises inside the row instead
          of forcing the row wider than its pane — `flex-1` alone keeps the
          flex child at its content width. */}
      <ItemContent className="min-w-0">
        <ItemTitle className="jv-truncate">{title}</ItemTitle>
        {/* The blurb clamps to two lines (upstream's own treatment); it is a
            sentence, never a single truncated line. */}
        {meta != null && <ItemDescription>{meta}</ItemDescription>}
      </ItemContent>
    </>
  );

  if (rowLink) {
    return (
      <li className={cx("jv-lib-row jv-lib-row--link", className)}>
        {cloneElement(
          rowLink,
          { className: cx("jv-lib-row__hit", rowLink.props.className) },
          <Item size="sm" render={<span />}>
            {body}
          </Item>,
        )}
        {actions != null && (
          <span className="jv-lib-row__actions">{actions}</span>
        )}
      </li>
    );
  }

  return (
    <Item size="sm" className={cx("jv-lib-row", className)} render={<li />}>
      {body}
      {actions != null && (
        <ItemActions className="jv-lib-row__actions">{actions}</ItemActions>
      )}
    </Item>
  );
}
