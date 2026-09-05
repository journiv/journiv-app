import { VIEWPORTS } from "../viewports";
import { expect, test } from "../fixtures/test";

/**
 * The adaptive overlay contract (DESIGN.md, "Adaptive overlays"):
 *
 *     interaction                 <= 860px             > 860px
 *     form / substantial modal    Drawer               Dialog
 *     simple confirmation         Drawer               AlertDialog
 *     overflow command menu       Drawer action sheet  DropdownMenu
 *
 * 1024px is the point of this file. It is a *layout* breakpoint band, not an
 * overlay one, so a tablet-width window gets the same anchored menu and centred
 * dialog as 1440px. Anything that treats 1024 as "mobile" is the bug this spec
 * exists to catch.
 *
 * Branches are told apart by role where roles differ (alertdialog vs dialog,
 * menu vs dialog) and by rendered geometry where they do not — a form dialog is
 * a `dialog` in both presentations. No CSS-structural selectors (README DESIGN.md).
 */

/**
 * Both presentations are `role="dialog"`, so geometry is what tells them apart.
 * The Drawer animates in over ~450ms (transform + height), so a single
 * `boundingBox()` right after `toBeVisible()` can measure the surface
 * mid-flight. `expect.poll` retries until it settles — a retrying assertion,
 * never a sleep (e2e/README.md docs/domain/moments.md).
 */
type Box = { x: number; y: number; width: number; height: number };

async function settledBox(locator: {
  boundingBox: () => Promise<Box | null>;
}): Promise<Box> {
  let last: Box | null = null;
  await expect
    .poll(
      async () => {
        const box = await locator.boundingBox();
        const stable =
          box !== null &&
          last !== null &&
          Math.abs(box.width - last.width) < 1 &&
          Math.abs(box.height - last.height) < 1 &&
          Math.abs(box.y - last.y) < 1;
        last = box;
        return stable;
      },
      { message: "overlay geometry never settled" },
    )
    .toBe(true);
  if (!last) throw new Error("overlay has no bounding box");
  return last;
}

for (const [name, viewport] of Object.entries(VIEWPORTS)) {
  const compact = viewport.width <= 860;

  test.describe(`adaptive overlays · ${name} (${viewport.width}px)`, () => {
    test.use({ viewport });

    test("a form modal is a bottom sheet only when compact", async ({
      page,
    }) => {
      await page.goto("/journals");
      await page
        .getByRole("region", { name: "Journals" })
        .getByRole("button", { name: "New journal" })
        .first()
        .click();

      const dialog = page.getByRole("dialog", { name: "New journal" });
      await expect(dialog).toBeVisible();
      const box = await settledBox(dialog);
      if (compact) {
        // A sheet spans the viewport and sits flush to its bottom edge.
        expect(box.width).toBeGreaterThan(viewport.width - 8);
        expect(box.y + box.height).toBeGreaterThan(viewport.height - 8);
      } else {
        // A centred dialog is narrower and clear of the bottom edge.
        expect(box.width).toBeLessThan(viewport.width - 32);
        expect(box.y + box.height).toBeLessThan(viewport.height - 8);
      }

      // The journey itself must not depend on which branch rendered.
      await dialog.getByLabel("Title").fill(`overlay-${name}`);
      await dialog.getByRole("button", { name: "Create journal" }).click();
      await expect(
        page
          .getByRole("region", { name: "Journals" })
          .getByText(`overlay-${name}`, { exact: true }),
      ).toBeVisible();
    });

    test("an overflow menu anchors above 860px and becomes a sheet below", async ({
      page,
      data,
    }) => {
      const journal = await data.journal({ title: data.label("Menu journal") });
      await page.goto("/journals");

      await page
        .getByRole("region", { name: "Journals" })
        .getByRole("button", { name: `${journal.title} actions` })
        .click();

      if (compact) {
        // A Drawer is not a menu container: the actions are buttons in a
        // dialog named by the trigger's own label.
        await expect(
          page.getByRole("dialog", { name: `${journal.title} actions` }),
        ).toBeVisible();
        await expect(page.getByRole("menu")).toHaveCount(0);
        await expect(
          page.getByRole("button", { name: "Rename" }),
        ).toBeVisible();
      } else {
        await expect(page.getByRole("menu")).toBeVisible();
        await expect(
          page.getByRole("menuitem", { name: "Rename" }),
        ).toBeVisible();
      }
    });

    test("a simple confirmation is an alertdialog only above 860px", async ({
      page,
      data,
    }) => {
      const journal = await data.journal({ title: data.label("Entry home") });
      const moment = await data.moment({
        journalId: journal.id,
        body: "Something worth deleting",
      });
      await page.goto(`/timeline/${moment.id}`);

      await page.getByRole("button", { name: "Entry actions" }).click();
      await page
        .getByRole(compact ? "button" : "menuitem", { name: "Delete entry…" })
        .click();

      if (compact) {
        // Base UI's Drawer never becomes an alertdialog — assert the honest
        // role rather than semantics the primitive does not implement.
        await expect(page.getByRole("dialog")).toBeVisible();
        await expect(page.getByRole("alertdialog")).toHaveCount(0);
      } else {
        await expect(page.getByRole("alertdialog")).toBeVisible();
      }

      const surface = page.getByRole(compact ? "dialog" : "alertdialog");
      await expect(
        surface.getByRole("button", { name: "Cancel" }),
      ).toBeVisible();
      await expect(
        surface.getByRole("button", { name: "Delete entry" }),
      ).toBeVisible();
    });
  });
}

