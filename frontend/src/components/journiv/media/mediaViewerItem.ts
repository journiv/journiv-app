import type {
  MediaLibraryItem,
  MomentMediaResponse,
} from "../../../api/generated/types.gen";

/**
 * Journiv's own model for one slide in the full-screen media viewer.
 *
 * The viewer is backed by a third-party lightbox (`yet-another-react-lightbox`).
 * Feature code and the viewer talk in `MediaViewerItem`, never in the library's
 * slide types or in a raw API response — so the two API shapes that can feed it
 * (`MomentMediaResponse` from the Reader, `MediaLibraryItem` from the Library,
 * and any future source such as Immich) converge on one contract, and swapping
 * the lightbox is a change to one component.
 *
 * The collection is **ready media only**: an `image` or `video` whose upload has
 * completed and that has a signed URL. Anything still processing, failed to
 * upload, or of a kind with no full-screen presentation (audio, `unknown`) is
 * left in the Reader gallery and never becomes a slide position. A slide that
 * was ready but whose URL breaks *at runtime* stays in place and is shown as an
 * error there (see `MediaViewer`'s `brokenIds`), so the slide count and
 * prev/next position never shift mid-session.
 */
export type MediaViewerItem = {
  /** Stable media id. The viewer is keyed by this, never by `src` — a
   *  re-signed URL changes `src` but must not change which slide is active. */
  id: string;
  kind: "image" | "video";
  /** Signed file URL. Always present (non-ready media is filtered out). */
  src: string;
  /** Signed poster/thumbnail URL, used as the video poster. */
  thumbnailSrc?: string;
  /** Image alt text. Never a caption (see docs/features/reader.md). `""` when absent. */
  alt: string;
  /** Original filename, shown as a subtle footer label when available. */
  filename?: string;
  mimeType?: string;
  width?: number;
  height?: number;
};

function isReady(uploadStatus: string | null | undefined, hasUrl: boolean) {
  // `completed`, or an older row with no status, both count as ready.
  return (
    hasUrl &&
    uploadStatus !== "pending" &&
    uploadStatus !== "processing" &&
    uploadStatus !== "failed"
  );
}

function toViewerItem(source: {
  id: string;
  media_type: string;
  mime_type?: string | null;
  upload_status?: string | null;
  width?: number | null;
  height?: number | null;
  alt_text?: string | null;
  signed_url?: string | null;
  signed_thumbnail_url?: string | null;
  original_filename?: string | null;
}): MediaViewerItem | null {
  if (source.media_type !== "image" && source.media_type !== "video") {
    return null;
  }
  if (!isReady(source.upload_status, Boolean(source.signed_url))) return null;
  return {
    id: source.id,
    kind: source.media_type,
    src: source.signed_url ?? "",
    thumbnailSrc: source.signed_thumbnail_url ?? undefined,
    alt: source.alt_text ?? "",
    filename: source.original_filename ?? undefined,
    mimeType: source.mime_type ?? undefined,
    width: source.width ?? undefined,
    height: source.height ?? undefined,
  };
}

/** Reader / editor: the ordered result of the moment-media endpoint. */
export function momentMediaToViewerItems(
  items: readonly MomentMediaResponse[] | undefined,
): MediaViewerItem[] {
  return (items ?? []).flatMap((item) => {
    const viewer = toViewerItem(item);
    return viewer ? [viewer] : [];
  });
}

/** Media library: one page's worth of flat library items. */
export function libraryMediaToViewerItems(
  items: readonly MediaLibraryItem[] | undefined,
): MediaViewerItem[] {
  return (items ?? []).flatMap((item) => {
    const viewer = toViewerItem({ ...item, original_filename: null });
    return viewer ? [viewer] : [];
  });
}
