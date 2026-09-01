import { toggleGoalCompletionApiV1GoalsGoalIdTogglePost } from "@/api/generated";
import { expect, test } from "../fixtures/test";

test.describe("library entity journeys", () => {
  test("recording a starter mood on a moment shows it in the reader", async ({
    page,
    data,
  }) => {
    const journal = await data.journal();
    const moment = await data.moment({
      journalId: journal.id,
      title: data.label("Mood entry"),
    });

    await page.goto(`/timeline/${moment.id}/edit`);
    await page.getByRole("button", { name: "Moment details" }).click();

    const saved = page.waitForResponse(
      (response) =>
        response.request().method() === "PUT" &&
        new URL(response.url()).pathname === `/api/v1/moments/${moment.id}`,
    );
    await page.getByRole("button", { name: "Good", exact: true }).click();
    await saved;

    await page.goto(`/timeline/${moment.id}`);
    const reader = page.getByRole("article");
    await expect(reader.getByText("Good", { exact: true })).toBeVisible();

    await page.reload();
    await expect(reader.getByText("Good", { exact: true })).toBeVisible();
  });

  test("creating a person and attaching them to a moment shows them in the reader", async ({
    page,
    data,
  }) => {
    const journal = await data.journal();
    const moment = await data.moment({
      journalId: journal.id,
      title: data.label("People entry"),
    });
    const person = data.label("River Song");

    await page.goto("/settings/journaling/people");
    const people = page.getByRole("main", { name: "People" });
    await people.getByRole("button", { name: "Add person" }).first().click();

    const dialog = page.getByRole("dialog", { name: "Add person" });
    await dialog.getByLabel("Name", { exact: true }).fill(person);
    await dialog.getByRole("button", { name: "Add person" }).click();

    await expect(people.getByText(person, { exact: true })).toBeVisible();
    await page.reload();
    await expect(people.getByText(person, { exact: true })).toBeVisible();

    await page.goto(`/timeline/${moment.id}/edit`);
    await page.getByRole("button", { name: "Moment details" }).click();

    const attached = page.waitForResponse(
      (response) =>
        response.request().method() === "PUT" &&
        new URL(response.url()).pathname ===
          `/api/v1/moments/${moment.id}/people`,
    );
    await page.getByRole("checkbox", { name: person, exact: true }).click();
    await attached;

    await page.goto(`/timeline/${moment.id}`);
    const readerPeople = page.getByRole("region", { name: "People" });
    await expect(
      readerPeople.getByRole("link", { name: person, exact: true }),
    ).toBeVisible();

    await page.reload();
    await expect(
      readerPeople.getByRole("link", { name: person, exact: true }),
    ).toBeVisible();
  });

  test("creating a goal shows it in the list and completion updates its progress", async ({
    page,
    data,
    api,
  }) => {
    const title = data.label("Monthly reflection goal");

    await page.goto("/settings/journaling/goals");
    const goals = page.getByRole("main", { name: "Goals" });
    await goals.getByRole("button", { name: "Add goal" }).first().click();

    const dialog = page.getByRole("dialog", { name: "Add goal" });
    await dialog.getByLabel("Goal title").fill(title);
    await dialog.getByLabel("Frequency").selectOption("monthly");

    const createdResponse = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname === "/api/v1/goals",
    );
    await dialog.getByRole("button", { name: "Add goal" }).click();
    const created = (await (await createdResponse).json()) as { id?: string };
    if (!created.id) throw new Error("POST /api/v1/goals returned no goal id");

    const search = goals.getByLabel("Search goals");
    await search.fill(title);
    await expect(goals.getByText(title, { exact: true })).toBeVisible();
    await expect(
      goals.getByText("Monthly · Achieve · 0/1 this period", { exact: true }),
    ).toBeVisible();

    await page.reload();
    await goals.getByLabel("Search goals").fill(title);
    await expect(goals.getByText(title, { exact: true })).toBeVisible();

    const toggled = await toggleGoalCompletionApiV1GoalsGoalIdTogglePost({
      client: api,
      path: { goal_id: created.id },
      body: {
        logged_date: new Date().toISOString().slice(0, 10),
        status: "success",
      },
    });
    if (toggled.error !== undefined)
      throw new Error(
        `POST /api/v1/goals/${created.id}/toggle returned HTTP ${toggled.response?.status ?? "unknown"}`,
      );

    await page.reload();
    await goals.getByLabel("Search goals").fill(title);
    await expect(
      goals.getByText("Monthly · Achieve · 1/1 this period", { exact: true }),
    ).toBeVisible();
  });
});
