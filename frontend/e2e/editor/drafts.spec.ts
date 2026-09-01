import { expect, test } from "../fixtures/test";

test.describe("local editor drafts", () => {
  test("an unsaved draft is recovered after an accidental reload", async ({
    page,
    data,
  }) => {
    const journal = await data.journal();
    const title = data.label("Recovered draft");
    const body = data.label("Writing that survived the reload");

    await page.goto(`/journals/${journal.id}/new`);
    await page.getByLabel("Entry title").fill(title);
    const editor = page.getByRole("textbox", { name: "Entry body" });
    await editor.click();
    await page.keyboard.type(body);

    await expect(
      page
        .getByRole("status")
        .filter({ hasText: "Saved locally · not in your journal yet" }),
    ).toBeVisible();
    await expect(page).toHaveURL((url) =>
      Boolean(url.searchParams.get("draft")),
    );

    page.once("dialog", (dialog) => void dialog.accept());
    await page.reload();

    await expect(
      page.getByText("You have writing that was never saved", { exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Recover" }).click();

    await expect(page.getByLabel("Entry title")).toHaveValue(title);
    await expect(
      page.getByRole("textbox", { name: "Entry body" }),
    ).toContainText(body);
  });
});
