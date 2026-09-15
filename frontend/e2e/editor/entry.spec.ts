import { freezeClock } from "../fixtures/determinism";
import { expect, test } from "../fixtures/test";
import { VIEWPORTS } from "../viewports";

test.describe("entry journeys", () => {
  test("writing a new entry and saving it shows it on the timeline", {
    tag: "@smoke",
  }, async ({ page, data }) => {
    const journal = await data.journal();
    const title = data.label("New entry");
    const body = data.label("A newly saved memory");

    await page.goto(`/journals/${journal.id}/new`);
    await page.getByLabel("Entry title").fill(title);
    const editor = page.getByRole("textbox", { name: "Entry body" });
    await editor.click();
    await page.keyboard.type(body);

    const created = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname === "/api/v1/moments",
    );
    await page.getByRole("button", { name: "Done", exact: true }).click();
    await created;

    await expect(page.getByRole("heading", { name: title })).toBeVisible();
    await expect(
      page.getByLabel("Entry content").getByText(body, { exact: true }),
    ).toBeVisible();

    await page.goto("/timeline");
    const timeline = page.getByRole("region", { name: "Timeline" });
    await expect(timeline.getByRole("link", { name: title })).toBeVisible();

    await page.reload();
    await expect(timeline.getByRole("link", { name: title })).toBeVisible();
  });

  test("editing an existing entry persists across a reload", async ({
    page,
    data,
  }) => {
    const journal = await data.journal();
    const moment = await data.moment({
      journalId: journal.id,
      title: data.label("Original entry"),
      body: data.label("Original body"),
    });
    const editedTitle = data.label("Edited entry");
    const editedBody = data.label("Edited body");

    await page.goto(`/timeline/${moment.id}`);
    await page.getByRole("button", { name: "Edit" }).click();

    await page.getByLabel("Entry title").fill(editedTitle);
    const editor = page.getByRole("textbox", { name: "Entry body" });
    await editor.click();
    await page.keyboard.press("ControlOrMeta+A");
    await page.keyboard.type(editedBody);

    const updated = page.waitForResponse(
      (response) =>
        response.request().method() === "PUT" &&
        new URL(response.url()).pathname === `/api/v1/moments/${moment.id}`,
    );
    await page.getByRole("button", { name: "Done", exact: true }).click();
    await updated;

    await expect(
      page.getByRole("heading", { name: editedTitle }),
    ).toBeVisible();
    await expect(
      page.getByLabel("Entry content").getByText(editedBody, { exact: true }),
    ).toBeVisible();

    await page.reload();
    await expect(
      page.getByRole("heading", { name: editedTitle }),
    ).toBeVisible();
    await expect(
      page.getByLabel("Entry content").getByText(editedBody, { exact: true }),
    ).toBeVisible();
  });

  test("clicking below short prose continues writing at the end", async ({
    page,
    data,
  }) => {
    const journal = await data.journal();
    const body = data.label("Short entry");
    const moment = await data.moment({ journalId: journal.id, body });

    await page.goto(`/timeline/${moment.id}/edit`);
    const editor = page.getByRole("textbox", { name: "Entry body" });
    await expect(editor).toBeVisible();

    const box = await editor.boundingBox();
    expect(box).not.toBeNull();
    expect(box?.height).toBeGreaterThanOrEqual(VIEWPORTS.desktop.height * 0.5);

    await editor.click({
      position: { x: 16, y: (box?.height ?? 0) - 16 },
    });
    await page.keyboard.type(" continued below");

    await expect(editor).toContainText(`${body} continued below`);
  });

  test("deleting an entry removes an entry-only moment from the timeline", async ({
    page,
    data,
  }) => {
    const journal = await data.journal();
    const title = data.label("Deleted entry");
    const moment = await data.moment({ journalId: journal.id, title });

    await page.goto(`/timeline/${moment.id}`);
    await page.getByRole("button", { name: "Entry actions" }).click();
    await page.getByRole("menuitem", { name: "Delete entry…" }).click();
    const dialog = page.getByRole("alertdialog");
    await expect(
      dialog.getByRole("heading", { name: `Delete “${title}”?` }),
    ).toBeVisible();

    const deleted = page.waitForResponse(
      (response) =>
        response.request().method() === "DELETE" &&
        new URL(response.url()).pathname ===
          `/api/v1/entries/${moment.entry?.id}`,
    );
    await dialog.getByRole("button", { name: "Delete entry" }).click();
    await deleted;

    await expect(page).toHaveURL((url) => url.pathname === "/timeline");
    const timeline = page.getByRole("region", { name: "Timeline" });
    await expect(timeline.getByRole("link", { name: title })).toHaveCount(0);
    await page.reload();
    await expect(timeline.getByRole("link", { name: title })).toHaveCount(0);
  });

  test("deleting writing preserves the Moment and its logged details", async ({
    page,
    data,
  }) => {
    const journal = await data.journal();
    const title = data.label("Entry with details");
    const tag = data.label("kept tag");
    const moment = await data.moment({ journalId: journal.id, title });
    await data.tags(moment.id, [tag]);

    await page.goto(`/timeline/${moment.id}`);
    await page.getByRole("button", { name: "Entry actions" }).click();
    await page.getByRole("menuitem", { name: "Delete entry…" }).click();
    const deleted = page.waitForResponse(
      (response) =>
        response.request().method() === "DELETE" &&
        new URL(response.url()).pathname ===
          `/api/v1/entries/${moment.entry?.id}`,
    );
    await page
      .getByRole("alertdialog")
      .getByRole("button", { name: "Delete entry" })
      .click();
    await deleted;

    await expect(page).toHaveURL(
      (url) => url.pathname === `/timeline/${moment.id}`,
    );
    await expect(
      page.getByRole("button", { name: "Write", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("region", { name: "Tags" }).getByText(tag),
    ).toBeVisible();

    await page.reload();
    await expect(
      page.getByRole("button", { name: "Write", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("region", { name: "Tags" }).getByText(tag),
    ).toBeVisible();
  });

  test("changing an entry date moves it to yesterday's timeline group", async ({
    page,
    data,
  }) => {
    await freezeClock(page);
    const journal = await data.journal();
    const title = data.label("Moved date entry");
    const moment = await data.moment({ journalId: journal.id, title });

    await page.goto(`/timeline/${moment.id}/edit`);
    await page
      .getByRole("button", { name: "Change entry date and time" })
      .click();

    const calendar = page.getByRole("grid");
    const yesterday = calendar.getByRole("button").filter({ hasText: /^16$/ });
    const changed = page.waitForResponse(
      (response) =>
        response.request().method() === "PUT" &&
        new URL(response.url()).pathname === `/api/v1/moments/${moment.id}`,
    );
    await yesterday.click();
    await changed;

    await page.goto("/timeline");
    const timeline = page.getByRole("region", { name: "Timeline" });
    await expect(
      timeline.getByRole("heading", { name: "Yesterday" }),
    ).toBeVisible();
    await expect(timeline.getByRole("link", { name: title })).toBeVisible();
  });

  test("moving an entry to another journal shows it in the new journal", async ({
    page,
    data,
  }) => {
    const source = await data.journal({ title: data.label("Source journal") });
    const destination = await data.journal({
      title: data.label("Destination journal"),
    });
    const title = data.label("Moved journal entry");
    const moment = await data.moment({ journalId: source.id, title });

    await page.goto(`/timeline/${moment.id}/edit`);
    await page
      .getByRole("combobox", { name: "Journal", exact: true })
      .selectOption({ label: destination.title });

    const moved = page.waitForResponse(
      (response) =>
        response.request().method() === "PUT" &&
        new URL(response.url()).pathname === `/api/v1/moments/${moment.id}`,
    );
    await page.getByRole("button", { name: "Done", exact: true }).click();
    await moved;

    await page.goto(`/journals/${destination.id}`);
    const destinationTimeline = page.getByRole("region", { name: "Timeline" });
    await expect(
      destinationTimeline.getByRole("heading", { name: destination.title }),
    ).toBeVisible();
    await expect(
      destinationTimeline.getByRole("link", { name: title }),
    ).toBeVisible();

    await page.reload();
    await expect(
      destinationTimeline.getByRole("link", { name: title }),
    ).toBeVisible();

    await page.goto(`/journals/${source.id}`);
    await expect(
      page
        .getByRole("region", { name: "Timeline" })
        .getByRole("link", { name: title }),
    ).toHaveCount(0);
  });

  test("formatting round-trips through save and reload", async ({
    page,
    data,
  }) => {
    const journal = await data.journal();
    const title = data.label("Formatted entry");
    const boldText = data.label("Bold memory");
    const italicText = data.label("Italic memory");
    const firstItem = data.label("First list item");
    const secondItem = data.label("Second list item");
    const taskItem = data.label("Task item");
    const nestedItem = data.label("Nested item");

    await page.goto(`/journals/${journal.id}/new`);
    await page.getByLabel("Entry title").fill(title);
    const editor = page.getByRole("textbox", { name: "Entry body" });
    await editor.click();

    await page.getByRole("button", { name: "Bold" }).click();
    await page.keyboard.type(boldText);
    await page.getByRole("button", { name: "Bold" }).click();
    await page.keyboard.press("Enter");

    await page.getByRole("button", { name: "Italic" }).click();
    await page.keyboard.type(italicText);
    await page.getByRole("button", { name: "Italic" }).click();
    await page.keyboard.press("Enter");

    await page.getByRole("button", { name: "Bullet list" }).click();
    await page.keyboard.type(firstItem);
    await page.keyboard.press("Enter");
    await page.keyboard.type(secondItem);
    await page.keyboard.press("Enter");
    await page.keyboard.press("Enter");

    await page.getByRole("button", { name: "Checklist" }).click();
    await page.keyboard.type(taskItem);
    await page.keyboard.press("Enter");
    await page.getByRole("button", { name: "Indent list item" }).click();
    await page.keyboard.type(nestedItem);

    await expect(
      page.getByRole("button", {
        name: /^Unsaved\. Saved on this device, not in your journal yet\./,
      }),
    ).toBeVisible();
    await expect(page).toHaveURL((url) =>
      Boolean(url.searchParams.get("draft")),
    );
    await page.getByRole("button", { name: "Done", exact: true }).click();
    await expect(page).toHaveURL(
      (url) =>
        url.pathname.startsWith(`/journals/${journal.id}/`) &&
        !url.pathname.endsWith("/new"),
    );

    const reader = page.getByLabel("Entry content");
    await expect(reader.getByRole("strong")).toHaveText(boldText);
    await expect(reader.getByRole("emphasis")).toHaveText(italicText);
    const list = reader.getByRole("list").first();
    await expect(
      list.getByRole("listitem").filter({ hasText: firstItem }),
    ).toBeVisible();
    await expect(
      list.getByRole("listitem").filter({ hasText: secondItem }),
    ).toBeVisible();
    // The task line renders as a checklist row; the nested line indents.
    await expect(
      reader.locator('li[data-list="unchecked"]').filter({ hasText: taskItem }),
    ).toBeVisible();
    await expect(reader.locator("li.ql-indent-1")).toHaveText(nestedItem);

    await page.reload();
    await expect(
      page.getByLabel("Entry content").getByRole("strong"),
    ).toHaveText(boldText);
    await expect(
      page.getByLabel("Entry content").getByRole("emphasis"),
    ).toHaveText(italicText);
    await expect(
      page
        .getByLabel("Entry content")
        .getByRole("list")
        .first()
        .getByRole("listitem")
        .filter({ hasText: firstItem }),
    ).toBeVisible();
    await expect(
      page
        .getByLabel("Entry content")
        .locator('li[data-list="unchecked"]')
        .filter({ hasText: taskItem }),
    ).toBeVisible();
    await expect(
      page.getByLabel("Entry content").locator("li.ql-indent-1"),
    ).toHaveText(nestedItem);
  });
});

test.describe("mobile editor", () => {
  test.use({ viewport: VIEWPORTS.mobile });

  test("the toolbar is reachable and text entry works at mobile width", async ({
    page,
    data,
  }) => {
    const journal = await data.journal();
    const title = data.label("Mobile entry");
    const body = data.label("Written on mobile");

    await page.goto(`/journals/${journal.id}/new`);
    await page.getByLabel("Entry title").fill(title);

    const toolbar = page.getByRole("toolbar", { name: "Editor actions" });
    await expect(toolbar).toBeVisible();
    const bold = toolbar.getByRole("button", { name: "Bold" });
    await expect(bold).toBeVisible();

    const editor = page.getByRole("textbox", { name: "Entry body" });
    await editor.click();
    await bold.click();
    await expect(bold).toHaveAttribute("aria-pressed", "true");
    await page.keyboard.type(body);

    await expect(editor).toContainText(body);
    await expect(
      page.getByRole("button", {
        name: /^Unsaved\. Saved on this device, not in your journal yet\./,
      }),
    ).toBeVisible();
    await expect(page).toHaveURL((url) =>
      Boolean(url.searchParams.get("draft")),
    );

    await page.getByRole("button", { name: "Done", exact: true }).click();
    await expect(page).toHaveURL(
      (url) =>
        url.pathname.startsWith(`/journals/${journal.id}/`) &&
        !url.pathname.endsWith("/new"),
    );
    await expect(
      page.getByLabel("Entry content").getByRole("strong"),
    ).toHaveText(body);
  });
});
