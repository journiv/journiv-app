import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { MomentMediaResponse } from "../../api/generated/types.gen";
import { closeRecordingDb, recordingRepository } from "./recordingRepository";
import { useAnchorPruning } from "./useAnchorPruning";

const OLD = "2026-09-19T12:00:00.000Z";
const LISTED = Date.parse("2026-09-20T12:00:00.000Z");

const save = (
  mediaId: string,
  over: Partial<Parameters<typeof recordingRepository.saveAnchor>[0]> = {},
) =>
  recordingRepository.saveAnchor({
    mediaId,
    userId: "user-1",
    draftKey: "user-1:entry:e1",
    momentId: "moment-1",
    anchor: { index: 1, before: "b", after: "a" },
    capturedAt: OLD,
    ...over,
  });

const media = (id: string, upload_status = "completed") =>
  ({ id, upload_status, media_type: "audio" }) as MomentMediaResponse;

const state = (
  over: Partial<Parameters<typeof useAnchorPruning>[0]["media"]> = {},
) => ({
  items: [] as MomentMediaResponse[] | undefined,
  isSuccess: true,
  isFetching: false,
  fetchedAt: LISTED,
  ...over,
});

const run = (
  over: {
    momentId?: string | undefined;
    mediaCount?: number | undefined;
    media?: ReturnType<typeof state>;
  } = {},
) =>
  renderHook(() =>
    useAnchorPruning({
      momentId: "momentId" in over ? over.momentId : "moment-1",
      mediaCount: over.mediaCount,
      media: over.media ?? state(),
    }),
  );

/** Prune is fire-and-forget, so wait for the store to reach the expected state. */
const gone = (mediaId: string) =>
  waitFor(
    async () =>
      expect(await recordingRepository.readAnchor(mediaId)).toBeNull(),
    { timeout: 10_000 },
  );
const settle = () => new Promise((resolve) => setTimeout(resolve, 60));

describe("useAnchorPruning", () => {
  it("drops the anchor of media that is no longer on the Moment", async () => {
    await save("gone");
    await save("kept");
    run({ media: state({ items: [media("kept")] }) });

    await gone("gone");
    expect(await recordingRepository.readAnchor("kept")).not.toBeNull();
  });

  it("never prunes an item that is still pending or processing", async () => {
    await save("uploading-1");
    await save("processing-1");
    await save("gone");
    run({
      media: state({
        items: [
          media("uploading-1", "pending"),
          media("processing-1", "processing"),
        ],
      }),
    });

    await gone("gone");
    expect(await recordingRepository.readAnchor("uploading-1")).not.toBeNull();
    expect(await recordingRepository.readAnchor("processing-1")).not.toBeNull();
  });

  it("keeps a fresh anchor whose media row the list has not caught up to", async () => {
    // Captured seconds before this list was fetched: the row may simply be new.
    await save("just-uploaded", {
      capturedAt: new Date(LISTED - 5_000).toISOString(),
    });
    run({ media: state({ items: [] }) });
    await settle();
    expect(
      await recordingRepository.readAnchor("just-uploaded"),
    ).not.toBeNull();
  });

  it.each([
    ["while the list is loading", { items: undefined, isSuccess: false }],
    ["while the list is refetching", { isFetching: true }],
    ["when the list failed to load", { items: undefined, isSuccess: false }],
  ])("does not prune %s", async (_label, over) => {
    await save("anchored");
    run({ media: state(over) });
    await settle();
    expect(await recordingRepository.readAnchor("anchored")).not.toBeNull();
  });

  it("treats a Moment with no media as an empty list", async () => {
    // The reader never loads a list for a Moment with media_count 0, which is
    // exactly what remains after the last recording is removed.
    await save("last-one");
    run({
      mediaCount: 0,
      media: state({ items: undefined, isSuccess: false, fetchedAt: 0 }),
    });
    await gone("last-one");
  });

  it("does not treat an unknown count as zero", async () => {
    await save("anchored");
    run({
      mediaCount: undefined,
      media: state({ items: undefined, isSuccess: false, fetchedAt: 0 }),
    });
    await settle();
    expect(await recordingRepository.readAnchor("anchored")).not.toBeNull();
  });

  it("only touches the Moment it was given", async () => {
    await save("mine", { momentId: "moment-1" });
    await save("theirs", { momentId: "moment-2" });
    run({ media: state({ items: [] }) });
    await gone("mine");
    expect(await recordingRepository.readAnchor("theirs")).not.toBeNull();
  });

  it("does nothing without a Moment", async () => {
    await save("anchored");
    run({ momentId: undefined, media: state({ items: [] }) });
    await settle();
    expect(await recordingRepository.readAnchor("anchored")).not.toBeNull();
  });

  it("stays silent when IndexedDB is unavailable", async () => {
    // A rejection nobody handles would fail this run, so "silent" is checked by
    // the run itself as well as by the assertions below.
    await closeRecordingDb(); // drop any cached connection
    const original = globalThis.indexedDB;
    const prune = vi.spyOn(recordingRepository, "pruneAnchors");
    // @ts-expect-error simulating a browser with no IndexedDB
    globalThis.indexedDB = undefined;
    try {
      expect(() => run({ media: state({ items: [] }) })).not.toThrow();
      await waitFor(() => expect(prune).toHaveBeenCalledTimes(1));
      // It really did fail, as unavailable storage — and nothing surfaced it.
      await expect(prune.mock.results[0]?.value).rejects.toMatchObject({
        unavailable: true,
      });
    } finally {
      prune.mockRestore();
      globalThis.indexedDB = original;
      await closeRecordingDb();
    }
  });
});
