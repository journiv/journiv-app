import type { Client } from "@/api/generated/client";
import {
  getMomentMediaApiV1MomentsMomentIdMediaGet,
  uploadMediaApiV1MediaUploadPost,
} from "@/api/generated";
import type { MomentMediaResponse } from "@/api/generated/types.gen";
import { expect, test } from "../fixtures/test";

// One second of silence, encoded with `ffmpeg -f lavfi -i anullsrc=r=8000:cl=mono
// -t 1 -b:a 8k -f mp3`. MP3 because libmagic sniffs WAV as `audio/x-wav`, which
// the backend allowlist does not carry. Real enough for the sniffing, duration
// probe and waveform extraction without a binary fixture in the repository.
const SILENT_MP3 = Buffer.from(
  "SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjU5LjI3LjEwMAAAAAAAAAAAAAAA/+MYxAAAAANIAAAAAExBTUUzLjEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVMQU1FMy4xMDBVVVVVVVVVVVVV/+MYxDsAAANIAAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVMQU1FMy4xMDBVVVVVVVVVVVVV/+MYxHYAAANIAAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVMQU1FMy4xMDBVVVVVVVVVVVVV/+MYxLEAAANIAAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVMQU1FMy4xMDBVVVVVVVVVVVVV/+MYxMQAAANIAAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVMQU1FMy4xMDBVVVVVVVVVVVVV/+MYxMQAAANIAAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVMQU1FMy4xMDBVVVVVVVVVVVVV/+MYxMQAAANIAAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVMQU1FMy4xMDBVVVVVVVVVVVVV/+MYxMQAAANIAAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVMQU1FMy4xMDBVVVVVVVVVVVVV/+MYxMQAAANIAAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVMQU1FMy4xMDBVVVVVVVVVVVVV/+MYxMQAAANIAAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVMQU1FMy4xMDBVVVVVVVVVVVVV/+MYxMQAAANIAAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVMQU1FMy4xMDBVVVVVVVVVVVVV/+MYxMQAAANIAAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVMQU1FMy4xMDBVVVVVVVVVVVVV/+MYxMQAAANIAAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV/+MYxMQAAANIAAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV/+MYxMQAAANIAAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV/+MYxMQAAANIAAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV",
  "base64",
);

async function listMedia(
  api: Client,
  momentId: string,
): Promise<MomentMediaResponse[]> {
  const result = await getMomentMediaApiV1MomentsMomentIdMediaGet({
    client: api,
    path: { moment_id: momentId },
  });
  if (result.error !== undefined || !result.data)
    throw new Error(
      `[e2e] GET /api/v1/moments/${momentId}/media returned HTTP ${result.response?.status}`,
    );
  return result.data;
}

let clipCounter = 0;

/** Uploads a clip and waits until the backend has finished processing it, so
 *  the surfaces under test offer it for deletion. The backend deduplicates a
 *  user's uploads by checksum and keeps one copy per moment, so each clip gets
 *  a unique ID3v1 trailer. Decoders ignore the trailer. */
async function attachAudio(
  api: Client,
  momentId: string,
  altText?: string,
): Promise<string> {
  clipCounter += 1;
  const trailer = Buffer.alloc(128);
  trailer.write(`TAGclip ${clipCounter}`, "latin1");
  const uploaded = await uploadMediaApiV1MediaUploadPost({
    client: api,
    body: {
      file: new File([Buffer.concat([SILENT_MP3, trailer])], "clip.mp3", {
        type: "audio/mpeg",
      }),
      moment_id: momentId,
      ...(altText ? { alt_text: altText } : {}),
    },
  });
  if (uploaded.error !== undefined || !uploaded.data)
    throw new Error(
      `[e2e] POST /api/v1/media/upload returned HTTP ${uploaded.response?.status}: ${JSON.stringify(uploaded.error)}`,
    );
  const mediaId = uploaded.data.id;
  await expect
    .poll(
      async () =>
        (await listMedia(api, momentId)).find((item) => item.id === mediaId)
          ?.upload_status,
      { timeout: 30_000 },
    )
    .toBe("completed");
  return mediaId;
}

const isDelete = (response: {
  url(): string;
  request(): { method(): string };
}) =>
  response.request().method() === "DELETE" &&
  new URL(response.url()).pathname.startsWith("/api/v1/media/");

