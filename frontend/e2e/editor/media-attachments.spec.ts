import { expect, test } from "../fixtures/test";
import { VIEWPORTS } from "../viewports";

const PHOTO = {
  name: "memory.png",
  mimeType: "image/png",
  // A valid 1px PNG keeps the backend's real media validation and processing
  // in the journey without adding a binary fixture to the repository.
  buffer: Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
    "base64",
  ),
};

const isUpload = (response: {
  url(): string;
  request(): { method(): string };
}) =>
  response.request().method() === "POST" &&
  new URL(response.url()).pathname === "/api/v1/media/upload";

function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((settle) => {
    resolve = settle;
  });
  return { promise, resolve };
}

test.describe("editor media attachments", () => {
  test.use({ viewport: VIEWPORTS.mobile });

  test("the file chooser preserves a caret in the middle of the writing", async ({
    page,
    data,
  }) => {
    const journal = await data.journal();
    const firstParagraph = "alpha bravo charlie";
    const secondParagraph = "second paragraph";

    await page.goto(`/journals/${journal.id}/new`);
    const editor = page.getByRole("textbox", { name: "Entry body" });
    await editor.click();
    await page.keyboard.type(firstParagraph);
    await page.keyboard.press("Enter");
    await page.keyboard.type(secondParagraph);

    // Place the caret after "alpha" through the browser's native Selection
    // API. The toolbar and native chooser must not replace it with the end.
    await editor.evaluate((root, offset) => {
      const firstLine = root.querySelector("p");
      const text = firstLine?.firstChild;
      if (!text) throw new Error("Could not find the first paragraph text");
      const range = document.createRange();
      range.setStart(text, offset);
      range.collapse(true);
      const selection = window.getSelection();
      selection?.removeAllRanges();
      selection?.addRange(range);
      (root as HTMLElement).focus();
      document.dispatchEvent(new Event("selectionchange"));
    }, "alpha".length);
    expect(
      await editor.evaluate((root) => {
        const selection = window.getSelection();
        if (!selection?.anchorNode) return -1;
        const beforeCaret = document.createRange();
        beforeCaret.setStart(root, 0);
        beforeCaret.setEnd(selection.anchorNode, selection.anchorOffset);
        return beforeCaret.toString().length;
      }),
    ).toBe("alpha".length);

    const fileChooser = page.waitForEvent("filechooser");
    await page
      .getByRole("button", { name: "Add photo, video or audio" })
      .click();
    const chooseFiles = page.getByRole("button", { name: "Choose files" });
    if (await chooseFiles.isVisible()) await chooseFiles.click();
    const uploadResponse = page.waitForResponse(isUpload);
    await (await fileChooser).setFiles(PHOTO);
    await uploadResponse;

    const image = editor.locator("img:not(.jv-upload__preview)");
    await expect(image).toHaveCount(1);
    const surroundingText = await image.evaluate((node) => {
      const root = node.closest("[contenteditable='true']");
      if (!root) throw new Error("Could not find the editor root");
      const before = document.createRange();
      before.setStart(root, 0);
      before.setEndBefore(node);
      const after = document.createRange();
      after.setStartAfter(node);
      after.setEnd(root, root.childNodes.length);
      return {
        before: before.cloneContents().textContent ?? "",
        after: after.cloneContents().textContent ?? "",
      };
    });

    expect(surroundingText.before).toContain("alpha");
    expect(surroundingText.after).toContain("bravo charlie");
    expect(surroundingText.after).toContain(secondParagraph);
  });

  test("Done explains that a slow upload must finish, then saves", async ({
    page,
    data,
  }) => {
    const journal = await data.journal();
    const title = data.label("Slow upload");
    const releaseUpload = deferred();
    const uploadReachedBackend = deferred();

    await page.route("**/api/v1/media/upload", async (route) => {
      const response = await route.fetch();
      uploadReachedBackend.resolve();
      await releaseUpload.promise;
      await route.fulfill({ response });
    });

    await page.goto(`/journals/${journal.id}/new`);
    await page.getByLabel("Entry title").fill(title);
    const editor = page.getByRole("textbox", { name: "Entry body" });
    await editor.click();
    await page.keyboard.type("Writing around a slow upload");

    const fileChooser = page.waitForEvent("filechooser");
    await page
      .getByRole("button", { name: "Add photo, video or audio" })
      .click();
    const chooseFiles = page.getByRole("button", { name: "Choose files" });
    if (await chooseFiles.isVisible()) await chooseFiles.click();
    const uploadResponse = page.waitForResponse(isUpload);
    await (await fileChooser).setFiles(PHOTO);
    await uploadReachedBackend.promise;
    await expect(
      page.getByRole("status", { name: "Uploading photo" }),
    ).toBeVisible();

    await page.getByRole("button", { name: "Done" }).click();
    await expect(page.getByRole("alert")).toHaveText(
      "Wait for uploads to finish before saving",
    );

    releaseUpload.resolve();
    await uploadResponse;
    await expect(editor.locator("img:not(.jv-upload__preview)")).toHaveCount(1);

    const saved = page.waitForResponse(
      (response) =>
        response.request().method() === "PUT" &&
        /^\/api\/v1\/moments\/[^/]+$/.test(new URL(response.url()).pathname),
    );
    await page.getByRole("button", { name: "Retry" }).click();
    await saved;

    await expect(page.getByRole("heading", { name: title })).toBeVisible();
    await expect(page.getByLabel("Entry content").locator("img")).toHaveCount(
      1,
    );
  });

  test("undoing a placeholder during upload deletes the uploaded media", async ({
    page,
    data,
  }) => {
    const journal = await data.journal();
    const releaseUpload = deferred();
    const uploadReachedBackend = deferred();
    let uploadedMediaId = "";

    await page.route("**/api/v1/media/upload", async (route) => {
      const response = await route.fetch();
      const body = await response.body();
      uploadedMediaId = (JSON.parse(body.toString()) as { id: string }).id;
      uploadReachedBackend.resolve();
      await releaseUpload.promise;
      await route.fulfill({ response, body });
    });

    await page.goto(`/journals/${journal.id}/new`);
    const editor = page.getByRole("textbox", { name: "Entry body" });
    await editor.click();

    const fileChooser = page.waitForEvent("filechooser");
    await page
      .getByRole("button", { name: "Add photo, video or audio" })
      .click();
    const chooseFiles = page.getByRole("button", { name: "Choose files" });
    if (await chooseFiles.isVisible()) await chooseFiles.click();
    const uploadResponse = page.waitForResponse(isUpload);
    await (await fileChooser).setFiles(PHOTO);
    await uploadReachedBackend.promise;
    await expect(
      page.getByRole("status", { name: "Uploading photo" }),
    ).toBeVisible();

    await page.getByRole("button", { name: "More actions" }).click();
    await page
      .getByRole("toolbar", { name: "More actions" })
      .getByRole("button", { name: "Undo" })
      .click();
    await expect(
      page.getByRole("status", { name: "Uploading photo" }),
    ).toHaveCount(0);

    const deleted = page.waitForResponse(
      (response) =>
        response.request().method() === "DELETE" &&
        new URL(response.url()).pathname === `/api/v1/media/${uploadedMediaId}`,
    );
    releaseUpload.resolve();
    await uploadResponse;
    expect((await deleted).ok()).toBe(true);

    await expect(editor.locator("img:not(.jv-upload__preview)")).toHaveCount(0);
    await expect(
      page.getByRole("status", { name: "Uploading photo" }),
    ).toHaveCount(0);
  });
});
