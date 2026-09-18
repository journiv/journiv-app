import { expect, test } from "../fixtures/test";

/**
 * registerType: "prompt" means a waiting worker never takes over on its own
 * (vite.config.ts, docs/features/pwa.md) -- clientsClaim/skipWaiting are both
 * false.
 *
 * A genuine "second build is waiting" scenario needs two different `dist/`
 * outputs served in sequence, which this harness does not attempt to stand
 * up -- it would be a second, fragile build pipeline for one spec. The
 * update-bar-appears / confirm-before-restart-when-dirty interaction is
 * instead covered deterministically at the unit level
 * (src/features/shell/UpdateBar.test.tsx), where virtual:pwa-register is
 * mocked and the worker lifecycle is simulated directly. What this suite can
 * honestly prove end-to-end against a real worker is the negative: nothing
 * appears, and nothing reloads, when no update is waiting.
 */
test.describe("update bar", () => {
  test("does not appear, and never auto-reloads, when no update is waiting", async ({
    page,
  }) => {
    await page.goto("/timeline");
    await expect(page.getByRole("button", { name: "New entry" })).toBeVisible();
    await expect(page.getByText(/new version of journiv/i)).toBeHidden();

    // A full reload replaces the whole document, so a marker set on `window`
    // cannot survive one. Ordinary SPA route changes (pushState) leave it
    // untouched, which is why this is a more honest "did not reload" signal
    // than counting Playwright's framenavigated events -- those fire on
    // in-app route settling too.
    await page.evaluate(() => {
      (
        window as unknown as { __pwaNoReloadMarker: number }
      ).__pwaNoReloadMarker = Date.now();
    });

    // Give a real registration a moment to settle and confirm it stays quiet.
    await page.waitForTimeout(2000);
    await expect(page.getByText(/new version of journiv/i)).toBeHidden();

    const markerSurvived = await page.evaluate(
      () =>
        (window as unknown as { __pwaNoReloadMarker?: number })
          .__pwaNoReloadMarker !== undefined,
    );
    expect(markerSurvived).toBe(true);
  });
});
