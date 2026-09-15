import { SKIP_WEB_SERVER } from "../env";
import { expect, test } from "../fixtures/test";
import { waitForActiveServiceWorker } from "./support";

test.describe("service worker", () => {
  test("registers and activates at scope /", async ({ page }) => {
    await page.goto("/timeline");
    await expect(async () => {
      const registrations = await page.evaluate(async () => {
        const list = await navigator.serviceWorker.getRegistrations();
        return list.map((registration) => ({
          scope: registration.scope,
          active: registration.active?.scriptURL,
        }));
      });
      expect(registrations).toContainEqual(
        expect.objectContaining({
          scope: new URL("/", page.url()).href,
          active: expect.stringContaining("/service-worker.js"),
        }),
      );
    }).toPass({ timeout: 10_000 });
  });

  // The single most important assertion in this suite (docs/features/pwa.md):
  // no /api, /media or /pub response may ever enter Cache Storage. Offline
  // reading is a separate, bounded IndexedDB query cache instead.
  test("never puts an authenticated response in Cache Storage", async ({
    page,
    data,
  }) => {
    const journal = await data.journal();
    const moment = await data.moment({
      journalId: journal.id,
      title: data.label("Cache check"),
      body: "Body text.",
    });

    await page.goto("/timeline");
    await waitForActiveServiceWorker(page);

    // clientsClaim is deliberately false, so the page that registered a newly
    // activated worker is not controlled until its next document navigation.
    // Reload before requesting the authenticated Moment, or the cache assertion
    // would never exercise the worker's fetch handler for that request.
    await page.reload();
    await expect
      .poll(() =>
        page.evaluate(() => navigator.serviceWorker.controller !== null),
      )
      .toBe(true);

    await page.goto(`/timeline/${moment.id}`);
    await expect(
      page.getByRole("heading", { name: data.label("Cache check") }),
    ).toBeVisible();

    const paths = await page.evaluate(async () => {
      const names = await caches.keys();
      const entries = await Promise.all(
        names.map(async (name) => {
          const cache = await caches.open(name);
          const requests = await cache.keys();
          return requests.map((request) => new URL(request.url).pathname);
        }),
      );
      return entries.flat();
    });

    // Positive control: an empty/absent cache would make the negative
    // assertion below vacuously true.
    expect(paths.length).toBeGreaterThan(0);
    expect(paths.some((path) => path.startsWith("/assets/"))).toBe(true);
    expect(paths.filter((path) => /^\/(api|media|pub)\//.test(path))).toEqual(
      [],
    );
  });

  test("does not claim /legacy/ navigations -- Flutter still owns its scope", async ({
    page,
  }) => {
    test.skip(
      !SKIP_WEB_SERVER,
      "dual-SPA checks require the FastAPI production frontend server",
    );

    await page.goto("/timeline");
    await waitForActiveServiceWorker(page);

    const response = await page.goto("/legacy/", {
      waitUntil: "domcontentloaded",
    });
    expect(response?.ok()).toBe(true);
    await expect(page.locator("flutter-view")).toBeVisible({
      timeout: 30_000,
    });
  });
});
