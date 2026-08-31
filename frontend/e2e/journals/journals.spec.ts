import { expect, test } from "../fixtures/test";

test.describe("journal journeys", () => {
  test("creating a journal shows it in the list and navigation after reload", async ({
    page,
    data,
  }) => {
    const title = data.label("Created journal");

    await page.goto("/journals");

    const journalsPane = page.getByRole("region", { name: "Journals" });
    const journalsNavigation = page.getByRole("navigation", {
      name: "Journals",
    });
    await journalsPane
      .getByRole("button", { name: "New journal" })
      .first()
      .click();

    const dialog = page.getByRole("dialog", { name: "New journal" });
    await dialog.getByLabel("Title").fill(title);
    await dialog.getByRole("button", { name: "Create journal" }).click();

    await expect(journalsPane.getByText(title, { exact: true })).toBeVisible();
    await expect(
      journalsNavigation.getByRole("link", { name: title, exact: true }),
    ).toBeVisible();

    await page.reload();

    await expect(journalsPane.getByText(title, { exact: true })).toBeVisible();
    await expect(
      journalsNavigation.getByRole("link", { name: title, exact: true }),
    ).toBeVisible();
  });

  test("renaming a journal persists the new title after reload", async ({
    page,
    data,
  }) => {
    const journal = await data.journal({
      title: data.label("Original journal"),
    });
    const renamedTitle = data.label("Renamed journal");

    await page.goto("/journals");

    const journalsPane = page.getByRole("region", { name: "Journals" });
    await journalsPane
      .getByRole("button", { name: `${journal.title} actions` })
      .click();
    await page.getByRole("menuitem", { name: "Rename" }).click();

    const dialog = page.getByRole("dialog", { name: "Edit journal" });
    await dialog.getByLabel("Title").fill(renamedTitle);
    await dialog.getByRole("button", { name: "Save changes" }).click();

    await expect(
      journalsPane.getByText(renamedTitle, { exact: true }),
    ).toBeVisible();

    await page.reload();

    await expect(
      journalsPane.getByText(renamedTitle, { exact: true }),
    ).toBeVisible();
  });

  test("archiving removes a journal and unarchiving restores it after reload", async ({
    page,
    data,
  }) => {
    const journal = await data.journal({
      title: data.label("Archive journal"),
    });

    await page.goto("/journals");

    const journalsPane = page.getByRole("region", { name: "Journals" });
    const journalsNavigation = page.getByRole("navigation", {
      name: "Journals",
    });
    const journalTitle = journalsPane.getByText(journal.title, { exact: true });
    const navigationLink = journalsNavigation.getByRole("link", {
      name: journal.title,
      exact: true,
    });

    await journalsPane
      .getByRole("button", { name: `${journal.title} actions` })
      .click();
    const archived = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname ===
          `/api/v1/journals/${journal.id}/archive`,
    );
    await page.getByRole("menuitem", { name: "Archive" }).click();
    await archived;

    const archivedDisclosure = journalsPane.getByText(/^Archived \(\d+\)$/);
    await expect(archivedDisclosure).toBeVisible();
    await expect(journalTitle).toBeHidden();
    await expect(navigationLink).toHaveCount(0);

    const journalsReloaded = page.waitForResponse(
      (response) =>
        response.request().method() === "GET" &&
        new URL(response.url()).pathname === "/api/v1/journals/",
    );
    await page.reload();
    await journalsReloaded;

    await expect(archivedDisclosure).toBeVisible();
    await expect(journalTitle).toBeHidden();
    await expect(navigationLink).toHaveCount(0);

    await archivedDisclosure.click();
    const restored = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname ===
          `/api/v1/journals/${journal.id}/unarchive`,
    );
    await journalsPane
      .getByRole("button", { name: `Unarchive ${journal.title}` })
      .click();
    await restored;

    await expect(journalTitle).toBeVisible();
    await expect(navigationLink).toBeVisible();

    const restoredJournalsReloaded = page.waitForResponse(
      (response) =>
        response.request().method() === "GET" &&
        new URL(response.url()).pathname === "/api/v1/journals/",
    );
    await page.reload();
    await restoredJournalsReloaded;

    await expect(journalTitle).toBeVisible();
    await expect(navigationLink).toBeVisible();
  });

  test("deleting a journal removes it after typed confirmation and reload", async ({
    page,
    data,
  }) => {
    const journal = await data.journal({ title: data.label("Delete journal") });

    await page.goto("/journals");

    const journalsPane = page.getByRole("region", { name: "Journals" });
    const journalsNavigation = page.getByRole("navigation", {
      name: "Journals",
    });
    await journalsPane
      .getByRole("button", { name: `${journal.title} actions` })
      .click();
    await page.getByRole("menuitem", { name: "Delete…" }).click();

    const dialog = page.getByRole("dialog", {
      name: `Delete “${journal.title}”?`,
    });
    const deleteButton = dialog.getByRole("button", {
      name: "Delete journal",
    });
    await expect(deleteButton).toBeDisabled();
    await dialog
      .getByLabel(`Type ${journal.title} to confirm`)
      .fill(journal.title);
    await expect(deleteButton).toBeEnabled();

    const deleted = page.waitForResponse(
      (response) =>
        response.request().method() === "DELETE" &&
        new URL(response.url()).pathname === `/api/v1/journals/${journal.id}`,
    );
    await deleteButton.click();
    await deleted;

    await expect(
      journalsPane.getByText(journal.title, { exact: true }),
    ).toHaveCount(0);
    await expect(
      journalsNavigation.getByRole("link", {
        name: journal.title,
        exact: true,
      }),
    ).toHaveCount(0);

    const journalsReloaded = page.waitForResponse(
      (response) =>
        response.request().method() === "GET" &&
        new URL(response.url()).pathname === "/api/v1/journals/",
    );
    await page.reload();
    await journalsReloaded;

    await expect(
      journalsPane.getByText(journal.title, { exact: true }),
    ).toHaveCount(0);
    await expect(
      journalsNavigation.getByRole("link", {
        name: journal.title,
        exact: true,
      }),
    ).toHaveCount(0);
  });

  test("opening a journal shows its moments and excludes another journal's entry", async ({
    page,
    data,
  }) => {
    const journal = await data.journal({ title: data.label("Alpine journal") });
    const otherJournal = await data.journal({
      title: data.label("Coastal journal"),
    });
    const entryTitle = data.label("Alpine entry");
    const otherEntryTitle = data.label("Coastal entry");
    await data.moment({ journalId: journal.id, title: entryTitle });
    await data.moment({
      journalId: otherJournal.id,
      title: otherEntryTitle,
    });

    await page.goto("/journals");

    await page
      .getByRole("region", { name: "Journals" })
      .getByRole("link", { name: journal.title })
      .click();

    await expect(page).toHaveURL(
      (url) => url.pathname === `/journals/${journal.id}`,
    );
    const timelinePane = page.getByRole("region", { name: "Timeline" });
    await expect(
      timelinePane.getByRole("heading", { name: journal.title }),
    ).toBeVisible();
    await expect(
      timelinePane.getByRole("link", { name: entryTitle }),
    ).toBeVisible();
    await expect(
      timelinePane.getByRole("link", { name: otherEntryTitle }),
    ).toHaveCount(0);
  });
});
