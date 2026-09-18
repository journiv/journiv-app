import { describe, expect, it } from "vitest";
import { createAppRouter } from ".";

/**
 * `defaultPreload: "intent"` only prefetches a chunk if TanStack Router finds
 * a `.preload()` on `route.options.component` (checked by
 * `@tanstack/router-core`'s `preloadRoute`, not by this app). Plain
 * `React.lazy` has no such static property, which is exactly why hovering a
 * sidebar `<Link>` prefetched nothing before this change. These tests check
 * the wiring is reachable and functional; the actual hover-triggered network
 * request needs a real browser (e2e/README.md), not Vitest+JSDOM.
 */
describe("route preload wiring", () => {
  it("exposes .preload() on every lazily-loaded route's component, reachable by path", () => {
    const router = createAppRouter();
    const paths = [
      "/journals",
      "/timeline/$momentId",
      "/timeline/new",
      "/library/tags",
      "/library/tags/$tagId",
      "/library/prompts",
      "/insights",
      "/settings/journaling/people",
      "/settings/journaling/moods",
      "/settings/journaling/activities",
      "/settings/journaling/goals",
    ] as const;
    for (const path of paths) {
      const route = router.routesByPath[path];
      expect(route, `route not found: ${path}`).toBeTruthy();
      const preload = route?.options.component?.preload;
      expect(preload, `.preload missing for ${path}`).toBeTypeOf("function");
    }
  });

  it("calling .preload() resolves the underlying dynamic import", async () => {
    const router = createAppRouter();
    const route = router.routesByPath["/library/tags"];
    await expect(route?.options.component?.preload?.()).resolves.toBeFalsy();
  });
});
