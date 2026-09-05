import "fake-indexeddb/auto";
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { QuillDelta } from "../../api/generated/types.gen";
import {
  closeDraftDb,
  DraftStorageError,
  draftRepository,
} from "./draftRepository";
import {
  DRAFT_DEBOUNCE_MS,
  type LocalDraftState,
  type UseLocalDraftOptions,
  useLocalDraft,
} from "./useLocalDraft";

const PHOTO = "0f8b1c2d-3e4f-4a5b-8c9d-0e1f2a3b4c5d";
const signed = (id: string, sig: string) =>
  `/api/v1/media/${id}/signed?uid=user-1&exp=1790000000&sig=${sig}`;

const KEY = "user-1:entry:entry-1";
const text = (value: string) => ({ ops: [{ insert: value }] }) as QuillDelta;

function setup(overrides: Partial<UseLocalDraftOptions> = {}) {
  const seen: { current: LocalDraftState | null } = { current: null };
  let options: UseLocalDraftOptions = {
    key: KEY,
    identity: { userId: "user-1", entryId: "entry-1" },
    journalId: "journal-1",
    title: "A rainy morning",
    promptId: null,
    baseUpdatedAt: "2026-08-24T08:30:00Z",
    dirty: true,
    getDocument: () => text("Coffee while the rain moved past.\n"),
    ...overrides,
  };

  function Probe() {
    seen.current = useLocalDraft(options);
    return null;
  }

  const view = render(<Probe />);
  return {
    seen,
    rerender: (next: Partial<UseLocalDraftOptions>) => {
      options = { ...options, ...next };
      view.rerender(<Probe />);
    },
    unmount: view.unmount,
  };
}

/**
 * A real macrotask. IndexedDB transactions settle on the runtime's own
 * scheduling, so the tests fake ONLY the debounce timer and keep a genuine tick
 * to let a write finish — faking everything stalls the database instead.
 */
const realSetTimeout = globalThis.setTimeout;
const tick = () =>
  new Promise<void>((resolve) => {
    realSetTimeout(resolve, 0);
  });

/** Lets any pending IndexedDB work complete. */
async function idle() {
  await act(async () => {
    for (let round = 0; round < 5; round += 1) await tick();
  });
}

/** Runs the debounce and lets the IndexedDB transaction settle. */
async function settle() {
  act(() => {
    vi.advanceTimersByTime(DRAFT_DEBOUNCE_MS);
  });
  await idle();
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
});

afterEach(async () => {
  // Unmount FIRST. Teardown is a flush point, so a component still mounted
  // would write a record after the database was cleared and leak it into the
  // next test. The global cleanup in src/test/setup.ts runs after this hook.
  cleanup();
  await idle();
  vi.useRealTimers();
  await closeDraftDb();
  await new Promise<void>((resolve) => {
    const request = indexedDB.deleteDatabase("journiv");
    request.onsuccess = () => resolve();
    request.onerror = () => resolve();
    request.onblocked = () => resolve();
  });
});

describe("debounce", () => {
  it("does not write before the debounce elapses", async () => {
    const { seen } = setup();
    act(() => seen.current?.schedule());

    act(() => {
      vi.advanceTimersByTime(DRAFT_DEBOUNCE_MS - 1);
    });
    await idle();
    expect(await draftRepository.read(KEY)).toBeNull();

    await settle();
    expect(await draftRepository.read(KEY)).not.toBeNull();
  });

  it("collapses a burst of typing into one write", async () => {
    const write = vi.spyOn(draftRepository, "write");
    const { seen } = setup();

    act(() => {
      seen.current?.schedule();
      seen.current?.schedule();
      seen.current?.schedule();
    });
    await settle();

    expect(write).toHaveBeenCalledTimes(1);
    write.mockRestore();
  });

  it("stores the document as it is at write time, not when scheduled", async () => {
    let body = "First\n";
    const { seen } = setup({ getDocument: () => text(body) });

    act(() => seen.current?.schedule());
    body = "First and second\n";
    await settle();

    expect(await draftRepository.read(KEY)).toMatchObject({
      contentDelta: { ops: [{ insert: "First and second\n" }] },
    });
  });

  it("writes nothing while there is nothing worth keeping", async () => {
    const { seen } = setup({ dirty: false });
    act(() => seen.current?.schedule());
    await settle();

    expect(await draftRepository.read(KEY)).toBeNull();
    expect(seen.current?.status).toBe("idle");
  });

  it("writes nothing until the signed-in user is known", async () => {
    // An unscoped record is worse than no record.
    const { seen, rerender } = setup({ key: null, identity: null });
    act(() => seen.current?.schedule());
    await settle();
    expect(await draftRepository.listForUser("user-1")).toEqual([]);

    rerender({ key: KEY, identity: { userId: "user-1", entryId: "entry-1" } });
    act(() => seen.current?.schedule());
    await settle();
    expect(await draftRepository.listForUser("user-1")).toHaveLength(1);
  });
});

