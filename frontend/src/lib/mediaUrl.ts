/**
 * Media URL helpers that are not tied to the Quill document.
 *
 * Journiv serves every attachment from `/api/v1/media/<id>/signed?…`, where the
 * `uid/exp/sig` query string is a short-lived credential that differs between
 * two fetches of the same file. Anything that needs to compare or de-duplicate
 * media across surfaces must key on the path, which is stable.
 */

/** Path portion of a media URL — stable across re-signing. */
export function mediaPath(source: string): string {
  return new URL(source, window.location.origin).pathname;
}
