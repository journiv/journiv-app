import { ImageOff, Loader2, TriangleAlert } from "lucide-react";
import type {
  MomentMediaResponse,
  MomentResponse,
} from "../../api/generated/types.gen";
import { Button } from "../../components/ui/button";
import { Skeleton } from "../../components/ui/skeleton";
import { mediaPath } from "../editor/deltaProfile";
import { cx } from "../../lib/cx";
import type { MomentMediaState } from "./useMomentMedia";

/**
 * The Moment's media gallery, rendered between the entry header and the prose.
 *
 * Design rules (docs/features/reader.md):
 * - `alt_text` is ALT TEXT. It goes in the `alt` attribute. Journiv has no
 *   caption field, so nothing is rendered under an image.
 * - Photographs are NEVER cropped. There is no full-image viewer yet, so a
 *   cropped preview would hide part of a memory with no way to inspect it.
 *   Every item is shown whole, at its own aspect ratio.
 * - `width`/`height` reserve the box so the prose cannot jump while decoding.
 * - Media referenced inline by the entry is excluded here — it is rendered in
 *   the prose instead, and must not appear twice.
 */
export function EntryMedia({
  moment,
  media,
  excludePaths,
}: {
  moment: MomentResponse;
  media: MomentMediaState;
  /**
   * Paths of media already rendered inline in the prose. Matched on path
   * because the signature query string differs between the copy hydrated into
   * the document and the copy returned by the media endpoint.
   */
  excludePaths?: ReadonlySet<string>;
}) {
  if ((moment.media_count ?? 0) === 0) return null;

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
        />
      ))}
    </div>
  );
}

function MediaItem({
  item,
  broken,
  onLoadError,
}: {
  item: MomentMediaResponse;
  broken: boolean;
  onLoadError: (id: string) => void;
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
    return (
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
      </div>
    );
  }

  if (item.media_type === "audio") {
    return (
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
      </div>
    );
  }

  if (item.media_type !== "image") return null;

  return (
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
    </div>
  );
}
