import { expect, test } from "../fixtures/test";

test.describe("tag journeys", () => {
  test("creating a tag and attaching it to a moment shows it in the reader", async ({
    page,
    data,
  }) => {
    const journal = await data.journal();
    const moment = await data.moment({
      journalId: journal.id,
      title: data.label("Tagged entry"),
    });
    const tag = data.label("created tag").toLowerCase();

    await page.goto("/library/tags");
    const tags = page.getByRole("main", { name: "Tags" });
    await tags.getByRole("button", { name: "New tag" }).first().click();

    const dialog = page.getByRole("dialog", { name: "New tag" });
    await dialog.getByLabel("Tag name").fill(tag);
    await dialog.getByRole("button", { name: "Add tag" }).click();

    await expect(tags.getByText(tag, { exact: true })).toBeVisible();

    await data.tags(moment.id, [tag]);
    await page.goto(`/timeline/${moment.id}`);

    const readerTags = page.getByRole("region", { name: "Tags" });
    await expect(readerTags.getByRole("link", { name: tag })).toBeVisible();

    await page.reload();
    await expect(readerTags.getByRole("link", { name: tag })).toBeVisible();
  });

  test("renaming a tag updates the library and the moment carrying it", async ({
    page,
    data,
  }) => {
    const journal = await data.journal();
    const moment = await data.moment({
      journalId: journal.id,
      title: data.label("Renamed tag entry"),
    });
    const original = data.label("original tag").toLowerCase();
    const renamed = data.label("renamed tag").toLowerCase();
    await data.tags(moment.id, [original]);

    await page.goto("/library/tags");
    const tags = page.getByRole("main", { name: "Tags" });
    await tags.getByRole("link").filter({ hasText: original }).first().click();

    await page.getByRole("button", { name: "Rename" }).click();
    const dialog = page.getByRole("dialog", {
      name: `Rename #${original}`,
    });
    await dialog.getByLabel("Tag name").fill(renamed);
    await dialog.getByRole("button", { name: "Save" }).click();

    const detail = page.getByRole("main", { name: "Tags" });
    await expect(
      detail.getByText(`#${renamed}`, { exact: true }),
    ).toBeVisible();

    await detail.getByRole("link", { name: "Tags", exact: true }).click();
    await expect(tags.getByText(renamed, { exact: true })).toBeVisible();
    await expect(tags.getByText(original, { exact: true })).toHaveCount(0);

    await page.goto(`/timeline/${moment.id}`);
    const readerTags = page.getByRole("region", { name: "Tags" });
    await expect(readerTags.getByRole("link", { name: renamed })).toBeVisible();
    await expect(readerTags.getByRole("link", { name: original })).toHaveCount(
      0,
    );

    await page.reload();
    await expect(readerTags.getByRole("link", { name: renamed })).toBeVisible();
  });

  test("a tag detail page lists the moments carrying it", async ({
    page,
    data,
  }) => {
    const journal = await data.journal();
    const firstTitle = data.label("First tagged entry");
    const secondTitle = data.label("Second tagged entry");
    const first = await data.moment({
      journalId: journal.id,
      title: firstTitle,
    });
    const second = await data.moment({
      journalId: journal.id,
      title: secondTitle,
    });
    const tag = data.label("shared tag").toLowerCase();
    await data.tags(first.id, [tag]);
    await data.tags(second.id, [tag]);

    await page.goto("/library/tags");
    await page
      .getByRole("main", { name: "Tags" })
      .getByRole("link")
      .filter({ hasText: tag })
      .first()
      .click();

    const recent = page.getByRole("region", { name: "Recent moments" });
    await expect(
      recent.getByRole("link").filter({ hasText: firstTitle }),
    ).toBeVisible();
    await expect(
      recent.getByRole("link").filter({ hasText: secondTitle }),
    ).toBeVisible();
  });
});
