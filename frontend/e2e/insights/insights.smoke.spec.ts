import { freezeClock, FROZEN_NOW } from "../fixtures/determinism";
import { expect, test } from "../fixtures/test";

/** Days before the frozen clock. `/moods/analytics/statistics` windows on the
 *  start/end dates the frontend derives from `Date.now()`, so freezing the
 *  browser clock to `FROZEN_NOW` makes seeding into a given Trend-period window
 *  deterministic. The writing-trend endpoint windows server-side on the real
 *  clock, so that surface is asserted structurally, not by seeded values
 *  (docs/features/insights.md). */
function daysAgo(n: number): Date {
  return new Date(FROZEN_NOW.getTime() - n * 24 * 60 * 60 * 1000);
}

test.describe("Insights", { tag: "@smoke" }, () => {
  test("summary, tab switching, period control and per-journal analytics", async ({
    page,
    data,
  }) => {
    const journal = await data.journal({
      title: data.label("Insights journal"),
    });
    for (let i = 0; i < 3; i++) {
      await data.moment({
        journalId: journal.id,
        title: data.label(`Entry ${i}`),
      });
    }

    await page.goto("/insights");

    // Reused Library workspace shell: one h1, the summary strip, the tab strip.
    await expect(
      page.getByRole("heading", { name: "Insights", level: 1 }),
    ).toBeVisible();
    await expect(page.getByText("Writing streak")).toBeVisible();
    await expect(page.getByText("Total entries")).toBeVisible();
    await expect(page.getByRole("tab", { name: "Overview" })).toBeVisible();

    // Overview renders its trend section (a chart or an in-range empty state)
    // and the Trend period control.
    const overview = page.getByRole("tabpanel");
    await expect(
      overview.getByRole("region", { name: "Writing frequency" }),
    ).toBeVisible();
    await expect(
      overview.getByRole("region", { name: "This month" }),
    ).toBeVisible();

    // The Trend period control shares the tab-strip row (outside the tabpanel);
    // it re-fires the windowed request and records the choice in the URL, and
    // is replaced by a static "All time" note on the Journals tab.
    const patterns365 = page.waitForResponse(
      (r) =>
        r.url().includes("/analytics/writing-patterns") &&
        r.url().includes("days=365"),
    );
    await page.getByLabel("Trend period").selectOption("365");
    await patterns365;
    await expect(page).toHaveURL(/[?&]period=365\b/);

    // Switching tabs keeps the period.
    await page.getByRole("tab", { name: "Journals" }).click();
    await expect(page).toHaveURL(/[?&]tab=journals\b/);
    await expect(page).toHaveURL(/[?&]period=365\b/);
    await expect(page.getByText("All time")).toBeVisible();
    await expect(
      page.getByRole("combobox", { name: "Trend period" }),
    ).toHaveCount(0);
    const perJournal = page.getByRole("region", { name: "Per journal" });
    await expect(
      perJournal.getByRole("cell", { name: data.label("Insights journal") }),
    ).toBeVisible();
    await expect(
      perJournal.getByRole("cell", { name: "3", exact: true }),
    ).toBeVisible();

    // Mood tab with nothing logged: the deterministic assertion is the empty
    // state.
    await page.getByRole("tab", { name: "Mood" }).click();
    await expect(page).toHaveURL(/[?&]tab=mood\b/);
    await expect(
      page.getByText("No moods logged in this period yet.").first(),
    ).toBeVisible();
  });

  test("Mood tab reflects seeded mood logs and reacts to the Trend period", async ({
    page,
    data,
  }) => {
    await freezeClock(page);

    const journal = await data.journal({ title: data.label("Mood journal") });
    const moods = await data.moods();
    const pick = (category: string) => {
      const mood = moods.find((m) => m.category === category);
      if (!mood) throw new Error(`no seeded mood in category ${category}`);
      return mood;
    };
    const positive = pick("positive");
    const negative = pick("negative");
    const neutral = pick("neutral");

    // Six logs, positive in the majority so "most frequent" is unambiguous.
    // Only the day-2 log falls inside a 7-day window; all six are inside 30.
    const plan: Array<[number, string]> = [
      [2, positive.id],
      [10, positive.id],
      [12, positive.id],
      [14, negative.id],
      [20, negative.id],
      [26, neutral.id],
    ];
    for (const [offset, moodId] of plan) {
      await data.moment({
        journalId: journal.id,
        title: data.label(`Mood ${offset}`),
        loggedAt: daysAgo(offset),
        primaryMoodId: moodId,
      });
    }

    await page.goto("/insights?tab=mood&period=30");

    // Non-empty mood surface — assert on region headings, labels and values,
    // never on the chart's SVG / Recharts internals.
    const moodOverview = page.getByRole("region", { name: "Mood overview" });
    await expect(moodOverview.getByText("Mood logs")).toBeVisible();
    await expect(moodOverview.getByText("Most frequent")).toBeVisible();
    await expect(moodOverview.getByText(positive.name)).toBeVisible();
    await expect(
      page.getByText("No moods logged in this period yet."),
    ).toHaveCount(0);

    await expect(
      page.getByRole("region", { name: "Mood over time" }),
    ).toBeVisible();

    const balance = page.getByRole("region", { name: "Mood balance" });
    const bars = balance.getByRole("list", { name: "Mood distribution" });
    await expect(bars.getByText("Positive")).toBeVisible();
    await expect(bars.getByText("Negative")).toBeVisible();
    await expect(bars.getByText("Neutral")).toBeVisible();
    await expect(bars.getByText("50%")).toBeVisible();

    // Narrowing the Trend period re-requests mood statistics for the shorter
    // window; only the day-2 log survives it, so the distribution collapses to
    // Positive alone.
    const stats7 = page.waitForResponse((r) => {
      if (!r.url().includes("/moods/analytics/statistics")) return false;
      const params = new URL(r.url()).searchParams;
      const start = params.get("start_date");
      const end = params.get("end_date");
      if (!start || !end) return false;
      const span =
        (Date.parse(`${end}T00:00:00Z`) - Date.parse(`${start}T00:00:00Z`)) /
        86_400_000;
      return span <= 7;
    });
    await page.getByLabel("Trend period").selectOption("7");
    await stats7;
    await expect(page).toHaveURL(/[?&]period=7\b/);
    await expect(bars.getByText("Positive")).toBeVisible();
    await expect(bars.getByText("Negative")).toHaveCount(0);
    await expect(bars.getByText("100%")).toBeVisible();
  });
});
