import type { Locator } from "@playwright/test";
import { expect, test } from "../fixtures/test";
import { VIEWPORTS, type ViewportName } from "../viewports";

/** The shell is a three-row grid (offline bar / content / update bar). A pane
 *  that fails to name `grid-row: 2` is auto-placed into the first row, where it
 *  collapses to its content height and paints over the navigation rail. Nothing
 *  else asserts geometry, so this is the guard: at every canonical width, every
 *  pane must occupy the full content row. */

const TOLERANCE = 1;

/** Panes fade and lift into place on arrival (`jv-pane-enter`, a 2px
 *  translate); measuring mid-flight reports geometry that is off by that
 *  offset. Wait for the pane's own animation to finish before reading a box —
 *  its own, not the document's: skeleton pulses run forever, and a cancelled
 *  animation rejects `finished`. */
async function box(locator: Locator) {
  await locator.evaluate(async (el) => {
    await Promise.all(
      el.getAnimations().map((animation) => animation.finished.catch(() => {})),
    );
  });
  const rect = await locator.boundingBox();
  if (!rect) throw new Error("expected the pane to be rendered");
  return rect;
}

/** Every pane, list or workspace, spans the shell's content row top to bottom. */
async function expectSpansContentRow(
  pane: Locator,
  viewport: { width: number; height: number },
) {
  await expect(pane).toBeVisible();
  const rect = await box(pane);
  expect(
    Math.abs(rect.y),
    "pane starts at the top of the shell",
  ).toBeLessThanOrEqual(TOLERANCE);
  expect(
    rect.y + rect.height,
    "pane reaches the bottom of the shell",
  ).toBeGreaterThanOrEqual(viewport.height - TOLERANCE);
}

/** A workspace also spans the list and page columns, so it reaches the right
 *  edge; a list pane occupies only its own column and does not. */
async function expectFillsContentRow(
  pane: Locator,
  viewport: { width: number; height: number },
) {
  await expectSpansContentRow(pane, viewport);
  const rect = await box(pane);
  expect(
    rect.x + rect.width,
    "pane reaches the right edge of the shell",
  ).toBeGreaterThanOrEqual(viewport.width - TOLERANCE);
}

/** Library-style workspaces span the list and page columns, so they must also
 *  start exactly where the navigation rail ends (desktop) or at the left edge
 *  (tablet, mobile: the rail is a drawer). */
const WORKSPACES: ReadonlyArray<{ path: string; label: string }> = [
  { path: "/library/tags", label: "Tags" },
  { path: "/settings/journaling/people", label: "People" },
  { path: "/settings/journaling/moods", label: "Moods" },
  { path: "/settings/journaling/activities", label: "Activities" },
  { path: "/settings/journaling/goals", label: "Goals" },
  { path: "/library/prompts", label: "Prompts" },
  { path: "/insights", label: "Insights" },
];

for (const name of Object.keys(VIEWPORTS) as ViewportName[]) {
  const viewport = VIEWPORTS[name];

  test.describe(`${name} pane geometry`, () => {
    test.use({ viewport });

    for (const { path, label } of WORKSPACES) {
      test(`${label} fills the content row`, async ({ page }) => {
        await page.goto(path);

        const workspace = page.getByRole("main", { name: label });
        await expectFillsContentRow(workspace, viewport);

        if (name === "desktop") {
          const nav = page.getByRole("complementary", {
            name: "Primary navigation",
          });
          const navRect = await box(nav);
          const rect = await box(workspace);
          expect(
            rect.x,
            "workspace does not overlap the navigation rail",
          ).toBeGreaterThanOrEqual(navRect.x + navRect.width - TOLERANCE);
          expect(navRect.height, "nav is not covered").toBeGreaterThanOrEqual(
            viewport.height - TOLERANCE,
          );
        } else {
          expect(Math.abs((await box(workspace)).x)).toBeLessThanOrEqual(
            TOLERANCE,
          );
        }
      });
    }

    test("Journals list pane fills the content row", async ({ page }) => {
      await page.goto("/journals");
      await expectSpansContentRow(
        page.getByRole("region", { name: "Journals" }),
        viewport,
      );
    });

    test("Timeline list pane fills the content row", async ({ page }) => {
      await page.goto("/timeline");
      await expectSpansContentRow(
        page.getByRole("region", { name: "Timeline" }),
        viewport,
      );
    });
  });
}