test.describe("menu to confirmation hand-off · mobile", () => {
  test.use({ viewport: VIEWPORTS.mobile });

  test("the action sheet closes, the confirmation opens, and the page still scrolls", async ({
    page,
    data,
  }) => {
    const journal = await data.journal({ title: data.label("Handoff") });
    await page.goto("/journals");

    const pane = page.getByRole("region", { name: "Journals" });
    await pane
      .getByRole("button", { name: `${journal.title} actions` })
      .click();
    const sheet = page.getByRole("dialog", {
      name: `${journal.title} actions`,
    });
    await expect(sheet).toBeVisible();

    await sheet.getByRole("button", { name: "Delete…" }).click();

    // The action sheet gives way to the typed-delete workflow — a new,
    // higher-attention surface, not something attached to the menu.
    await expect(sheet).toHaveCount(0);
    const confirmation = page.getByRole("dialog", {
      name: `Delete “${journal.title}”?`,
    });
    await expect(confirmation).toBeVisible();

    await confirmation.getByRole("button", { name: "Cancel" }).click();
    await expect(confirmation).toHaveCount(0);

    // Two overlapping popups each take a scroll lock; releasing one must not
    // leave the page locked. Asserted behaviourally, not by reading a class.
    await expect
      .poll(async () =>
        page.evaluate(() => {
          const el = document.scrollingElement ?? document.body;
          return getComputedStyle(el).overflow;
        }),
      )
      .not.toBe("hidden");
  });
});

test.describe("dark theme", () => {
  test.use({ viewport: VIEWPORTS.mobile, theme: "dark" });

  test("a confirmation sheet renders in dark mode", async ({ page, data }) => {
    const journal = await data.journal({ title: data.label("Dark") });
    await page.goto("/journals");

    await page
      .getByRole("region", { name: "Journals" })
      .getByRole("button", { name: `${journal.title} actions` })
      .click();
    const sheet = page.getByRole("dialog", {
      name: `${journal.title} actions`,
    });
    await expect(sheet).toBeVisible();

    await sheet.getByRole("button", { name: "Delete…" }).click();

    await expect(sheet).toHaveCount(0);
    await expect(
      page.getByRole("dialog", { name: `Delete “${journal.title}”?` }),
    ).toBeVisible();
  });
});
