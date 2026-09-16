import { describe, expect, it } from "vitest";
import { createAppRouter } from "../router";
import { manifestShortcuts } from "./manifestShortcuts";

describe("manifestShortcuts", () => {
  it("every shortcut url resolves to a real, static route", () => {
    const router = createAppRouter();

    for (const shortcut of manifestShortcuts) {
      const matches = router.matchRoutes(shortcut.url);
      // An unmatched path resolves only to __root__; a path that only hits a
      // dynamic segment (e.g. a future rename shadowed by /timeline/$momentId)
      // is not the static route the shortcut is meant to open.
      expect(
        matches.length,
        `${shortcut.url} did not match any route beyond __root__`,
      ).toBeGreaterThan(1);
      const deepestRouteId = matches[matches.length - 1]?.routeId;
      expect(
        deepestRouteId,
        `${shortcut.url} resolved to a dynamic route (${deepestRouteId}), not a static one`,
      ).not.toMatch(/\$/);
    }
  });

  it("does not include a Quick Log shortcut", () => {
    expect(
      manifestShortcuts.some((shortcut) =>
        shortcut.name.toLowerCase().includes("quick log"),
      ),
    ).toBe(false);
  });
});
