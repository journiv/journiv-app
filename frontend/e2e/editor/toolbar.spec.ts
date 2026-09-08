import { expect, test } from "../fixtures/test";
import { VIEWPORTS } from "../viewports";

test.describe("editor toolbar layout", () => {
  test("fits its pane and keeps every action reachable at canonical widths", async ({
    page,
    data,
  }) => {
    const journal = await data.journal();
    let toolbarHeight: number | undefined;

    for (const viewport of Object.values(VIEWPORTS)) {
      await page.setViewportSize(viewport);
      await page.goto(`/journals/${journal.id}/new`);

      const toolbar = page.getByRole("toolbar", { name: "Editor actions" });
      await expect(toolbar).toBeVisible();

      const dimensions = await toolbar.evaluate((element) => {
        const buttons = [...element.querySelectorAll("button")].map(
          (button) => {
            const rect = button.getBoundingClientRect();
            return { width: rect.width, height: rect.height };
          },
        );
        const rect = element.getBoundingClientRect();
        return {
          clientWidth: element.clientWidth,
          scrollWidth: element.scrollWidth,
          toolbarHeight: rect.height,
          buttons,
        };
      });

      if (viewport === VIEWPORTS.mobile) {
        // The compact bar is one horizontally scrolling row — it is meant to
        // overflow its box, not collapse into a More popover.
        expect(dimensions.scrollWidth).toBeGreaterThan(dimensions.clientWidth);
      } else {
        expect(dimensions.scrollWidth).toBeLessThanOrEqual(
          dimensions.clientWidth,
        );
      }
      expect(dimensions.buttons.length).toBeGreaterThan(0);
      expect(new Set(dimensions.buttons.map(({ width }) => width)).size).toBe(
        1,
      );
      expect(new Set(dimensions.buttons.map(({ height }) => height)).size).toBe(
        1,
      );

      toolbarHeight ??= dimensions.toolbarHeight;
      expect(dimensions.toolbarHeight).toBe(toolbarHeight);

      for (const name of [
        "Bold",
        "Italic",
        "Bullet list",
        "Checklist",
        "Add link",
        "Add photo, video or audio",
        "Moment details",
      ]) {
        await expect(toolbar.getByRole("button", { name })).toHaveCount(1);
      }

      if (viewport === VIEWPORTS.mobile) {
        const editor = page.getByRole("textbox", { name: "Entry body" });
        await editor.click();

        // No More popover at the compact width: every control that the regular
        // width would collapse is present on the scrolling bar itself.
        await expect(
          toolbar.getByRole("button", { name: "More actions" }),
        ).toHaveCount(0);
        for (const name of [
          "Heading 1",
          "Heading 2",
          "Heading 3",
          "Undo",
          "Redo",
          "Ordered list",
          "Blockquote",
          "Underline",
          "Strike",
          "Markdown shortcuts",
        ]) {
          await expect(toolbar.getByRole("button", { name })).toHaveCount(1);
        }

        // Playwright scrolls the control into the bar's own overflow before
        // clicking it, so a swiped-away control is still reachable.
        await toolbar.getByRole("button", { name: "Heading 1" }).click();
        await page.keyboard.type("Mobile heading");
        await expect(editor.locator("h1")).toHaveText("Mobile heading");
      }
    }
  });
});
