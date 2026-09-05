import {
  Check,
  FileAudio,
  ImageOff,
  Loader2,
  Paperclip,
  TriangleAlert,
} from "lucide-react";
import { type ReactNode, useState } from "react";
import type {
  MomentMediaResponse,
  MomentResponse,
} from "../../api/generated/types.gen";
import { cx } from "../../lib/cx";
import { mediaPath } from "../../lib/mediaUrl";
import { Button } from "../ui/button";
import { Skeleton } from "../ui/skeleton";
import "./momentMedia.css";
import type { MomentMediaState } from "./useMomentMedia";

/**
 * A Moment's media gallery.
 *
 * Two treatments, one data source:
 *
 * - `variant="content"` (default, the Reader): full-bleed, uncropped, one
 *   column — this media *is* the entry's content. `alt_text` is alt text, never
 *   a caption. Media referenced inline by the prose is excluded so it does not
 *   appear twice.
 * - `variant="tray"` (the Editor): a labelled panel of small cropped
 *   thumbnails — media *attached to the Moment* that is not in the entry yet.
 *   `excludePaths` marks an item as already added rather than hiding it, so
 *   "Add to entry" has a visible before/after. See docs/features/editor.md.
 *
 * The component stays presentational and Quill-free; the Editor passes
 * `renderItemAction` for the per-item "Add to entry" control.
 */
type MomentMediaGalleryProps = {
  moment: MomentResponse;
  media: MomentMediaState;
  /**
   * Paths of media already rendered inline in the prose. Matched on path
   * because the signature query string differs between the copy hydrated into
   * the document and the copy returned by the media endpoint. In `content`
   * mode these items are hidden; in `tray` mode they are shown as "Added".
   */
  excludePaths?: ReadonlySet<string>;
  /** `"content"` (default) or `"tray"`. */
  variant?: "content" | "tray";
  /**
   * Optional per-item control. The Editor uses it for "Add to entry"; the
   * Reader passes nothing. Return a falsy value for an item the action does not
   * apply to (e.g. a `media_type` the editor cannot place inline) — that item
   * still renders as a plain attachment. Not called for items already added.
   */
  renderItemAction?: (item: MomentMediaResponse) => ReactNode;
};

export function MomentMediaGallery(props: MomentMediaGalleryProps) {
  if ((props.moment.media_count ?? 0) === 0) return null;
  return props.variant === "tray" ? (
    <MediaTray {...props} />
  ) : (
    <ContentGallery {...props} />
  );
}

/* -------------------------------------------------------------------------
 * Reader: media as entry content.
 * ---------------------------------------------------------------------- */

function ContentGallery({
  media,
  excludePaths,
  renderItemAction,
}: MomentMediaGalleryProps) {
  if (media.isLoading) {
    return (
      <div className="jv-media" role="status" aria-label="Loading media">
        <Skeleton className="jv-media__placeholder" />
      </div>
    );
  }

  // Known user content must not disappear without a word — but it must also not
  // block the writing, so this stays a quiet inline notice rather than a
  // pane-filling error.
  if (media.isError) {
    return (
      <div className="jv-media">
        <MediaError media={media} />
      </div>
    );
  }

  // An authoritative empty list beats a denormalised `media_count`: the count
  // lives on the Moment row and can drift. Nothing to retry, so stay silent.
  const items = (media.items ?? []).filter(
    (item) => !excludePaths?.has(mediaPath(item.signed_url ?? "")),
  );
  if (!items.length) return null;

  return (
    <div className="jv-media">
      {items.map((item) => (
        <MediaItem
          key={item.id}
          item={item}
          broken={Boolean(media.broken[item.id])}
          onLoadError={media.reportLoadFailure}
          action={renderItemAction?.(item)}
        />
      ))}
    </div>
  );
}

