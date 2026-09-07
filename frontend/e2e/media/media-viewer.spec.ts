import { expect, test } from "../fixtures/test";

/** A small, valid PNG generated in the browser. */
async function pngFixture(page: {
  evaluate: (fn: () => string) => Promise<string>;
}) {
  const dataUrl = await page.evaluate(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 24;
    canvas.height = 24;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Canvas is unavailable");
    for (let y = 0; y < canvas.height; y += 1) {
      for (let x = 0; x < canvas.width; x += 1) {
        context.fillStyle = (x + y) % 2 === 0 ? "#405DE6" : "#F2EFEA";
        context.fillRect(x, y, 1, 1);
      }
    }
    return canvas.toDataURL("image/png");
  });
  return Buffer.from(dataUrl.slice(dataUrl.indexOf(",") + 1), "base64");
}

test.describe("reader media viewer", () => {
  test("opens a gallery photo full screen, navigates without stacking history, deep-links, and restores focus", async ({
    page,
    data,
  }) => {
    const journal = await data.journal();
    const title = data.label("Entry with photos");
    const moment = await data.moment({ journalId: journal.id, title });

    // Attach two photos to the moment through the editor.
    const mediaIds: string[] = [];
    await page.goto(`/timeline/${moment.id}/edit`);
    for (let i = 0; i < 2; i += 1) {
      await page
        .getByRole("button", { name: "Add photo, video or audio" })
        .click();
      const uploaded = page.waitForResponse(
        (response) =>
          response.request().method() === "POST" &&
          new URL(response.url()).pathname === "/api/v1/media/upload" &&
          response.status() === 201,
      );
      await page.setInputFiles('input[type="file"]', {
        name: `viewer-${i}.png`,
        mimeType: "image/png",
        buffer: await pngFixture(page),
      });
      mediaIds.push((await (await uploaded).json()).id as string);
    }
    await page.getByRole("button", { name: "Done" }).click();
    await expect(page).toHaveURL(
      (url) => url.pathname === `/timeline/${moment.id}`,
    );

    const triggers = page.getByRole("button", { name: /^View photo/ });
    await expect(triggers).toHaveCount(2);

    // Open the first photo.
    await triggers.first().click();
    await expect(page).toHaveURL(/[?&]media=/);
    const viewer = page.getByRole("dialog", { name: "Media viewer" });
    await expect(viewer).toBeVisible();
    const firstId = new URL(page.url()).searchParams.get("media");

    // Advance: the id changes but the history entry is replaced, not pushed.
    await page.keyboard.press("ArrowRight");
    await expect(page).toHaveURL(
      (url) => url.searchParams.get("media") !== firstId,
    );

    // One Back closes the viewer instead of stepping to the previous photo.
    await page.goBack();
    await expect(viewer).toBeHidden();
    await expect(page).toHaveURL(
      (url) =>
        url.pathname === `/timeline/${moment.id}` &&
        !url.searchParams.has("media"),
    );

    // A direct deep link to a valid media id opens the viewer and is not
    // stripped while the media list loads.
    await page.goto(`/timeline/${moment.id}?media=${mediaIds[1]}`);
    await expect(
      page.getByRole("dialog", { name: "Media viewer" }),
    ).toBeVisible();
    await expect(page).toHaveURL(
      (url) => url.searchParams.get("media") === mediaIds[1],
    );

    // A bogus deep-link id is dropped once the list has settled.
    await page.goto(`/timeline/${moment.id}?media=does-not-exist`);
    await expect(triggers.first()).toBeVisible();
    await expect(page).toHaveURL((url) => !url.searchParams.has("media"));
    await expect(page.getByRole("dialog")).toBeHidden();

    // Reopen and dismiss with Escape; focus returns to the trigger.
    await triggers.first().click();
    await expect(
      page.getByRole("dialog", { name: "Media viewer" }),
    ).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toBeHidden();
    await expect(triggers.first()).toBeFocused();
  });
});
