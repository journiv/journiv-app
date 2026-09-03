import type { ReactNode } from "react";
import type {
  JournalResponse,
  MomentResponse,
} from "../../api/generated/types.gen";
import { formatDayLong, formatTimeOfDay } from "../../lib/datetime";
import { MomentMeta } from "./MomentMeta";
import { JournalBadge } from "./JournalBadge";

/**
 * The document header shared by the reader and the editor.
 *
 * Both surfaces MUST use this component so that reading and writing cannot
 * drift apart typographically. If the entry has no title, the date becomes the
 * page heading — a title is never invented.
 *
 * `title` is a slot: the reader passes an <h1>, the editor passes its title
 * field. When it is omitted this component renders the date as the <h1>.
 *
 * `dateControl` is likewise a slot: the editor passes an interactive control
 * that edits the Moment's `logged_at_utc` (docs/features/editor.md); the reader passes
 * nothing and the date/time renders as plain text.
 */
export function EntryHeader({
  loggedAtUtc,
  loggedTimezone,
  moment,
  journal,
  title,
  dateControl,
  kindLabel,
  children,
}: {
  loggedAtUtc: string;
  loggedTimezone: string;
  /** Optional: a new entry has no Moment yet, so metadata is simply absent. */
  moment?: MomentResponse;
  journal?: JournalResponse;
  title?: ReactNode;
  /** Editor-only: replaces the static date/time line with an editable control. */
  dateControl?: ReactNode;
  kindLabel?: string | null;
  children?: ReactNode;
}) {
  const day = formatDayLong(loggedAtUtc, loggedTimezone);
  const time = formatTimeOfDay(loggedAtUtc, loggedTimezone);

  return (
    <header className="jv-entry-header">
      {title ? (
        <>
          {dateControl ?? (
            <p className="jv-entry-header__date jv-meta">
              {day} · {time}
            </p>
          )}
          {title}
        </>
      ) : (
        <>
          <h1 className="jv-entry-title jv-entry-title--date">{day}</h1>
          {dateControl ?? (
            <p className="jv-entry-header__date jv-meta">
              {time}
              {kindLabel ? ` · ${kindLabel}` : ""}
            </p>
          )}
        </>
      )}
      {moment ? (
        <MomentMeta
          moment={moment}
          journal={journal}
          surface="reader"
          className="jv-entry-header__meta"
        />
      ) : (
        journal && (
          <div className="jv-meta jv-meta-row jv-entry-header__meta">
            <span className="jv-meta-cell">
              <JournalBadge journal={journal} />
            </span>
          </div>
        )
      )}
      {children}
    </header>
  );
}
