import { expect, test } from "../fixtures/test";
import { SKIP_WEB_SERVER } from "../env";

test.describe("production frontend cutover", { tag: "@smoke" }, () => {
  test.skip(
    !SKIP_WEB_SERVER,
    "dual-SPA checks require the FastAPI production frontend server",
  );

  test("React owns root deep links, refreshes, and same-origin API calls", async ({
    page,
  }) => {
    await page.goto("/settings/support/help");
    await expect(
      page.getByRole("heading", { name: "Help & feedback" }),
    ).toBeVisible();

    await page.reload();
    await expect(
      page.getByRole("heading", { name: "Help & feedback" }),
    ).toBeVisible();

    const health = await page.evaluate(async () => {
      const response = await fetch("/api/v1/health");
      return { ok: response.ok, url: response.url };
    });
    expect(health.ok).toBe(true);
    expect(new URL(health.url).origin).toBe(new URL(page.url()).origin);

    await expect(
      page.getByRole("link", { name: /use legacy interface/i }),
    ).toHaveAttribute("href", "/legacy/");
  });

  test("Flutter owns legacy deep links without consuming React auth", async ({
    page,
  }) => {
    await page.goto("/");
    const reactSession = await page.evaluate(() =>
      sessionStorage.getItem("journiv.session.v1"),
    );
    expect(reactSession).not.toBeNull();

    const response = await page.goto("/legacy/settings", {
      waitUntil: "domcontentloaded",
    });
    expect(response?.ok()).toBe(true);
    await expect(page.locator("flutter-view")).toBeVisible({ timeout: 30_000 });
    expect(new URL(page.url()).pathname.startsWith("/legacy/")).toBe(true);

    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(page.locator("flutter-view")).toBeVisible({ timeout: 30_000 });
    expect(new URL(page.url()).pathname.startsWith("/legacy/")).toBe(true);
    expect(
      await page.evaluate(() => sessionStorage.getItem("journiv.session.v1")),
    ).toBe(reactSession);
  });
});
