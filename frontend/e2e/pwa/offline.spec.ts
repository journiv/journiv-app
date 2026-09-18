import { expect, test } from "../fixtures/test";
import { waitForActiveServiceWorker } from "./support";

/**
 * `context.setOffline()` only blocks real network requests; it does not
 * change `navigator.onLine` or fire the `online`/`offline` DOM events a real
 * OS-level connectivity change would (verified empirically while building
 * this suite). The reconnect-upgrade test below dispatches a synthetic
 * `online` event for that reason -- it is standing in for what a real
 * device's network stack would fire on its own.
 */

test.describe("offline", () => {
  test("an offline reload still boots the shell", async ({ page }) => {
    await page.goto("/timeline");
    await waitForActiveServiceWorker(page);
    await expect(page.getByRole("button", { name: "New entry" })).toBeVisible();

    await page.context().setOffline(true);
    await page.reload();

    await expect(page).toHaveURL(/\/timeline/);
    await expect(page.getByText(/you.?re offline/i)).toBeVisible();
  });

  test("a previously read moment stays readable offline, and mutations are honestly disabled", async ({
    page,
    data,
  }) => {
    const journal = await data.journal();
    const title = data.label("Offline read");
    const moment = await data.moment({
      journalId: journal.id,
      title,
      body: "Read me offline.",
    });

    // Read it once online so it enters the bounded offline cache
    // (persistedQueries.ts's allowlist -- src/app/offline/).
    await page.goto(`/timeline/${moment.id}`);
    await waitForActiveServiceWorker(page);
    await expect(page.getByRole("heading", { name: title })).toBeVisible();
    // The persister throttles writes (default 1s).
    await page.waitForTimeout(1500);

    await page.context().setOffline(true);
    await page.reload();

    await expect(page.getByText(/you.?re offline/i)).toBeVisible();
    await expect(page.getByRole("heading", { name: title })).toBeVisible();
    await expect(
      page.getByRole("button", { name: "New entry" }),
    ).toBeDisabled();
  });

  test("reconnecting upgrades the session in place, no reload", async ({
    page,
  }) => {
    await page.goto("/timeline");
    await waitForActiveServiceWorker(page);
    await expect(page.getByRole("button", { name: "New entry" })).toBeVisible();

    await page.context().setOffline(true);
    await page.reload();
    await expect(page.getByText(/you.?re offline/i)).toBeVisible();

    await page.context().setOffline(false);
    await page.evaluate(() => window.dispatchEvent(new Event("online")));

    await expect(page.getByText(/you.?re offline/i)).toBeHidden();
    await expect(page.getByRole("button", { name: "New entry" })).toBeEnabled();
    // No reload happened -- the offline reload above is the only navigation.
    await expect(page).toHaveURL(/\/timeline/);
  });

  test("an offline logout is not silently undone when the network returns", async ({
    page,
  }) => {
    await page.goto("/timeline");
    await expect(page.getByRole("button", { name: "New entry" })).toBeVisible();

    await page.context().setOffline(true);
    // Logout attempts POST /auth/logout, which fails offline -- the
    // tombstone (journiv.logout-pending.v1) is what stops restore() from
    // silently signing back in once the cookie is reachable again
    // (docs/features/authentication.md, "Logging out when the cookie cannot
    // be deleted").
    await page.getByRole("button", { name: "Log out" }).click();
    await expect(page).toHaveURL(/\/login/);

    await page.context().setOffline(false);
    await page.reload();

    await expect(page).toHaveURL(/\/login/);
    await expect(
      page.getByRole("heading", { name: "Welcome back" }),
    ).toBeVisible();
  });
});
