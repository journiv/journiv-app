import { freezeClock } from "../fixtures/determinism";
import { expect, test } from "../fixtures/test";

// `fullyParallel` workers can be reused for later test groups, along with their
// account and its moments. A distinct worker-fixture pool gives TL-003 a fresh
// worker while still using the one shared Journiv authentication mechanism.
const freshAccountTest = test.extend<object, { freshAccountWorker: true }>({
  freshAccountWorker: [
    // Playwright requires a destructuring pattern for a fixture with no deps.
    // biome-ignore lint/correctness/noEmptyPattern: required by Playwright's fixture API
    async ({}, use) => {
      await use(true);
    },
    { scope: "worker", auto: true },
  ],
});

test.describe("timeline journeys", () => {
  test("created moments appear under their logged day", async ({
    page,
    data,
  }) => {
    await freezeClock(page);
    const journal = await data.journal();
    const firstTitle = data.label("Morning entry");
    const secondTitle = data.label("Evening entry");
    await data.moment({ journalId: journal.id, title: firstTitle });
    await data.moment({ journalId: journal.id, title: secondTitle });

    await page.goto("/timeline");

    const timeline = page.getByRole("region", { name: "Timeline" });
    await expect(
      timeline.getByRole("heading", { name: "Today", exact: true }),
    ).toBeVisible();
    await expect(
      timeline.getByRole("link", { name: firstTitle }),
    ).toBeVisible();
    await expect(
      timeline.getByRole("link", { name: secondTitle }),
    ).toBeVisible();
  });

  test("selecting a moment opens it in the reader pane", async ({
    page,
    data,
  }) => {
    const journal = await data.journal();
    const title = data.label("Reader entry");
    const moment = await data.moment({ journalId: journal.id, title });

    await page.goto("/timeline");
    await page
      .getByRole("region", { name: "Timeline" })
      .getByRole("link", { name: title })
      .click();

    await expect(page).toHaveURL(
      (url) => url.pathname === `/timeline/${moment.id}`,
    );
    await expect(
      page
        .getByRole("region", { name: "Moment detail" })
        .getByRole("heading", { name: title }),
    ).toBeVisible();
  });

  test("filtering by journal shows only that journal's moments", async ({
    page,
    data,
  }) => {
    const selectedJournal = await data.journal({
      title: data.label("Selected journal"),
    });
    const otherJournal = await data.journal({
      title: data.label("Other journal"),
    });
    const selectedTitle = data.label("Selected journal entry");
    const otherTitle = data.label("Other journal entry");
    await data.moment({
      journalId: selectedJournal.id,
      title: selectedTitle,
    });
    await data.moment({ journalId: otherJournal.id, title: otherTitle });

    await page.goto("/timeline");
    await page
      .getByRole("navigation", { name: "Journals" })
      .getByRole("link", { name: selectedJournal.title, exact: true })
      .click();

    await expect(page).toHaveURL(
      (url) => url.pathname === `/journals/${selectedJournal.id}`,
    );
    const timeline = page.getByRole("region", { name: "Timeline" });
    await expect(
      timeline.getByRole("heading", {
        name: selectedJournal.title,
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      timeline.getByRole("link", { name: selectedTitle }),
    ).toBeVisible();
    await expect(timeline.getByRole("link", { name: otherTitle })).toHaveCount(
      0,
    );
  });
});

freshAccountTest.describe("timeline journeys", () => {
  freshAccountTest(
    "a new account shows the empty timeline state",
    async ({ page }) => {
      await page.goto("/timeline");

      const timeline = page.getByRole("region", { name: "Timeline" });
      await expect(
        timeline.getByText("No moments yet", { exact: true }),
      ).toBeVisible();
      await expect(
        timeline.getByText("Your timeline will fill up as you write.", {
          exact: true,
        }),
      ).toBeVisible();
      await expect(
        timeline.getByRole("button", { name: "Write your first entry" }),
      ).toBeVisible();
    },
  );
});
