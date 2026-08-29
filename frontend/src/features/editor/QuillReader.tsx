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
}) {
  const plan = planReaderContent(content);
  const hostRef = useRef<HTMLDivElement>(null);
  const reported = useRef(false);

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
    <div ref={hostRef}>
      <QuillSurface
        editorId={`reader-${entryId}`}
        initialContent={plan.delta}
        formats={READER_FORMATS}
        readOnly
      />
    </div>
  );
}