function MediaItem({
  item,
  broken,
  onLoadError,
  action,
}: {
  item: MomentMediaResponse;
  broken: boolean;
  onLoadError: (id: string) => void;
  action?: ReactNode;
}) {
  const status = item.upload_status ?? "completed";
  // The frame always reserves space. When the API reported dimensions it uses
  // the item's own ratio, so nothing is cropped and nothing shifts.
  const ratio =
    item.width && item.height ? `${item.width} / ${item.height}` : undefined;
  const frame = {
    className: "jv-media__frame",
    style: ratio ? { aspectRatio: ratio } : undefined,
  };
  const noun = item.media_type === "image" ? "Photo" : "Media";

  // The action attaches to a ready item only — there is nothing to add to the
  // prose while an item is still processing or is unavailable.
  const withAction = (body: ReactNode) =>
    action ? (
      <div className="jv-media__item">
        {body}
        <div className="jv-media__item-action">{action}</div>
      </div>
    ) : (
      body
    );

  if (status === "pending" || status === "processing") {
    return (
      <div {...frame} role="status">
        <span className="jv-media__note">
          <Loader2 className="jv-spin" aria-hidden="true" size={16} />
          Processing
        </span>
      </div>
    );
  }

  if (status === "failed" || broken || !item.signed_url) {
    return (
      <div {...frame}>
        <span className="jv-media__note">
          <ImageOff aria-hidden="true" size={16} />
          {noun} unavailable
        </span>
      </div>
    );
  }

  if (item.media_type === "video") {
    return withAction(
      <div {...frame}>
        {/* PROVISIONAL: verified against images only. See docs/known-gaps.md. */}
        {/* biome-ignore lint/a11y/useMediaCaption: Journiv has no caption or
            subtitle field on media, so there is nothing to attach a <track> to. */}
        <video
          className={cx("jv-media__element", "jv-media__element--contain")}
          src={item.signed_url}
          poster={item.signed_thumbnail_url ?? undefined}
          controls
          preload="metadata"
          onError={() => onLoadError(item.id)}
        />
      </div>,
    );
  }

  if (item.media_type === "audio") {
    return withAction(
      <div className="jv-media__audio">
        {/* PROVISIONAL: verified against images only. See docs/features/reader.md. */}
        {/* biome-ignore lint/a11y/useMediaCaption: no caption field exists. */}
        <audio
          className="jv-media__element"
          src={item.signed_url}
          controls
          preload="metadata"
          onError={() => onLoadError(item.id)}
        />
      </div>,
    );
  }

  // A kind this build cannot preview (`media_type: "unknown"`). It stays a
  // visible Moment attachment — never dropped, never inserted — and the
  // consumer's action, if any, is expected to withhold itself for it.
  if (item.media_type !== "image") {
    return withAction(
      <div {...frame}>
        <span className="jv-media__note">
          <Paperclip aria-hidden="true" size={16} />
          Attachment
        </span>
      </div>,
    );
  }

  return withAction(
    <div {...frame}>
      <img
        className={cx("jv-media__element", "jv-media__element--contain")}
        src={item.signed_url}
        alt={item.alt_text ?? ""}
        width={item.width ?? undefined}
        height={item.height ?? undefined}
        loading="lazy"
        decoding="async"
        onError={() => onLoadError(item.id)}
      />
    </div>,
  );
}

/* -------------------------------------------------------------------------
 * Editor: media as an attachment tray, distinct from the writing.
 * ---------------------------------------------------------------------- */

