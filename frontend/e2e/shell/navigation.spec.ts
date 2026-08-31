import { expect, test } from "../fixtures/test";
import { VIEWPORTS } from "../viewports";

test.describe("desktop shell navigation", () => {
  test.use({ viewport: VIEWPORTS.desktop });

  test("the signed-in app loads the timeline with sidebar navigation visible", {
    tag: "@smoke",
  }, async ({ page }) => {
    await page.goto("/timeline");

    await expect(page).toHaveURL((url) => url.pathname === "/timeline");
    const sidebar = page.getByRole("complementary", {
      name: "Primary navigation",
    });
    await expect(sidebar).toBeVisible();
    await expect(
      sidebar.getByRole("navigation", { name: "Views" }),
    ).toBeVisible();
    await expect(page.getByRole("region", { name: "Timeline" })).toBeVisible();
  });

  test("sidebar navigation marks the active destination", async ({ page }) => {
    await page.goto("/timeline");

    const sidebar = page.getByRole("complementary", {
      name: "Primary navigation",
    });
    const timeline = sidebar.getByRole("link", {
      name: "Timeline",
      exact: true,
    });
    const journals = sidebar.getByRole("link", { name: "All journals" });
    const tags = sidebar.getByRole("link", { name: "Tags", exact: true });

    await expect(timeline).toHaveAttribute("aria-current", "page");

    await journals.click();
    await expect(page).toHaveURL((url) => url.pathname === "/journals");
    await expect(journals).toHaveAttribute("aria-current", "page");

    await tags.click();
    await expect(page).toHaveURL((url) => url.pathname === "/library/tags");
    await expect(tags).toHaveAttribute("aria-current", "page");
  });
});

test.describe("mobile shell navigation", () => {
  test.use({ viewport: VIEWPORTS.mobile });

  test("opening a moment pushes from the list pane to the detail pane", async ({
    page,
    data,
  }) => {
    const journal = await data.journal();
    const title = data.label("Mobile detail entry");
    const moment = await data.moment({ journalId: journal.id, title });

    await page.goto("/timeline");

    const timelinePane = page.getByRole("region", { name: "Timeline" });
    const detailPane = page.getByRole("region", { name: "Moment detail" });
    await expect(timelinePane).toBeVisible();
    await expect(detailPane).toBeHidden();

    await page.getByRole("link", { name: title }).click();

    await expect(page).toHaveURL(
      (url) => url.pathname === `/timeline/${moment.id}`,
    );
    await expect(timelinePane).toBeHidden();
    await expect(detailPane).toBeVisible();
    await expect(page.getByRole("heading", { name: title })).toBeVisible();
  });
});

test.describe("tablet shell navigation", () => {
  test.use({ viewport: VIEWPORTS.tablet });

  test("navigation opens from the PageBar drawer", async ({ page }) => {
    await page.goto("/timeline");

    await expect(
      page.getByRole("complementary", { name: "Primary navigation" }),
    ).toBeHidden();
    const openNavigation = page.getByRole("button", {
      name: "Open navigation",
    });
    await expect(openNavigation).toBeVisible();

    await openNavigation.click();

    const drawer = page.getByRole("dialog", { name: "Journiv navigation" });
    await expect(drawer).toBeVisible();
    await expect(
      drawer.getByRole("navigation", { name: "Views" }),
    ).toBeVisible();
    await expect(
      drawer.getByRole("link", { name: "Timeline", exact: true }),
    ).toHaveAttribute("aria-current", "page");
  });
});
