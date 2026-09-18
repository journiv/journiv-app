import {
  deleteCurrentUserApiV1UsersMeDelete,
  loginApiV1AuthLoginPost,
} from "@/api/generated";
import { runId } from "../env";
import { createJournivClient } from "../fixtures/api";
import { expect, test } from "../fixtures/test";

test.describe("authentication journeys", () => {
  test.describe("signed out", () => {
    test.use({ session: "none" });

    test("invalid credentials show the sign-in error and stay on login", async ({
      page,
      journivUser,
    }) => {
      await page.goto("/login");

      await page.getByLabel("Email").fill(journivUser.email);
      await page
        .getByLabel("Password")
        .fill(`${journivUser.password}-incorrect`);
      await page.getByRole("button", { name: "Sign in" }).click();

      await expect(page).toHaveURL((url) => url.pathname === "/login");
      await expect(page.getByRole("alert")).toHaveText(
        "Sign in failed. Check your email and password.",
      );
    });

    test("signing in from a deep link returns to the requested page", async ({
      page,
      data,
      journivUser,
    }) => {
      const journal = await data.journal();
      const title = data.label("Deep link entry");
      const moment = await data.moment({ journalId: journal.id, title });
      const requestedPath = `/timeline/${moment.id}`;

      await page.goto(`${requestedPath}?q=remember`);
      await expect(page).toHaveURL((url) => url.pathname === "/login");

      await page.getByLabel("Email").fill(journivUser.email);
      await page.getByLabel("Password").fill(journivUser.password);
      await page.getByRole("button", { name: "Sign in" }).click();

      await expect(page).toHaveURL(
        (url) =>
          url.pathname === requestedPath &&
          url.searchParams.get("q") === "remember",
      );
      await expect(page.getByRole("heading", { name: title })).toBeVisible();
    });

    test("a user created through sign up is signed in on the timeline", async ({
      page,
    }, testInfo) => {
      const email = `e2e-signup-${runId()}-w${testInfo.workerIndex}@example.com`;
      const password = `E2e-signup-${runId()}-Aa1`;
      let accessToken: string | undefined;

      try {
        await page.goto("/signup");

        await page.getByLabel("Name").fill("E2E Signup User");
        await page.getByLabel("Email").fill(email);
        await page.getByLabel("Password", { exact: true }).fill(password);
        await page.getByLabel("Confirm password").fill(password);
        await page.getByRole("button", { name: "Create account" }).click();

        await expect(page).toHaveURL((url) => url.pathname === "/timeline");
        await expect(
          page.getByRole("button", { name: "Log out" }),
        ).toBeVisible();

        // The signed-in proof above is the URL and the Log out button, not a
        // token: the access token now lives only in an in-memory variable
        // inside session.ts, unreachable from the browser's storage
        // (docs/features/authentication.md). A follow-up API login with the
        // same credentials gets a token for the cleanup delete below,
        // independent of whatever the page itself is holding.
        const logIn = await loginApiV1AuthLoginPost({
          client: createJournivClient(),
          body: { email, password },
        });
        if (logIn.error === undefined && logIn.data)
          accessToken = logIn.data.access_token;
      } finally {
        if (accessToken) {
          const deleted = await deleteCurrentUserApiV1UsersMeDelete({
            client: createJournivClient(accessToken),
          });
          if (deleted.error !== undefined) {
            console.warn(
              `[e2e] Could not delete the UI-created signup account (HTTP ${deleted.response?.status}).`,
            );
          }
        }
      }
    });

    test("sign up shows the disabled state from instance config", async ({
      page,
    }) => {
      // SignUpPage renders this state from instance config. Fetching the real
      // response and overriding one field keeps the intercepted schema honest.
      await page.route("**/api/v1/instance/config", async (route) => {
        const response = await route.fetch();
        const config = await response.json();
        await route.fulfill({ json: { ...config, disable_signup: true } });
      });

      await page.goto("/signup");

      await expect(
        page.getByRole("heading", { name: "Sign up is disabled" }),
      ).toBeVisible();
      await expect(
        page.getByRole("link", { name: "Return to sign in" }),
      ).toBeVisible();
    });
  });

  test("signing out returns to login and keeps a protected route unreachable", async ({
    page,
  }) => {
    await page.goto("/timeline");
    await page.getByRole("button", { name: "Log out" }).click();

    await expect(page).toHaveURL((url) => url.pathname === "/login");
    await expect(
      page.getByRole("heading", { name: "Welcome back" }),
    ).toBeVisible();
    expect(
      await page.evaluate(() =>
        localStorage.getItem("journiv.session-hint.v1"),
      ),
    ).toBeNull();

    // The fixture init script runs again for a reload. If refresh is
    // unreachable, it must not recreate the hint that logout removed and
    // misclassify this tab as an offline authenticated session.
    await page.route("**/api/v1/auth/refresh", (route) => route.abort());
    await page.reload();
    await expect(
      page.getByRole("heading", { name: "Welcome back" }),
    ).toBeVisible();
    expect(
      await page.evaluate(() =>
        localStorage.getItem("journiv.session-hint.v1"),
      ),
    ).toBeNull();

    // Back asks the client router to revisit /timeline in the same document,
    // after the logout action has cleared its session. The route guard must
    // send that attempt straight back to the login screen.
    await page.goBack();
    await expect(page).toHaveURL((url) => url.pathname === "/login");
    await expect(
      page.getByRole("heading", { name: "Welcome back" }),
    ).toBeVisible();
  });
});