describe("what reaches storage", () => {
  it("stores durable media ids, never a signed URL", async () => {
    setup({
      getDocument: () =>
        ({
          ops: [
            { insert: "Look\n" },
            { insert: { image: signed(PHOTO, "s3cr3t") } },
            { insert: "\n" },
          ],
        }) as QuillDelta,
    }).seen.current?.flush();
    await idle();

    const record = await draftRepository.read(KEY);
    const serialized = JSON.stringify(record);
    expect(serialized).toContain(PHOTO);
    for (const forbidden of ["sig=", "uid=", "exp=", "blob:", "/api/"]) {
      expect(serialized).not.toContain(forbidden);
    }
  });

  it("keeps an in-flight upload placeholder out of the record", async () => {
    const { seen } = setup({
      getDocument: () =>
        ({
          ops: [
            { insert: "Writing\n" },
            { insert: { "journiv-upload": { uploadId: "upload-1" } } },
            { insert: "\n" },
          ],
        }) as QuillDelta,
    });
    act(() => seen.current?.schedule());
    await settle();

    expect(JSON.stringify(await draftRepository.read(KEY))).not.toContain(
      "journiv-upload",
    );
  });

  it("carries the momentId a new-entry draft acquired from a media upload", async () => {
    const { seen } = setup({
      key: "user-1:new:local-1",
      identity: {
        userId: "user-1",
        momentId: "moment-9",
        entryId: "draft-entry-9",
        localDraftId: "local-1",
      },
    });
    act(() => seen.current?.schedule());
    await settle();

    expect(await draftRepository.read("user-1:new:local-1")).toMatchObject({
      momentId: "moment-9",
      entryId: "draft-entry-9",
      localDraftId: "local-1",
    });
  });

  it("stores both a selected prompt and an explicit prompt removal", async () => {
    const { seen, rerender } = setup({ promptId: "prompt-1" });
    act(() => seen.current?.schedule());
    await settle();
    expect((await draftRepository.read(KEY))?.promptId).toBe("prompt-1");

    rerender({ promptId: null });
    act(() => seen.current?.schedule());
    await settle();
    expect((await draftRepository.read(KEY))?.promptId).toBeNull();
  });

  it("refuses to store a draft that cannot represent the entry's media", async () => {
    const { seen } = setup({
      getDocument: () =>
        ({
          ops: [
            { insert: "Imported\n" },
            { insert: { image: "/media/legacy/holiday.jpg" } },
            { insert: "\n" },
          ],
        }) as QuillDelta,
    });
    act(() => seen.current?.schedule());
    await settle();

    // Nothing stored, and the status says so. A partial copy would drop the
    // photo on recovery, and the next Done would ask the backend to delete it.
    expect(seen.current?.status).toBe("unsupported");
    expect(await draftRepository.read(KEY)).toBeNull();
  });

  it("never overwrites a known-good draft with a lossy one", async () => {
    let body: QuillDelta = text("Complete and safe\n");
    const { seen } = setup({ getDocument: () => body });

    act(() => seen.current?.schedule());
    await settle();
    expect(seen.current?.status).toBe("saved");

    // The entry now holds something a draft cannot represent.
    body = {
      ops: [
        { insert: "Complete and safe\n" },
        { insert: { image: "/media/legacy/holiday.jpg" } },
        { insert: "\n" },
      ],
    } as QuillDelta;
    act(() => seen.current?.schedule());
    await settle();

    expect(seen.current?.status).toBe("unsupported");
    // The earlier, complete draft is untouched.
    expect(await draftRepository.read(KEY)).toMatchObject({
      contentDelta: { ops: [{ insert: "Complete and safe\n" }] },
    });
  });

  it("records an in-flight upload as omitted, so it can be reattached", async () => {
    const { seen } = setup({
      getDocument: () =>
        ({
          ops: [
            { insert: "Writing\n" },
            { insert: { "journiv-upload": { uploadId: "upload-1" } } },
            { insert: "\n" },
          ],
        }) as QuillDelta,
    });
    act(() => seen.current?.schedule());
    await settle();

    // A transient upload does not block the write — the writing is still worth
    // keeping — but it is recorded so nobody is told a photo was saved.
    expect(seen.current?.status).toBe("saved");
    expect(seen.current?.omittedTransientUploads).toBe(1);
    expect(await draftRepository.read(KEY)).toMatchObject({
      omittedTransientUploads: 1,
    });
  });

  it("survives a document the editor refuses to hand over", async () => {
    const { seen } = setup({
      getDocument: () => {
        throw new Error("Editor is not ready");
      },
    });
    act(() => seen.current?.schedule());
    await settle();

    expect(await draftRepository.read(KEY)).toBeNull();
    expect(seen.current?.status).toBe("idle");
  });
});

