import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { FileQuestion, ImageOff, Music, Pin, Video } from "lucide-react";
import type {
  JournalResponse,
  MomentResponse,
} from "../../api/generated/types.gen";
import { MomentMeta } from "../../components/journiv/MomentMeta";
import { formatTimeOfDay } from "../../lib/datetime";
import {
  momentKind,
  momentKindLabel,
  momentLeadMedia,
  momentLeadText,
  momentTitle,
  truncate,
} from "../../lib/moment";
import { cx } from "../../lib/cx";
import { Badge } from "../../components/ui/badge";

/**
 * One Moment in the Timeline.
 *
 * A Moment without a title does NOT get an invented one. Its own content takes
 * the primary slot at body weight, and the time plus a kind label carry the
 * identity. See DESIGN.md "Moment rendering semantics".
 */
export function MomentListItem({
  moment,
  journal,
  journalId,
  selected,
  search,
  view,
  month,
  date,
  scopeSearch,
}: {
  moment: MomentResponse;
  journal?: JournalResponse;
  journalId?: string;
  selected: boolean;
  search: string;
  /** Keeps the calendar/media view (and, for the calendar, its month and
   *  selected day) mounted when a row opens the reader. */
  view?: "calendar" | "media";
  month?: string;
  date?: string;
  /** Keeps an entity scope (`?person=…`, `?tag=…`, …) mounted when the row
   *  opens the reader beside the scoped list (docs/features/library.md). */
  scopeSearch?: Record<string, string>;
}) {
  const kind = momentKind(moment);
  const title = momentTitle(moment);
  const lead = momentLeadText(moment);
  const kindLabel = momentKindLabel(moment, kind);
  const leadMedia = momentLeadMedia(moment);
  // A thumbnail URL can be issued for a file that is gone or unreachable. Keyed
  // by URL so a refreshed signed URL gets a fresh try.
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const extraMedia = (moment.media_count ?? 0) - 1;

  const body = (
    <>
      <span className="jv-moment__body">
        <span className="jv-moment__lead">
          <span className="jv-meta">
            {formatTimeOfDay(moment.logged_at_utc, moment.logged_timezone)}
          </span>
          {kindLabel && <Badge variant="outline">{kindLabel}</Badge>}
          {moment.is_pinned && (
            <Pin className="jv-moment__pin" aria-label="Pinned" size={12} />
          )}
        </span>
        {title && <span className="jv-moment-title jv-clamp-2">{title}</span>}
        {lead && (
          <span
            className={cx(
              title ? "jv-excerpt" : "jv-moment__prose",
              "jv-clamp-2",
            )}
          >
            {truncate(lead, 200)}
          </span>
        )}
        <MomentMeta moment={moment} journal={journal} surface="row" />
      </span>
      {leadMedia && (
        <span
          className={cx(
            "jv-moment__media",
            (leadMedia.kind === "placeholder" || leadMedia.src === failedSrc) &&
              "jv-moment__media--placeholder",
          )}
        >
          {leadMedia.kind === "image" && leadMedia.src !== failedSrc ? (
            <img
              src={leadMedia.src}
              alt=""
              loading="lazy"
              decoding="async"
              onError={() => setFailedSrc(leadMedia.src)}
            />
          ) : (
            <PlaceholderGlyph media={leadMedia.media} />
          )}
          {leadMedia.kind === "image" && leadMedia.hasAudio && (
            <span className="jv-moment__media-audio" aria-hidden="true">
              <Music size={12} />
            </span>
          )}
          {extraMedia > 0 && (
            <span className="jv-moment__media-count">+{extraMedia}</span>
          )}
        </span>
      )}
    </>
  );

  const className = cx("jv-moment", selected && "is-selected");
  const linkSearch = {
    q: search,
    ...(view ? { view } : {}),
    ...(view === "calendar" && month ? { month } : {}),
    ...(view === "calendar" && date ? { date } : {}),
    ...(scopeSearch ?? {}),
  };
  return journalId ? (
    <Link
      className={className}
      to="/journals/$journalId/$momentId"
      params={{ journalId, momentId: moment.id }}
      search={linkSearch}
      aria-current={selected ? "page" : undefined}
    >
      {body}
    </Link>
  ) : (
    <Link
      className={className}
      to="/timeline/$momentId"
      params={{ momentId: moment.id }}
      search={linkSearch}
      aria-current={selected ? "page" : undefined}
    >
      {body}
    </Link>
  );
}

/** Stands in for an attachment with no thumbnail, like the Media pane tiles. */
function PlaceholderGlyph({
  media,
}: {
  media: "audio" | "video" | "image" | "unknown";
}) {
  const Glyph =
    media === "audio"
      ? Music
      : media === "video"
        ? Video
        : media === "image"
          ? ImageOff
          : FileQuestion;
  return <Glyph aria-hidden="true" size={24} />;
}
