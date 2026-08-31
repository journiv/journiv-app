import { expect, test } from "../fixtures/test";

/** The smoke suite: does the application fundamentally work?
 *
 *  These three tests are the foundation's own proof. Each one covers a distinct
 *  piece of infrastructure, and if any fails, no other spec in the repo can be
 *  trusted — so they run first, in CI, on every dispatch.
 */
test.describe("authentication", { tag: "@smoke" }, () => {
  test.describe("signed out", () => {
    test.use({ session: "none" });

    // Proves: routing, the `beforeLoad` guard, and that semantic locators find
    // the real UI. Needs no session, so it isolates the guard from auth.
    test("a protected route sends an anonymous visitor to sign in", async ({
      page,
    }) => {
      await page.goto("/timeline");

      await expect(page).toHaveURL(/\/login\?/);
      await expect(
        page.getByRole("heading", { name: "Welcome back" }),
      ).toBeVisible();
      // The guard must preserve the destination, or every deep link breaks.
      expect(new URL(page.url()).searchParams.get("returnTo")).toContain(
        "/timeline",
      );
    });

    // Proves: the backend is real, the worker account the fixtures created can
    // actually sign in, and the login form works end to end.
    test("valid credentials sign the user in", async ({
      page,
      journivUser,
    }) => {
      await page.goto("/login");

      await page.getByLabel("Email").fill(journivUser.email);
      await page.getByLabel("Password").fill(journivUser.password);
      await page.getByRole("button", { name: "Sign in" }).click();

      await expect(page).toHaveURL(/\/timeline/);
    });
  });

  // Proves the single most load-bearing piece of this framework: the injected
  // sessionStorage session. Every authenticated spec in the repo depends on it,
  // and nothing else would tell us if SESSION_STORAGE_KEY drifted from the app.
  test("an injected session starts the app signed in", async ({ page }) => {
    await page.goto("/timeline");

    await expect(page).toHaveURL(/\/timeline/);
    await expect(page).not.toHaveURL(/\/login/);
  });
});
