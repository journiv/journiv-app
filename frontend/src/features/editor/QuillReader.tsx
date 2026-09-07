import { useEffect, useRef } from "react";
import type { QuillDelta } from "../../api/generated/types.gen";
import {
  hasUnsupportedEmbed,
  inlineMediaPaths,
  isReaderDocumentDelta,
  JOURNIV_DELTA_FORMATS,
} from "./deltaProfile";
import "./mediaBlots";
import { QuillSurface } from "./QuillSurface";

/** Reader profile: Gate-1 formats plus inline media. Never used for saving. */
const READER_FORMATS = [
  ...JOURNIV_DELTA_FORMATS,
  "image",
  "video",
  "audio",
] as const;

/**
 * How the reader can present a stored document.
 *
 * `inlinePaths` lets the gallery skip media that the prose already shows.
 */
export function planReaderContent(content: unknown) {
  if (
    !isReaderDocumentDelta(content) ||
    hasUnsupportedEmbed(content as QuillDelta)
  ) {
    return { renderable: false as const, inlinePaths: new Set<string>() };
  }
  const delta = content as QuillDelta;
  return {
    renderable: true as const,
    delta,
    inlinePaths: new Set(inlineMediaPaths(delta)),
  };
}

export function QuillReader({
  content,
  entryId,
  plainText,
  onMediaError,
  onImageActivate,
}: {
  content: unknown;
  entryId: string;
  plainText?: string | null;
  /**
   * Called when an inline image fails to load. Inline sources are signed URLs
   * hydrated into the document by the backend, so re-signing them means
   * refetching the entry — the media endpoint cannot help here.
   */
  onMediaError?: () => void;
  /**
   * Called with the `src` of an inline image the reader activates (click, or
   * Enter / Space while it is focused), to open it in the full-screen viewer.
   * When set, inline images are given button semantics and made keyboard
   * focusable. Images only — an inline `<video>` keeps its native controls and
   * has no expand affordance here.
   */
  onImageActivate?: (src: string) => void;
}) {
  const plan = planReaderContent(content);
  const hostRef = useRef<HTMLDivElement>(null);
  const reported = useRef(false);

  // biome-ignore lint/correctness/useExhaustiveDependencies: entryId intentionally resets this ref for each entry.
  useEffect(() => {
    reported.current = false;
  }, [entryId]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host || !onMediaError) return;
    // Image load errors do not bubble, so listen in the capture phase.
    const handle = (event: Event) => {
      if (!(event.target instanceof HTMLImageElement) || reported.current)
        return;
      reported.current = true;
      onMediaError();
    };
    host.addEventListener("error", handle, true);
    return () => host.removeEventListener("error", handle, true);
  }, [onMediaError]);

  // Quill renders inline images as plain <img> inside a non-editable surface, so
  // they are neither focusable nor operable by keyboard. A real <button> would
  // need a custom blot; giving the <img> button semantics + a tab stop is the
  // practical equivalent. The activation itself stays delegated on the host.
  useEffect(() => {
    const host = hostRef.current;
    if (!host || !onImageActivate) return;

    const stampImages = () => {
      for (const img of host.querySelectorAll<HTMLImageElement>("img")) {
        if (img.dataset.jvActivatable) continue;
        img.dataset.jvActivatable = "true";
        img.setAttribute("role", "button");
        img.setAttribute("tabindex", "0");
        if (!img.hasAttribute("aria-label")) {
          img.setAttribute(
            "aria-label",
            img.alt ? `View image: ${img.alt}` : "View image",
          );
        }
      }
    };
    stampImages();
    // Re-stamp if the document is re-rendered (e.g. a re-signed entry refetch).
    const observer = new MutationObserver(stampImages);
    observer.observe(host, { childList: true, subtree: true });

    const activate = (target: EventTarget | null) => {
      if (!(target instanceof HTMLImageElement) || !target.src) return false;
      onImageActivate(target.src);
      return true;
    };
    const onClick = (event: MouseEvent) => {
      if (activate(event.target)) event.preventDefault();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      if (!(event.target instanceof HTMLImageElement)) return;
      // Space would otherwise scroll the page.
      event.preventDefault();
      activate(event.target);
    };
    host.addEventListener("click", onClick);
    host.addEventListener("keydown", onKeyDown);
    return () => {
      observer.disconnect();
      host.removeEventListener("click", onClick);
      host.removeEventListener("keydown", onKeyDown);
    };
  }, [onImageActivate]);

  if (!plan.renderable) {
    return (
      <div className="jv-reader-content-warning" role="note">
        <p>Some formatting or media in this entry cannot be displayed yet.</p>
        {plainText ? (
          <p className="jv-reader-plain-text">{plainText}</p>
        ) : (
          <p>No plain-text preview is available.</p>
        )}
      </div>
    );
  }

  return (
    <div
      ref={hostRef}
      className={onImageActivate ? "jv-reader-content--zoomable" : undefined}
    >
      <QuillSurface
        editorId={`reader-${entryId}`}
        initialContent={plan.delta}
        formats={READER_FORMATS}
        readOnly
      />
    </div>
  );
}
