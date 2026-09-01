import { expect, test } from "../fixtures/test";

/** A small, valid PNG generated in the browser for each upload test. */
async function imageFixture(page: {
  evaluate: (pageFunction: () => string) => Promise<string>;
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

test.describe("media attachments", () => {
  test("uploading an image attaches it to the entry and it survives a reload", async ({
    page,
    data,
  }) => {
    const journal = await data.journal();
    const title = data.label("Entry with a photo");
    const moment = await data.moment({ journalId: journal.id, title });

    await page.goto(`/timeline/${moment.id}/edit`);
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
      name: "e2e-photo.png",
      mimeType: "image/png",
      buffer: await imageFixture(page),
    });
    await uploaded;

    await page.getByRole("button", { name: "Done" }).click();
    await expect(page).toHaveURL(
      (url) => url.pathname === `/timeline/${moment.id}`,
    );

    await page.goto("/timeline");
    const row = page
      .getByRole("region", { name: "Timeline" })
      .getByRole("link", { name: title });
    // Timeline thumbnails are intentionally decorative (`alt=""`), so they
    // have no accessible role. This assertion waits for real async processing.
    await expect(row.locator("img")).toBeVisible();

    await page.reload();
    await expect(
      page
        .getByRole("region", { name: "Timeline" })
        .getByRole("link", { name: title })
        .locator("img"),
    ).toBeVisible();
  });

  test("a rejected file upload shows an error", async ({ page, data }) => {
    const journal = await data.journal();
    const moment = await data.moment({ journalId: journal.id });

    await page.goto(`/timeline/${moment.id}/edit`);
    await page
      .getByRole("button", { name: "Add photo, video or audio" })
      .click();
    await page.setInputFiles('input[type="file"]', {
      name: "e2e-not-media.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("This is not an image, video, or audio file."),
    });

    await expect(page.getByRole("alert")).toContainText(
      "That file couldn’t be read.",
    );
  });
});
