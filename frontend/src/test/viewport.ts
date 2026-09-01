/**
 * A `matchMedia` that answers from a width the test controls.
 *
 * jsdom implements no layout, so its own `matchMedia` reports `matches: false`
 * for every query and never fires a change event. That is fine until something
 * *chooses behaviour* from a media query — the adaptive overlays (DESIGN.md §9)
 * pick their primitive from `(max-width: 860px)`, and Settings picks its
 * presentation from `(min-width: 1101px)`. Against the stock stub those tests
 * silently only ever exercise one branch.
 *
 * Installed by `src/test/setup.ts` for every test file. Width queries are
 * evaluated for real; everything else (`prefers-color-scheme`, …) stays
 * unmatched, as it was before.
 */

/** Every test file starts here — the desktop band (DESIGN.md §9, > 1100px). */
export const DEFAULT_TEST_VIEWPORT_WIDTH = 1440;

let width = DEFAULT_TEST_VIEWPORT_WIDTH;
const targets = new Set<EventTarget>();

function evaluate(query: string): boolean {
  const max = query.match(/\(max-width:\s*(\d+)px\)/);
  if (max) return width <= Number(max[1]);
  const min = query.match(/\(min-width:\s*(\d+)px\)/);
  if (min) return width >= Number(min[1]);
  return false;
}

/**
 * Sets the width every `matchMedia` query is evaluated against, and notifies
 * live listeners. Wrap in `act(...)` when a mounted component observes it:
 *
 *     act(() => setTestViewportWidth(390));   // compact — the Drawer branch
 */
export function setTestViewportWidth(next: number) {
  width = next;
  for (const target of targets) target.dispatchEvent(new Event("change"));
}

/** Restores the desktop default. Called from the global `afterEach`. */
export function resetTestViewportWidth() {
  width = DEFAULT_TEST_VIEWPORT_WIDTH;
}

export function installMatchMediaStub() {
  Object.defineProperty(globalThis, "matchMedia", {
    configurable: true,
    value: (query: string) => {
      const target = new EventTarget();
      targets.add(target);
      return {
        get matches() {
          return evaluate(query);
        },
        media: query,
        onchange: null,
        addEventListener: (type: string, listener: EventListener) =>
          target.addEventListener(type, listener),
        removeEventListener: (type: string, listener: EventListener) =>
          target.removeEventListener(type, listener),
        addListener: (listener: EventListener) =>
          target.addEventListener("change", listener),
        removeListener: (listener: EventListener) =>
          target.removeEventListener("change", listener),
        dispatchEvent: (event: Event) => target.dispatchEvent(event),
      };
    },
  });
}