test.describe("deleting an audio clip", () => {
  test("from the reader removes the only clip and its menu action", async ({
    page,
    api,
    data,
  }) => {
    const journal = await data.journal();
    const moment = await data.moment({ journalId: journal.id });
    await attachAudio(api, moment.id);

    await page.goto(`/journals/${journal.id}/${moment.id}`);
    await expect(page.getByRole("slider", { name: /^Seek / })).toBeVisible();

    await page.getByRole("button", { name: "Moment actions" }).click();
    await page.getByRole("menuitem", { name: "Delete audio clip…" }).click();
    const dialog = page.getByRole("alertdialog");
    await expect(dialog).toContainText("Delete this audio clip?");
    const deleted = page.waitForResponse(isDelete);
    await dialog.getByRole("button", { name: "Delete audio clip" }).click();
    expect((await deleted).ok()).toBe(true);

    await expect(dialog).toBeHidden();
    // The dialog closes after the Moment refetch, so the clip is already gone.
    expect(await page.getByRole("slider", { name: /^Seek / }).count()).toBe(0);
    await expect(page.getByText("Media couldn’t be loaded")).toHaveCount(0);

    await page.getByRole("button", { name: "Moment actions" }).click();
    await expect(
      page.getByRole("menuitem", { name: /Delete audio clip/ }),
    ).toHaveCount(0);
    await page.keyboard.press("Escape");

    expect(await listMedia(api, moment.id)).toEqual([]);
  });

  test("from the reader names each clip when there are several", async ({
    page,
    api,
    data,
  }) => {
    const journal = await data.journal();
    const moment = await data.moment({ journalId: journal.id });
    await attachAudio(api, moment.id, "Ferry horn");
    await attachAudio(api, moment.id);

    await page.goto(`/journals/${journal.id}/${moment.id}`);
    await expect(page.getByRole("slider", { name: /^Seek / })).toHaveCount(2);

    await page.getByRole("button", { name: "Moment actions" }).click();
    await expect(
      page.getByRole("menuitem", { name: "Delete audio clip 1 (Ferry horn)…" }),
    ).toBeVisible();
    await expect(
      page.getByRole("menuitem", {
        name: /^Delete audio clip 2 \(\d:\d\d\)…$/,
      }),
    ).toBeVisible();
    await page
      .getByRole("menuitem", { name: "Delete audio clip 1 (Ferry horn)…" })
      .click();
    const dialog = page.getByRole("alertdialog");
    await expect(dialog).toContainText("Delete audio clip 1 (Ferry horn)?");
    const deleted = page.waitForResponse(isDelete);
    await dialog.getByRole("button", { name: "Delete audio clip" }).click();
    expect((await deleted).ok()).toBe(true);

    await expect(page.getByRole("slider", { name: /^Seek / })).toHaveCount(1);
    await page.getByRole("button", { name: "Moment actions" }).click();
    await expect(
      page.getByRole("menuitem", { name: "Delete audio clip…" }),
    ).toBeVisible();
    await page.keyboard.press("Escape");

    const remaining = await listMedia(api, moment.id);
    expect(remaining).toHaveLength(1);
    expect(remaining[0].alt_text ?? null).toBeNull();
  });

  test("the editor loads no media list for a Moment without media", async ({
    page,
    data,
  }) => {
    const journal = await data.journal();
    const moment = await data.moment({ journalId: journal.id });
    const mediaListRequests: string[] = [];
    page.on("request", (request) => {
      const { pathname } = new URL(request.url());
      if (pathname === `/api/v1/moments/${moment.id}/media`)
        mediaListRequests.push(pathname);
    });

    await page.goto(`/journals/${journal.id}/${moment.id}/edit`);
    await expect(page.getByRole("button", { name: "Done" })).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Voice note" }),
    ).toBeVisible();

    expect(mediaListRequests).toEqual([]);
    await expect(
      page.getByRole("region", { name: "Attached to this moment" }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("status", { name: "Loading media" }),
    ).toHaveCount(0);
  });

  test("from the editor tray, down to an empty tray that disappears", async ({
    page,
    api,
    data,
  }) => {
    const journal = await data.journal();
    const moment = await data.moment({ journalId: journal.id });
    await attachAudio(api, moment.id);
    await attachAudio(api, moment.id);

    await page.goto(`/journals/${journal.id}/${moment.id}/edit`);
    const tray = page.getByRole("region", { name: "Attached to this moment" });
    const deleteButtons = tray.getByRole("button", {
      name: "Delete voice note",
    });
    await expect(deleteButtons).toHaveCount(2);

    for (const remaining of [1, 0]) {
      await deleteButtons.first().click();
      const dialog = page.getByRole("alertdialog");
      await expect(dialog).toContainText("Delete this voice note?");
      const deleted = page.waitForResponse(isDelete);
      await dialog.getByRole("button", { name: "Delete voice note" }).click();
      expect((await deleted).ok()).toBe(true);
      await expect(dialog).toBeHidden();
      expect(await deleteButtons.count()).toBe(remaining);
    }

    await expect(tray).toHaveCount(0);
    await expect(page.getByRole("alert")).toHaveCount(0);
    expect(await listMedia(api, moment.id)).toEqual([]);

    await page.getByRole("button", { name: "Done" }).click();
    await expect(page).toHaveURL(
      new RegExp(`/journals/${journal.id}/${moment.id}(\\?.*)?$`),
    );
    await expect(page.getByRole("slider", { name: /^Seek / })).toHaveCount(0);
  });
});
