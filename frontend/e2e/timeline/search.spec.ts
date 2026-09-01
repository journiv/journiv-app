import { expect, test } from "../fixtures/test";

test.describe("timeline search", () => {
  test("searching narrows the timeline to matching entries", async ({
    page,
    data,
  }) => {
    const journal = await data.journal();
    const matchingTitle = data.label("Orchid sunrise");
    const otherTitle = data.label("Harbor fog");
    await data.moment({ journalId: journal.id, title: matchingTitle });
    await data.moment({ journalId: journal.id, title: otherTitle });

    await page.goto("/timeline");
    const timeline = page.getByRole("region", { name: "Timeline" });
    await expect(
      timeline.getByRole("link", { name: matchingTitle }),
    ).toBeVisible();
    await expect(
      timeline.getByRole("link", { name: otherTitle }),
    ).toBeVisible();

    await timeline.getByLabel("Search all moments").fill("Orchid");
    await expect(page).toHaveURL(
      (url) =>
        url.pathname === "/timeline" && url.searchParams.get("q") === "Orchid",
    );
    await expect(
      timeline.getByRole("link", { name: matchingTitle }),
    ).toBeVisible();
    await expect(timeline.getByRole("link", { name: otherTitle })).toHaveCount(
      0,
    );
  });

  test("an unmatched query shows the search empty state and clearing restores entries", async ({
    page,
    data,
  }) => {
    const journal = await data.journal();
    const firstTitle = data.label("Amber trail");
    const secondTitle = data.label("Cobalt lake");
    await data.moment({ journalId: journal.id, title: firstTitle });
    await data.moment({ journalId: journal.id, title: secondTitle });

    await page.goto("/timeline");
    const timeline = page.getByRole("region", { name: "Timeline" });
    const search = timeline.getByLabel("Search all moments");
    const query = "violet-no-such-memory";
    await search.fill(query);

    await expect(page).toHaveURL(
      (url) =>
        url.pathname === "/timeline" && url.searchParams.get("q") === query,
    );
    await expect(
      timeline.getByText(`No moments match “${query}”`, { exact: true }),
    ).toBeVisible();

    await search.fill("");
    await expect(page).toHaveURL(
      (url) =>
        url.pathname === "/timeline" &&
        (url.searchParams.get("q") ?? "") === "",
    );
    await expect(
      timeline.getByRole("link", { name: firstTitle }),
    ).toBeVisible();
    await expect(
      timeline.getByRole("link", { name: secondTitle }),
    ).toBeVisible();
  });
});
