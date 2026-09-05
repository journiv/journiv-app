import { VIEWPORTS } from "../viewports";
import { expect, test } from "../fixtures/test";

for (const theme of ["light", "dark"] as const) {
  for (const [name, viewport] of Object.entries(VIEWPORTS)) {
    const compact = viewport.width <= 860;

    test.describe(`reader actions · ${theme} · ${name} (${viewport.width}px)`, () => {
      test.use({ viewport, theme });

      test("keeps download and destructive delete in the adaptive overflow menu", async ({
        page,
        data,
      }) => {
        const journal = await data.journal({
          title: data.label("Reader menu"),
        });
        const moment = await data.moment({
          journalId: journal.id,
          title: data.label("Reader entry"),
        });
        await page.goto(`/timeline/${moment.id}`);

        await page.getByRole("button", { name: "Entry actions" }).click();
        const surface = page.getByRole(compact ? "dialog" : "menu", {
          name: compact ? "Entry actions" : undefined,
        });
        await expect(surface).toBeVisible();
        await expect(
          surface.getByRole(compact ? "button" : "menuitem", {
            name: "Download PDF",
          }),
        ).toBeVisible();
        await expect(
          surface.getByRole(compact ? "button" : "menuitem", {
            name: "Delete entry…",
          }),
        ).toBeVisible();

        if (!compact) {
          await expect(
            surface.locator("[data-slot=dropdown-menu-separator]"),
          ).toBeVisible();
          await expect(
            surface.getByRole("menuitem", { name: "Delete entry…" }),
          ).toHaveAttribute("data-variant", "destructive");
        }
      });
    });
  }
}

test.describe("reader PDF feedback · dark mobile", () => {
  test.use({ viewport: VIEWPORTS.mobile, theme: "dark" });

  test("shows a pending action, then a failure toast", async ({
    page,
    data,
  }) => {
    const journal = await data.journal({ title: data.label("PDF feedback") });
    const moment = await data.moment({ journalId: journal.id });
    const pdfRoute = `**/api/v1/entries/${moment.entry?.id}/pdf`;
    let failPdf: (() => void) | undefined;
    const pendingPdf = new Promise<void>((resolve) => {
      failPdf = resolve;
    });
    await page.route(pdfRoute, async (route) => {
      await pendingPdf;
      await route.fulfill({ status: 500 });
    });
    await page.goto(`/timeline/${moment.id}`);

    await page.getByRole("button", { name: "Entry actions" }).click();
    await page.getByRole("button", { name: "Download PDF" }).click();

    // The action sheet closes on select, so the in-flight state lives in a
    // pending toast rather than the (now unmounted) menu item.
    await expect(page.getByText("Preparing your PDF…")).toBeVisible();

    await page.getByRole("button", { name: "Entry actions" }).click();
    const pending = page.getByRole("button", { name: "Downloading PDF…" });
    await expect(pending).toBeDisabled();

    failPdf?.();
    // A high-priority error toast announces through an assertive live region;
    // its retry lives on the visible surface (aria-hidden until focused).
    await expect(
      page.getByRole("alert").getByText("Couldn’t download PDF. Try again."),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Retry", includeHidden: true }),
    ).toBeVisible();
  });
});
