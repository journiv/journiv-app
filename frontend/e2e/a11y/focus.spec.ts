import { expect, test } from "../fixtures/test";

test.describe("accessibility behaviours", () => {
  test("opening a dialog moves focus into it and closing restores its trigger", async ({
    page,
    data,
  }) => {
    const journal = await data.journal();
    const title = data.label("Dialog entry");
    const moment = await data.moment({ journalId: journal.id, title });
    await page.goto(`/timeline/${moment.id}`);

    const trigger = page.getByRole("button", { name: "Delete entry" });
    await trigger.focus();
    await expect(trigger).toBeFocused();

    await page.keyboard.press("Enter");

    const dialog = page.getByRole("dialog", { name: `Delete “${title}”?` });
    await expect(dialog.getByRole("button", { name: "Cancel" })).toBeFocused();

    await page.keyboard.press("Escape");

    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
  });

  test("a new entry can be written and saved with the keyboard alone", async ({
    page,
    data,
  }) => {
    await data.journal();
    const title = data.label("Keyboard entry");
    const body = data.label("Written without a pointer");

    await page.goto("/timeline");

    const newEntry = page.getByRole("button", { name: "New entry" });
    await newEntry.focus();
    await expect(newEntry).toBeFocused();
    await page.keyboard.press("Enter");

    await expect(page).toHaveURL((url) => url.pathname === "/timeline/new");

    const entryTitle = page.getByLabel("Entry title");
    await entryTitle.focus();
    await expect(entryTitle).toBeFocused();
    await page.keyboard.type(title);

    const editor = page.getByRole("textbox", { name: "Entry body" });
    await editor.focus();
    await expect(editor).toBeFocused();
    await page.keyboard.type(body);

    const created = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname === "/api/v1/moments",
    );
    await page.keyboard.press("ControlOrMeta+S");
    await created;

    await expect(page.getByRole("heading", { name: title })).toBeVisible();
    await expect(
      page.getByLabel("Entry content").getByText(body, { exact: true }),
    ).toBeVisible();
  });
});