describe("lifecycle flush points", () => {
  it("writes when the page is hidden", async () => {
    setup();
    act(() => {
      Object.defineProperty(document, "visibilityState", {
        configurable: true,
        value: "hidden",
      });
      document.dispatchEvent(new Event("visibilitychange"));
    });
    await idle();

    expect(await draftRepository.read(KEY)).not.toBeNull();
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: "visible",
    });
  });

  it("does not write when the page merely becomes visible again", async () => {
    const write = vi.spyOn(draftRepository, "write");
    setup();
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    await idle();

    expect(write).not.toHaveBeenCalled();
    write.mockRestore();
  });

  it("writes on pagehide", async () => {
    setup();
    act(() => {
      window.dispatchEvent(new Event("pagehide"));
    });
    await idle();

    expect(await draftRepository.read(KEY)).not.toBeNull();
  });

  it("writes on teardown, so leaving the editor keeps the last keystrokes", async () => {
    const { seen, unmount } = setup();
    act(() => seen.current?.schedule());
    // Unmount before the debounce would have fired.
    act(() => {
      unmount();
    });
    await idle();

    expect(await draftRepository.read(KEY)).not.toBeNull();
  });

  it("stops listening once torn down", async () => {
    const write = vi.spyOn(draftRepository, "write");
    const { unmount } = setup();
    act(() => {
      unmount();
    });
    await idle();
    write.mockClear();

    act(() => {
      window.dispatchEvent(new Event("pagehide"));
    });
    await idle();
    expect(write).not.toHaveBeenCalled();
    write.mockRestore();
  });
});

describe("status", () => {
  it("only says saved after the write has actually landed", async () => {
    const { seen } = setup();
    expect(seen.current?.status).toBe("idle");

    act(() => seen.current?.schedule());
    await settle();
    expect(seen.current?.status).toBe("saved");
  });

  it("says so when a write fails, rather than looking saved", async () => {
    const write = vi
      .spyOn(draftRepository, "write")
      .mockRejectedValue(new DraftStorageError("no room"));
    const { seen } = setup();

    act(() => seen.current?.schedule());
    await settle();

    expect(seen.current?.status).toBe("failed");
    write.mockRestore();
  });

  it("distinguishes a browser that will not store anything", async () => {
    const write = vi
      .spyOn(draftRepository, "write")
      .mockRejectedValue(
        new DraftStorageError("blocked", { unavailable: true }),
      );
    const { seen } = setup();

    act(() => seen.current?.schedule());
    await settle();

    expect(seen.current?.status).toBe("unavailable");
    write.mockRestore();
  });

  it("announces the first stored draft exactly once", async () => {
    const onFirstStore = vi.fn();
    const { seen } = setup({ onFirstStore });

    act(() => seen.current?.schedule());
    await settle();
    act(() => seen.current?.schedule());
    await settle();

    expect(onFirstStore).toHaveBeenCalledTimes(1);
  });

  it("does not announce a first store that failed", async () => {
    const onFirstStore = vi.fn();
    const write = vi
      .spyOn(draftRepository, "write")
      .mockRejectedValueOnce(new DraftStorageError("nope"));
    const { seen } = setup({ onFirstStore });

    act(() => seen.current?.schedule());
    await settle();
    expect(onFirstStore).not.toHaveBeenCalled();

    write.mockRestore();
    act(() => seen.current?.schedule());
    await settle();
    expect(onFirstStore).toHaveBeenCalledTimes(1);
  });
});

describe("remove", () => {
  it("deletes the record and goes back to idle", async () => {
    const { seen } = setup();
    act(() => seen.current?.schedule());
    await settle();
    expect(await draftRepository.read(KEY)).not.toBeNull();

    await act(async () => {
      await seen.current?.remove();
    });
    await idle();

    expect(await draftRepository.read(KEY)).toBeNull();
    expect(seen.current?.status).toBe("idle");
  });

  it("cancels a write that was already scheduled", async () => {
    const { seen } = setup();
    act(() => seen.current?.schedule());
    await act(async () => {
      await seen.current?.remove();
    });
    await settle();
    expect(await draftRepository.read(KEY)).toBeNull();
  });

  it("is not undone by the teardown flush", async () => {
    // A confirmed save and an explicit discard both delete the record and then
    // leave the editor — and leaving tears this down. If teardown wrote the
    // record back, the entry the writer just saved (or threw away) would be
    // offered for recovery on the next visit.
    const { seen, unmount } = setup();
    act(() => seen.current?.schedule());
    await settle();
    await act(async () => {
      await seen.current?.remove();
    });

    unmount();
    await idle();

    expect(await draftRepository.read(KEY)).toBeNull();
  });

  it("keeps writing again once there is something new to keep", async () => {
    const { seen } = setup();
    await act(async () => {
      await seen.current?.remove();
    });
    act(() => seen.current?.schedule());
    await settle();
    expect(await draftRepository.read(KEY)).not.toBeNull();
  });
});
