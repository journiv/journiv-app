import { expect, test } from "../fixtures/test";

const bodyContrast = () => {
  const toRgb = (color: string) => {
    const canvas = document.createElement("canvas");
    canvas.width = 1;
    canvas.height = 1;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Canvas 2D context is unavailable");
    context.fillStyle = color;
    context.fillRect(0, 0, 1, 1);
    return [...context.getImageData(0, 0, 1, 1).data].slice(0, 3);
  };
  const luminance = ([red, green, blue]: number[]) =>
    [red, green, blue]
      .map((channel) => channel / 255)
      .map((channel) =>
        channel <= 0.04045
          ? channel / 12.92
          : ((channel + 0.055) / 1.055) ** 2.4,
      )
      .reduce(
        (total, channel, index) =>
          total + channel * [0.2126, 0.7152, 0.0722][index],
        0,
      );
  const styles = getComputedStyle(document.body);
  const foreground = luminance(toRgb(styles.color));
  const background = luminance(toRgb(styles.backgroundColor));
  return (
    (Math.max(foreground, background) + 0.05) /
    (Math.min(foreground, background) + 0.05)
  );
};

test.describe("runtime design", () => {
  test("RD-001 body text keeps at least 5:1 contrast on the canvas", async ({
    page,
  }) => {
    await page.goto("/timeline");
    await expect(page.getByRole("region", { name: "Timeline" })).toBeVisible();

    const contrast = await page.evaluate(bodyContrast);

    expect(contrast).toBeGreaterThanOrEqual(5);
  });

  test("RD-002 the boundary widths keep the documented pane layout", async ({
    page,
    data,
  }) => {
    const journal = await data.journal();
    const title = data.label("Breakpoint entry");
    const moment = await data.moment({ journalId: journal.id, title });
    const timeline = page.getByRole("region", { name: "Timeline" });
    const detail = page.getByRole("region", { name: "Moment detail" });
    const navigation = page.getByRole("complementary", {
      name: "Primary navigation",
    });
    const openNavigation = page.getByRole("button", {
      name: "Open navigation",
    });

    await page.setViewportSize({ width: 859, height: 900 });
    await page.goto(`/timeline/${moment.id}`);
    await expect(detail.getByRole("heading", { name: title })).toBeVisible();
    await expect(timeline).toBeHidden();
    await expect(detail).toBeVisible();
    await expect(navigation).toBeHidden();
    await expect(openNavigation).toBeHidden();
    await expect(page.getByRole("button", { name: "Back" })).toBeVisible();

    for (const width of [861, 1099]) {
      await page.setViewportSize({ width, height: 900 });
      await expect(timeline).toBeVisible();
      await expect(detail).toBeVisible();
      await expect(navigation).toBeHidden();
      await expect(openNavigation).toBeVisible();

      const panes = await page.evaluate(() => {
        const timelinePane = document.querySelector('[aria-label="Timeline"]');
        const detailPane = document.querySelector(
          '[aria-label="Moment detail"]',
        );
        if (!timelinePane || !detailPane) throw new Error("Panes are missing");
        return {
          timelineRight: timelinePane.getBoundingClientRect().right,
          detailLeft: detailPane.getBoundingClientRect().left,
        };
      });
      expect(panes.timelineRight).toBeLessThanOrEqual(panes.detailLeft);
    }

    await page.setViewportSize({ width: 1101, height: 900 });
    await expect(timeline).toBeVisible();
    await expect(detail).toBeVisible();
    await expect(navigation).toBeVisible();
    await expect(openNavigation).toBeHidden();

    const desktopPanes = await page.evaluate(() => {
      const navigationPane = document.querySelector(
        '[aria-label="Primary navigation"]',
      );
      const timelinePane = document.querySelector('[aria-label="Timeline"]');
      const detailPane = document.querySelector('[aria-label="Moment detail"]');
      if (!navigationPane || !timelinePane || !detailPane)
        throw new Error("Desktop panes are missing");
      return {
        navigationRight: navigationPane.getBoundingClientRect().right,
        timelineLeft: timelinePane.getBoundingClientRect().left,
        timelineRight: timelinePane.getBoundingClientRect().right,
        detailLeft: detailPane.getBoundingClientRect().left,
      };
    });
    expect(desktopPanes.navigationRight).toBeLessThanOrEqual(
      desktopPanes.timelineLeft,
    );
    expect(desktopPanes.timelineRight).toBeLessThanOrEqual(
      desktopPanes.detailLeft,
    );
  });
});

test.describe("runtime design in dark mode", () => {
  test.use({ theme: "dark" });

  test("RD-001 body text keeps at least 5:1 contrast on the canvas", async ({
    page,
  }) => {
    await page.goto("/timeline");
    await expect(page.getByRole("region", { name: "Timeline" })).toBeVisible();

    const contrast = await page.evaluate(bodyContrast);

    expect(contrast).toBeGreaterThanOrEqual(5);
  });
});
