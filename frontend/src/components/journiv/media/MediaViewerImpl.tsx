import { ImageOff } from "lucide-react";
import { useEffect, useMemo } from "react";
import Lightbox, {
  type Callbacks,
  type Render,
  type Slide,
} from "yet-another-react-lightbox";
import Counter from "yet-another-react-lightbox/plugins/counter";
import Fullscreen from "yet-another-react-lightbox/plugins/fullscreen";
import Video from "yet-another-react-lightbox/plugins/video";
import Zoom from "yet-another-react-lightbox/plugins/zoom";
import "yet-another-react-lightbox/styles.css";
import "yet-another-react-lightbox/plugins/counter.css";
import { usePrefersReducedMotion } from "../../../features/insights/usePrefersReducedMotion";
import { mediaPath } from "../../../lib/mediaUrl";
import { Button } from "../../ui/button";
import { resolveFailedMediaUrl } from "./mediaViewerError";
import type { MediaViewerItem } from "./mediaViewerItem";
import "./mediaViewer.css";

export type MediaViewerProps = {
  /** Ordered, ready media. Build with the `*ToViewerItems` adapters. */
  items: MediaViewerItem[];
  /** Id of the open item, or `null` when the viewer is closed. */
  activeId: string | null;
  /** The active slide changed (prev / next / swipe). */
  onActiveIdChange: (id: string) => void;
  /** The viewer was dismissed (Escape, close button, backdrop). */
  onClose: () => void;
  /**
   * An image or video inside the viewer failed to load once. The caller
   * re-signs that media and updates `items`; the viewer stays on the same
   * `activeId` (a media id, never a URL) and reloads the slide in place.
   */
  onItemError?: (id: string) => void;
  /**
   * Ids whose media has failed twice and is treated as broken. Those slides
   * keep their position and show an in-place error with a retry, rather than
   * disappearing and shifting every following slide.
   */
  brokenIds?: ReadonlySet<string>;
  /** Retry every broken slide (re-sign and reload). */
  onRetry?: () => void;
};

/** Slide object carrying Journiv state back to the render callbacks. */
type JvSlide = Slide & { jvId: string; jvBroken: boolean };

function buildSlide(item: MediaViewerItem, broken: boolean): JvSlide {
  const shared = { jvId: item.id, jvBroken: broken } as const;
  // A broken slide is always image-typed so `render.slide` (below) can draw the
  // error in place. The Video plugin's own slide renderer never delegates to
  // `render.slide` for `type: "video"`, so a broken video kept as a video slide
  // would render blank instead. `src` is unused — `render.slide` intercepts.
  if (broken) {
    return { ...shared, type: "image", src: "" } as JvSlide;
  }
  if (item.kind === "video") {
    return {
      ...shared,
      type: "video",
      poster: item.thumbnailSrc,
      width: item.width,
      height: item.height,
      controls: true,
      preload: "metadata",
      playsInline: true,
      sources: [{ src: item.src, type: item.mimeType ?? "video/mp4" }],
    } as JvSlide;
  }
  return {
    ...shared,
    type: "image",
    src: item.src,
    alt: item.alt,
    width: item.width,
    height: item.height,
  } as JvSlide;
}

function ErrorSlide({ onRetry }: { onRetry?: () => void }) {
  return (
    <div className="jv-media-viewer__error" role="status">
      <ImageOff aria-hidden="true" size={28} />
      <p className="jv-media-viewer__error-text">
        This media couldn’t be loaded.
      </p>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

/**
 * Full-screen media viewer, backed by `yet-another-react-lightbox` (v3.32).
 *
 * The library is used *only* as a media viewer. It renders its own portal with
 * `role="dialog"` + `aria-modal="true"` unconditionally, names it from
 * `labels.Lightbox`, marks every sibling `inert` + `aria-hidden` while open,
 * moves focus into the dialog on open (`controller.focus`, default on) and
 * restores it to the trigger on close. `controller.aria` is a deprecated
 * internal no-op in this version and is intentionally not set. Because the
 * library manages focus, scroll lock and keyboard handling itself, it is never
 * wrapped in a Journiv `Dialog`.
 *
 * Loaded lazily through `MediaViewer` so the library and its plugins stay off
 * the route's initial bundle.
 */
export function MediaViewerImpl({
  items,
  activeId,
  onActiveIdChange,
  onClose,
  onItemError,
  brokenIds,
  onRetry,
}: MediaViewerProps) {
  const reduceMotion = usePrefersReducedMotion();

  const slides = useMemo(
    () =>
      items.map((item) => buildSlide(item, Boolean(brokenIds?.has(item.id)))),
    [items, brokenIds],
  );
  const index = Math.max(
    0,
    items.findIndex((item) => item.id === activeId),
  );
  const open = activeId != null && items.some((item) => item.id === activeId);

  // Media load errors do not bubble, so catch them in the capture phase on the
  // document — the lightbox renders into a portal outside this subtree, and the
  // Video plugin puts no `onError` on its <video>/<source> at all. Mirrors the
  // inline-media recovery in features/editor/QuillReader.tsx.
  useEffect(() => {
    if (!open || !onItemError) return;
    const handle = (event: Event) => {
      const target = event.target;
      if (!(target instanceof Element) || !target.closest(".jv-media-viewer")) {
        return;
      }
      const url = resolveFailedMediaUrl(target);
      if (!url) return;
      const path = mediaPath(url);
      const hit = items.find(
        (item) => item.src && mediaPath(item.src) === path,
      );
      if (hit) onItemError(hit.id);
    };
    document.addEventListener("error", handle, true);
    return () => document.removeEventListener("error", handle, true);
  }, [open, items, onItemError]);

  const handleView: Callbacks["view"] = ({ index: next }) => {
    const item = items[next];
    if (item && item.id !== activeId) onActiveIdChange(item.id);
  };

  const render: Render = {
    // A healthy slide returns `undefined` so the library's own renderer (and
    // the Zoom / Video plugins) handles it. Only a slide that broke at runtime
    // gets a Journiv-drawn in-place error.
    slide: ({ slide }) =>
      (slide as JvSlide).jvBroken ? (
        <ErrorSlide onRetry={onRetry} />
      ) : undefined,
    slideFooter: ({ slide }) => {
      const item = items.find((i) => i.id === (slide as JvSlide).jvId);
      return item?.filename ? (
        <div className="jv-media-viewer__footer">{item.filename}</div>
      ) : null;
    },
  };

  return (
    <Lightbox
      className="jv-media-viewer"
      open={open}
      close={onClose}
      index={index}
      slides={slides}
      plugins={[Zoom, Video, Counter, Fullscreen]}
      // A moment's media is a finite set; wrapping past the last item back to
      // the first is disorienting here.
      carousel={{ finite: true }}
      controller={{ closeOnBackdropClick: true }}
      video={{ controls: true, preload: "metadata", playsInline: true }}
      labels={{ Lightbox: "Media viewer" }}
      on={{ view: handleView }}
      render={render}
      animation={
        reduceMotion ? { fade: 0, swipe: 0, navigation: 0 } : undefined
      }
    />
  );
}