function MediaTray({
  media,
  excludePaths,
  renderItemAction,
}: MomentMediaGalleryProps) {
  const [expanded, setExpanded] = useState(false);

  const shell = (body: ReactNode, extraHint?: ReactNode) => (
    <section
      className="jv-media jv-media--tray"
      aria-label="Attached to this moment"
    >
      <div className="jv-media__tray-head">
        <span className="jv-media__tray-label">On this moment</span>
        {extraHint ?? (
          <p className="jv-media__tray-hint">
            These attachments aren’t in your entry yet. Add the ones you want to
            include.
          </p>
        )}
      </div>
      {body}
    </section>
  );

  if (media.isLoading) {
    return shell(
      <div
        className="jv-media__tray-grid"
        role="status"
        aria-label="Loading media"
      >
        <Skeleton className="jv-media__tile" />
        <Skeleton className="jv-media__tile" />
        <Skeleton className="jv-media__tile" />
      </div>,
    );
  }
  if (media.isError) {
    return shell(<MediaError media={media} />);
  }

  const items = media.items ?? [];
  if (!items.length) return null;

  const isAdded = (item: MomentMediaResponse) =>
    Boolean(excludePaths?.has(mediaPath(item.signed_url ?? "")));
  const addable = items.filter(
    (item) => (item.upload_status ?? "completed") !== "failed",
  );
  const addedCount = addable.filter(isAdded).length;
  const allAdded = addable.length > 0 && addedCount === addable.length;
  const collapsed = allAdded && !expanded;

  const toggle = allAdded ? (
    <Button
      variant="ghost"
      size="sm"
      className="jv-media__tray-toggle"
      onClick={() => setExpanded((value) => !value)}
    >
      {collapsed ? "Show" : "Hide"}
    </Button>
  ) : null;

  if (collapsed) {
    return shell(
      null,
      <div className="jv-media__tray-summary">
        <p className="jv-media__tray-hint">
          <Check aria-hidden="true" size={14} />
          {addedCount === 1
            ? "1 attachment added to your entry"
            : `${addedCount} attachments added to your entry`}
        </p>
        {toggle}
      </div>,
    );
  }

  return shell(
    <>
      {toggle && <div className="jv-media__tray-summary">{toggle}</div>}
      <ul className="jv-media__tray-grid">
        {items.map((item) => {
          const added = isAdded(item);
          return (
            <TrayTile
              key={item.id}
              item={item}
              added={added}
              broken={Boolean(media.broken[item.id])}
              onLoadError={media.reportLoadFailure}
              action={added ? null : renderItemAction?.(item)}
            />
          );
        })}
      </ul>
    </>,
  );
}

function TrayTile({
  item,
  added,
  broken,
  onLoadError,
  action,
}: {
  item: MomentMediaResponse;
  added: boolean;
  broken: boolean;
  onLoadError: (id: string) => void;
  action?: ReactNode;
}) {
  const status = item.upload_status ?? "completed";
  const unavailable = status === "failed" || broken || !item.signed_url;
  const busy = status === "pending" || status === "processing";
  const label = item.alt_text?.trim() || undefined;

  let body: ReactNode;
  if (busy) {
    body = (
      <span className="jv-media__tile-glyph" title="Processing">
        <Loader2 className="jv-spin" aria-hidden="true" size={18} />
      </span>
    );
  } else if (unavailable) {
    body = (
      <span className="jv-media__tile-glyph" title="Unavailable">
        <ImageOff aria-hidden="true" size={18} />
      </span>
    );
  } else if (item.media_type === "image") {
    body = (
      <img
        src={item.signed_url ?? ""}
        alt={item.alt_text ?? ""}
        loading="lazy"
        decoding="async"
        onError={() => onLoadError(item.id)}
      />
    );
  } else if (item.media_type === "video") {
    body = (
      <video
        src={item.signed_url ?? ""}
        poster={item.signed_thumbnail_url ?? undefined}
        muted
        preload="metadata"
        onError={() => onLoadError(item.id)}
      />
    );
  } else if (item.media_type === "audio") {
    body = (
      <span className="jv-media__tile-glyph" title={label ?? "Audio"}>
        <FileAudio aria-hidden="true" size={18} />
      </span>
    );
  } else {
    body = (
      <span className="jv-media__tile-glyph" title={label ?? "Attachment"}>
        <Paperclip aria-hidden="true" size={18} />
      </span>
    );
  }

  return (
    <li
      className={cx("jv-media__tile", added && "jv-media__tile--added")}
      title={label}
    >
      {body}
      {added ? (
        <span className="jv-media__tile-badge" title="Added to entry">
          <Check aria-hidden="true" size={14} />
        </span>
      ) : (
        action && <div className="jv-media__tile-action">{action}</div>
      )}
    </li>
  );
}

function MediaError({ media }: { media: MomentMediaState }) {
  return (
    <p className="jv-media__failure" role="status">
      <TriangleAlert aria-hidden="true" size={15} />
      <span>Media couldn’t be loaded</span>
      <Button
        variant="ghost"
        size="sm"
        onClick={media.retryAll}
        disabled={media.isFetching}
      >
        {media.isFetching ? "Retrying…" : "Retry"}
      </Button>
    </p>
  );
}
