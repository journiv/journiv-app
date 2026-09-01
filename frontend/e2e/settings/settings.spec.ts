import { expect, test } from "../fixtures/test";

test.describe("settings", () => {
  test("settings opens as an overlay over the workspace and closes back to it", async ({
    page,
  }) => {
    await page.goto("/timeline");

    const timeline = page.getByRole("region", { name: "Timeline" });
    await expect(timeline).toBeVisible();

    await page.getByRole("button", { name: "Settings" }).click();

    await expect(page).toHaveURL((url) => url.pathname === "/settings/profile");
    await expect(page.getByRole("dialog", { name: "Settings" })).toBeVisible();
    await expect(timeline).toBeVisible();

    await page.getByRole("button", { name: "Close settings" }).click();

    await expect(page).toHaveURL((url) => url.pathname === "/timeline");
    await expect(page.getByRole("dialog", { name: "Settings" })).toHaveCount(0);
    await expect(timeline).toBeVisible();
  });

  test("changing the display name persists across a reload", async ({
    page,
    data,
  }) => {
    const displayName = data.label("Updated display name");

    await page.goto("/settings/profile");
    const name = page.getByLabel("Display name");
    await name.fill(displayName);
    const saved = page.waitForResponse(
      (response) =>
        response.request().method() === "PUT" &&
        new URL(response.url()).pathname === "/api/v1/users/me",
    );
    await page.getByRole("button", { name: "Save changes" }).click();
    await saved;

    await expect(name).toHaveValue(displayName);

    await page.reload();

    await expect(page.getByLabel("Display name")).toHaveValue(displayName);
  });

  test("switching the theme to dark applies it and survives a reload", async ({
    page,
  }) => {
    await page.goto("/timeline");

    const darkTheme = page.getByRole("button", { name: "Dark theme" });
    await darkTheme.click();

    await expect(darkTheme).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("html")).toHaveClass(/dark/);

    await page.reload();

    await expect(
      page.getByRole("button", { name: "Dark theme" }),
    ).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("html")).toHaveClass(/dark/);
  });

  test("changing the password rejects the old password and restores the worker credential", async ({
    page,
    journivUser,
  }) => {
    const changedPassword = "E2e-Changed-Password-1";
    let passwordChanged = false;
    const changePassword = async (
      currentPassword: string,
      newPassword: string,
    ) => {
      await page.getByLabel("Current password").fill(currentPassword);
      await page.getByLabel("New password", { exact: true }).fill(newPassword);
      await page.getByLabel("Confirm new password").fill(newPassword);
      await page.getByRole("button", { name: "Change password" }).click();
      await expect(
        page.getByText("Your password has been changed."),
      ).toBeVisible();
    };

    try {
      await page.goto("/settings/security");
      await changePassword(journivUser.password, changedPassword);
      passwordChanged = true;

      await page.goto("/login");
      await page.getByLabel("Email").fill(journivUser.email);
      await page.getByLabel("Password").fill(journivUser.password);
      await page.getByRole("button", { name: "Sign in" }).click();

      await expect(page.getByRole("alert")).toHaveText(
        "Sign in failed. Check your email and password.",
      );

      await page.getByLabel("Password").fill(changedPassword);
      await page.getByRole("button", { name: "Sign in" }).click();
      await expect(page).toHaveURL((url) => url.pathname === "/timeline");

      await page.goto("/settings/security");
      await changePassword(changedPassword, journivUser.password);
      passwordChanged = false;
    } finally {
      if (passwordChanged) {
        await page.goto("/login");
        await page.getByLabel("Email").fill(journivUser.email);
        await page.getByLabel("Password").fill(changedPassword);
        await page.getByRole("button", { name: "Sign in" }).click();
        await expect(page).toHaveURL((url) => url.pathname === "/timeline");

        await page.goto("/settings/security");
        await changePassword(changedPassword, journivUser.password);
      }
    }
  });
});
