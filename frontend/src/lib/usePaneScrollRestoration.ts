import { useLayoutEffect, useRef } from "react";

const scrollPositions = new Map<string, number>();

/** Gestures that mean the reader has taken over: restoration stops rather
 *  than yanking them back to where they were last time. */
const USER_GESTURES = ["wheel", "touchstart", "keydown"] as const;

/**
 * Restores a pane's own scroll position across an unmount/remount caused by
 * navigating away and back. Timeline, Journals, Media, Calendar and each
 * Library section are sibling routes, so moving between two of them — or
 * opening a Library detail, which is a push page — fully remounts the list
 * pane, which otherwise lands back at the top (DESIGN.md "Navigation
 * loading"). Selecting a moment from the Timeline does *not* need this:
 * `/timeline` and `/timeline/$momentId` both render `Workspace`, which React
 * reconciles rather than remounts, so that pane keeps its scroll natively.
 *
 * `key` identifies the logical pane, not a DOM node or a route path — pass a
 * stable string unique to that list (`"timeline"`, `"journals"`,
 * `"library:Tags"`), so unrelated panes never share or overwrite each
 * other's remembered position. Attach the returned ref to the pane's single
 * scroll owner element. `isLoading` keeps restoration alive while initial
 * rows are pending; once loading completes, the hook stops after its final
 * attempt even if the pane is now too short to reach the old offset.
 */
export function usePaneScrollRestoration<T extends HTMLElement>(
  key: string,
  isLoading = false,
) {
  const ref = useRef<T | null>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;

    // Read once, up front. `scrollTop` clamps to whatever content exists at
    // this instant, and the browser fires a real `scroll` event for that
    // clamp — so a listener that records every scroll would write the clamped
    // value back over the target and destroy it before the content is tall
    // enough to reach it. `restoring` is what keeps the listener quiet until
    // we are done, and is why the target lives in a local rather than being
    // re-read from the map on each attempt.
    const target = scrollPositions.get(key) ?? 0;
    let restoring = target > 0;
    let observer: MutationObserver | undefined;

    const stop = () => {
      restoring = false;
      observer?.disconnect();
      // Deliberately does not record where we ended up. If loaded content is
      // shorter than it was on the previous visit, the saved offset is still
      // the right one for the next visit, and the reader's own scrolling
      // replaces it the moment they move.
    };

    const attempt = () => {
      if (!restoring) return;
      el.scrollTop = target;
      if (el.scrollTop === target) stop();
    };

    const onScroll = () => {
      if (!restoring) scrollPositions.set(key, el.scrollTop);
    };

    el.addEventListener("scroll", onScroll, { passive: true });
    for (const type of USER_GESTURES) {
      el.addEventListener(type, stop, { passive: true });
    }

    if (restoring) {
      // A skeleton-to-content handoff lands whenever its query resolves, many
      // frames after mount — so a single `requestAnimationFrame` cannot see
      // it. Re-attempt on subtree changes until the query settles, rather than
      // imposing a deadline that can expire before delayed rows arrive.
      observer = new MutationObserver(attempt);
      observer.observe(el, { childList: true, subtree: true });
      attempt();
      if (restoring && !isLoading) stop();
    }

    return () => {
      stop();
      el.removeEventListener("scroll", onScroll);
      for (const type of USER_GESTURES) {
        el.removeEventListener(type, stop);
      }
    };
  }, [key, isLoading]);

  return ref;
}
