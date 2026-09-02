import { expect, test } from "../fixtures/test";
import { VIEWPORTS } from "../viewports";

/**
 * The longest form in the product — Library → Goals → "Add goal", ten fields
 * plus a colour swatch grid and an icon grid — against the adaptive overlay
 * contract (DESIGN.md §9).
 *
 * This exists because that form used to be a plain centred `Dialog`. At
 * 390×844 it laid out at roughly 1300px tall, so it overflowed the viewport
 * with no scroll owner: the "Add goal" button was simply off-screen and the
 * form could not be submitted at all. Height alone is not the bug and is not
 * what this asserts — a long form is allowed to be long. What must hold is that
 * the surface fits the viewport, the *body* is what scrolls, and the actions
 * stay reachable while it does.
 *
 * Both listed viewports matter and for different reasons: 390 is the sheet
 * branch, 1024 is the centred-dialog branch that a naive "tablet is mobile"
 * reading gets wrong.
 */
for (const name of ["mobile", "tablet"] as const) {
  const viewport = VIEWPORTS[name];

  test.describe(`long library form · ${name} (${viewport.width}×${viewport.height})`, () => {
    test.use({ viewport });

    test("fits the viewport, scrolls its body, and keeps its actions reachable", async ({
      page,
    }) => {
      await page.goto("/settings/journaling/goals");
      await page
        .getByRole("main", { name: "Goals" })
        .getByRole("button", { name: "Add goal" })
        .first()
        .click();

      const dialog = page.getByRole("dialog", { name: "Add goal" });
      await expect(dialog).toBeVisible();

      // 1. The surface is inside the viewport. A modal taller than the window
      //    has already lost, whichever branch rendered it.
      await expect
        .poll(async () => {
          const box = await dialog.boundingBox();
          return box
            ? box.y >= 0 && box.y + box.height <= viewport.height
            : null;
        })
        .toBe(true);

      // 2. The submit action is on screen *before* anything is scrolled. This
      //    is the regression: it used to be below the fold with no way down.
      const submit = dialog.getByRole("button", { name: "Add goal" });
      await expect(submit).toBeInViewport();
      await expect(
        dialog.getByRole("button", { name: "Cancel" }),
      ).toBeInViewport();

      // 3. The content really is taller than the space it was given — without
      //    this the first two assertions could pass on a form that happens to
      //    fit, and would stop testing anything the day it grows.
      // The last fieldset in the form. Deliberately not one of the colour or
      // icon radios: those are `sr-only` inputs behind a styled label, so
      // `toBeInViewport` would read 0 for them wherever the form is scrolled.
      const lastField = dialog.getByRole("group", { name: "Icon" });
      await expect(lastField).not.toBeInViewport();

      // 4. The body is the scroll owner: scrolling brings the far end of the
      //    form up, and the actions do not scroll away with it.
      await lastField.scrollIntoViewIfNeeded();
      await expect(lastField).toBeInViewport();
      await expect(submit).toBeInViewport();

      // 5. And the form still works from there.
      await dialog.getByLabel("Goal title").fill("Longest form goal");
      await expect(submit).toBeEnabled();
    });

    test("the first field does not steal focus in the sheet presentation", async ({
      page,
    }) => {
      await page.goto("/settings/journaling/goals");
      await page
        .getByRole("main", { name: "Goals" })
        .getByRole("button", { name: "Add goal" })
        .first()
        .click();

      const dialog = page.getByRole("dialog", { name: "Add goal" });
      await expect(dialog).toBeVisible();

      // Autofocusing a text input inside the opening tap summons the on-screen
      // keyboard, which costs a third of a 844px-tall viewport before the user
      // has decided to type. The centred dialog has no such cost and does focus.
      const titleFocused = await dialog
        .getByLabel("Goal title")
        .evaluate((el) => el === document.activeElement);
      expect(titleFocused).toBe(viewport.width > 860);
    });
  });
}
