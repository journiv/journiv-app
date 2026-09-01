import { useSyncExternalStore } from "react";

/** DESIGN.md §9's compact boundary — at or below this width the app is one
 *  pane per screen, and an adaptive overlay presents as a Drawer. */
export const COMPACT_QUERY = "(max-width: 860px)";

function subscribe(onStoreChange: () => void) {
  if (
    typeof window === "undefined" ||
    typeof window.matchMedia !== "function"
  ) {
    return () => undefined;
  }
  const media = window.matchMedia(COMPACT_QUERY);
  media.addEventListener("change", onStoreChange);
  return () => media.removeEventListener("change", onStoreChange);
}

function getSnapshot() {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia(COMPACT_QUERY).matches
  );
}

/**
 * `true` at or below 860px — the compact / one-pane band (DESIGN.md §9).
 *
 * §9 forbids JS breakpoint state for *layout*, and that has not changed: every
 * pane, grid and reflow in Journiv is still CSS. This hook exists for the one
 * thing CSS cannot express — which *primitive* an adaptive overlay mounts
 * (Drawer vs Dialog / AlertDialog / DropdownMenu). A CSS-only switch would need
 * both trees mounted with one hidden, duplicating every form control,
 * accessible name and `useId()` inside the overlay.
 *
 * Only the three adaptive overlays in `src/components/journiv/` may call this.
 * Feature code must never ask how wide the window is.
 */
export function useCompactViewport(): boolean {
  // The snapshot is a boolean, so useSyncExternalStore's identity check is
  // stable even though matchMedia returns a fresh MediaQueryList each call.
  return useSyncExternalStore(subscribe, getSnapshot, () => false);
}
