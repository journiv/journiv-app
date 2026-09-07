/**
 * The URL that failed to load, given the target of a captured `error` event
 * inside the viewer. Covers the three shapes the lightbox can produce:
 *
 * - `<img>` — a plain image slide.
 * - `<source>` — a child of the Video plugin's `<video>`; `error` fires on the
 *   `<source>`, and it does not bubble, which is why the listener is capturing.
 * - `<video>` — the final failure once every `<source>` has failed;
 *   `currentSrc` is then empty, so fall back to the first `<source>`.
 *
 * Anything else returns `""` and the caller ignores it.
 */
export function resolveFailedMediaUrl(target: EventTarget | null): string {
  if (target instanceof HTMLImageElement) {
    return target.currentSrc || target.src;
  }
  if (target instanceof HTMLSourceElement) {
    return target.src;
  }
  if (target instanceof HTMLVideoElement) {
    return target.currentSrc || target.querySelector("source")?.src || "";
  }
  return "";
}
