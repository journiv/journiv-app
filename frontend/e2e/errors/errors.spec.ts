import { expect, test } from "../fixtures/test";

test.describe("error states", () => {
  test("a timeline query failure shows an actionable error state", async ({
    page,
  }) => {
    await page.route("**/api/v1/moments?**", async (route) => {
      await route.fulfill({ status: 500 });
    });

    await page.goto("/timeline");

    const timeline = page.getByRole("region", { name: "Timeline" });
    const error = timeline.getByRole("alert");
    await expect(error).toBeVisible();
    await expect(
      error.getByText("Moments could not be loaded", { exact: true }),
    ).toBeVisible();
    await expect(
      error.getByRole("button", { name: "Try again" }),
    ).toBeVisible();
  });

  test("a failed entry save keeps the writing visible and offers a retry", async ({
    page,
    data,
  }) => {
    const journal = await data.journal();
    const moment = await data.moment({ journalId: journal.id });
    const body = data.label("Writing kept after failed save");

    await page.route(`**/api/v1/moments/${moment.id}`, async (route) => {
      if (route.request().method() === "PUT") {
        await route.fulfill({ status: 500 });
        return;
      }
      await route.continue();
    });

    await page.goto(`/timeline/${moment.id}/edit`);
    const editor = page.getByRole("textbox", { name: "Entry body" });
    await editor.click();
    await page.keyboard.press("ControlOrMeta+A");
    await page.keyboard.type(body);
    await page.getByRole("button", { name: "Done" }).click();

    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
    await expect(editor).toContainText(body);
  });
});
