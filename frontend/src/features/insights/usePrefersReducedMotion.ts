import { useSyncExternalStore } from "react";

const QUERY = "(prefers-reduced-motion: reduce)";

function subscribe(onStoreChange: () => void) {
  if (
    typeof window === "undefined" ||
    typeof window.matchMedia !== "function"
  ) {
    return () => undefined;
  }
  const media = window.matchMedia(QUERY);
  media.addEventListener("change", onStoreChange);
  return () => media.removeEventListener("change", onStoreChange);
}

function getSnapshot() {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia(QUERY).matches
  );
}

/**
 * `true` when the viewer asked for reduced motion. Used to turn off the Recharts
 * entry animation — DESIGN.md requires honouring reduced motion and adding no
 * decorative animation. This is an accessibility preference, not a layout
 * breakpoint, so it does not fall under the "feature code never measures the
 * viewport" rule.
 */
export function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot, () => true);
}
