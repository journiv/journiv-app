import "fake-indexeddb/auto";
import { afterEach, describe, expect, it } from "vitest";
import {
  ANCHOR_PRUNE_GRACE_MS,
  blobToArrayBuffer,
  buildRecordingFile,
  closeRecordingDb,
  recordingFileName,
  recordingRepository,
  RecordingStorageError,
  type RecordingSession,
} from "./recordingRepository";

const session = (over: Partial<RecordingSession> = {}): RecordingSession => ({
  id: "rec-1",
  userId: "user-1",
  draftKey: "user-1:new:abc",
  mimeType: "audio/webm;codecs=opus",
  startedAt: "2026-09-19T14:30:00.000Z",
  updatedAt: "2026-09-19T14:30:00.000Z",
  durationMs: 0,
  chunkCount: 0,
  status: "recording",
  anchor: { index: 4, before: "before", after: "after" },
  ...over,
});

const bytes = (...values: number[]) => new Uint8Array(values).buffer;

async function readAll(file: File) {
  return new Uint8Array(await blobToArrayBuffer(file));
}

afterEach(async () => {
  await closeRecordingDb();
  await new Promise<void>((resolve) => {
    const request = indexedDB.deleteDatabase("journiv-recordings");
    request.onsuccess = () => resolve();
    request.onerror = () => resolve();
    request.onblocked = () => resolve();
  });
});

describe("recordingRepository", () => {
  it("persists chunks as they arrive and assembles them in order", async () => {
    const s = session();
    await recordingRepository.createSession(s);
    // Arrival order is not index order: assembly must sort.
    await recordingRepository.appendChunk(s.id, 1, bytes(3, 4));
    await recordingRepository.appendChunk(s.id, 0, bytes(1, 2));
    await recordingRepository.appendChunk(s.id, 2, bytes(5));

    const file = await recordingRepository.assemble(s);
    expect(file).not.toBeNull();
    expect(Array.from(await readAll(file as File))).toEqual([1, 2, 3, 4, 5]);
  });

  it("builds a real File with the recorder's MIME and a dated name", async () => {
    const s = session({ mimeType: "audio/mp4" });
    await recordingRepository.createSession(s);
    await recordingRepository.appendChunk(s.id, 0, bytes(9));
    const file = (await recordingRepository.assemble(s)) as File;
    expect(file).toBeInstanceOf(File);
    expect(file.type).toBe("audio/mp4");
    expect(file.name).toMatch(/^voice-note-\d{4}-\d{2}-\d{2}-\d{4}\.m4a$/);
  });

  it("merges chunks that never reached storage so nothing is lost", async () => {
    const s = session();
    await recordingRepository.createSession(s);
    await recordingRepository.appendChunk(s.id, 0, bytes(1));
    await recordingRepository.appendChunk(s.id, 2, bytes(3));
    const missing = new Map<number, Blob>([
      [1, new Blob([new Uint8Array([2])])],
    ]);
    const file = (await recordingRepository.assemble(s, missing)) as File;
    expect(Array.from(await readAll(file))).toEqual([1, 2, 3]);
  });

  it("returns null when there is nothing to assemble", async () => {
    const s = session();
    await recordingRepository.createSession(s);
    expect(await recordingRepository.assemble(s)).toBeNull();
  });

  it("refuses a stopped recording with a missing chunk or a hole", async () => {
    const s = session({ chunkCount: 3, status: "stopped" });
    await recordingRepository.createSession(s);
    await recordingRepository.appendChunk(s.id, 0, bytes(1));
    await recordingRepository.appendChunk(s.id, 2, bytes(3));
    expect(await recordingRepository.assemble(s)).toBeNull();
    await recordingRepository.appendChunk(s.id, 3, bytes(4));
    expect(await recordingRepository.assemble(s)).toBeNull();
  });

  it("survives a simulated reload: a fresh connection still sees the session", async () => {
    const s = session();
    await recordingRepository.createSession(s);
    await recordingRepository.appendChunk(s.id, 0, bytes(7, 7));
    await recordingRepository.updateSession(s.id, {
      durationMs: 4000,
      chunkCount: 1,
    });

    await closeRecordingDb(); // the page is gone; only the database remains

    const found = await recordingRepository.listUnfinished("user-1");
    expect(found).toHaveLength(1);
    expect(found[0]).toMatchObject({
      id: s.id,
      durationMs: 4000,
      chunkCount: 1,
    });
    const file = (await recordingRepository.assemble(
      found[0] as RecordingSession,
    )) as File;
    expect(Array.from(await readAll(file))).toEqual([7, 7]);
  });

  it("keeps the staged copy until it is explicitly deleted", async () => {
    const s = session();
    await recordingRepository.createSession(s);
    await recordingRepository.appendChunk(s.id, 0, bytes(1));
    await recordingRepository.updateSession(s.id, { status: "stopped" });

    // e.g. the upload failed: nothing deleted it, so it is still recoverable.
    expect(await recordingRepository.listUnfinished("user-1")).toHaveLength(1);

    await recordingRepository.deleteSession(s.id);
    expect(await recordingRepository.listUnfinished("user-1")).toHaveLength(0);
    expect(await recordingRepository.assemble(s)).toBeNull();
    // Deleting twice is safe.
    await expect(
      recordingRepository.deleteSession(s.id),
    ).resolves.toBeUndefined();
  });

  it("only lists a user's own recordings, newest first", async () => {
    await recordingRepository.createSession(
      session({ id: "a", startedAt: "2026-09-19T10:00:00.000Z" }),
    );
    await recordingRepository.createSession(
      session({ id: "b", startedAt: "2026-09-19T12:00:00.000Z" }),
    );
    await recordingRepository.createSession(
      session({ id: "c", userId: "user-2" }),
    );
    const own = await recordingRepository.listUnfinished("user-1");
    expect(own.map((s) => s.id)).toEqual(["b", "a"]);
  });

  it("does not resurrect a session that was deleted while updating", async () => {
    await recordingRepository.updateSession("gone", { durationMs: 1 });
    expect(await recordingRepository.readSession("gone")).toBeNull();
  });

  it("keeps a transcript anchor per media id after the audio is deleted", async () => {
    const s = session();
    await recordingRepository.createSession(s);
    await recordingRepository.appendChunk(s.id, 0, bytes(1));
    await recordingRepository.saveAnchor({
      mediaId: "media-1",
      userId: "user-1",
      draftKey: s.draftKey,
      momentId: "moment-1",
      anchor: s.anchor,
      capturedAt: s.startedAt,
    });
    await recordingRepository.deleteSession(s.id);

    expect(await recordingRepository.readAnchor("media-1")).toMatchObject({
      momentId: "moment-1",
      anchor: s.anchor,
    });
    await recordingRepository.deleteAnchor("media-1");
    expect(await recordingRepository.readAnchor("media-1")).toBeNull();
  });
});

describe("pruneAnchors", () => {
  const NOW = Date.parse("2026-09-20T12:00:00.000Z");
  const OLD = "2026-09-19T12:00:00.000Z"; // a day before NOW, well past the grace

  const anchor = (
    mediaId: string,
    over: Partial<Parameters<typeof recordingRepository.saveAnchor>[0]> = {},
  ) =>
    recordingRepository.saveAnchor({
      mediaId,
      userId: "user-1",
      draftKey: "user-1:entry:e1",
      momentId: "moment-1",
      anchor: { index: 3, before: "b", after: "a" },
      capturedAt: OLD,
      ...over,
    });

  it("removes an anchor whose media is gone and keeps the rest", async () => {
    await anchor("gone");
    await anchor("present");
    await anchor("elsewhere", { momentId: "moment-2" });

    const removed = await recordingRepository.pruneAnchors(
      "moment-1",
      new Set(["present"]),
      NOW,
    );

    expect(removed).toBe(1);
    expect(await recordingRepository.readAnchor("gone")).toBeNull();
    expect(await recordingRepository.readAnchor("present")).not.toBeNull();
    // Another Moment's anchors are never touched, whatever the list says.
    expect(await recordingRepository.readAnchor("elsewhere")).not.toBeNull();
  });

  it("removes every anchor of a Moment whose media list is empty", async () => {
    await anchor("a");
    await anchor("b");
    expect(
      await recordingRepository.pruneAnchors("moment-1", new Set(), NOW),
    ).toBe(2);
    expect(await recordingRepository.readAnchor("a")).toBeNull();
    expect(await recordingRepository.readAnchor("b")).toBeNull();
  });

  it("keeps a fresh anchor even when the list does not have its media", async () => {
    // An upload can finish while a list request is in flight; the list then
    // legitimately lacks a media row that exists.
    const justNow = new Date(NOW - ANCHOR_PRUNE_GRACE_MS + 1000).toISOString();
    await anchor("fresh", { capturedAt: justNow });
    expect(
      await recordingRepository.pruneAnchors("moment-1", new Set(), NOW),
    ).toBe(0);
    expect(await recordingRepository.readAnchor("fresh")).not.toBeNull();
  });

  it("keeps an anchor captured after the list was fetched", async () => {
    await anchor("newer", { capturedAt: "2026-09-20T12:30:00.000Z" });
    expect(
      await recordingRepository.pruneAnchors("moment-1", new Set(), NOW),
    ).toBe(0);
    expect(await recordingRepository.readAnchor("newer")).not.toBeNull();
  });

  it("keeps an anchor whose age it cannot read", async () => {
    await anchor("odd", { capturedAt: "not a date" });
    expect(
      await recordingRepository.pruneAnchors("moment-1", new Set(), NOW),
    ).toBe(0);
    expect(await recordingRepository.readAnchor("odd")).not.toBeNull();
  });

  it("is not affected by staged audio being deleted", async () => {
    // The anchor deliberately outlives the staged copy; only the media ends it.
    const s = session();
    await recordingRepository.createSession(s);
    await anchor("media-9", { draftKey: s.draftKey });
    await recordingRepository.deleteSession(s.id);
    expect(
      await recordingRepository.pruneAnchors(
        "moment-1",
        new Set(["media-9"]),
        NOW,
      ),
    ).toBe(0);
    expect(await recordingRepository.readAnchor("media-9")).not.toBeNull();
  });

  it("rejects as unavailable, rather than pretending, when IndexedDB is missing", async () => {
    const original = globalThis.indexedDB;
    // @ts-expect-error simulating a browser with no IndexedDB
    globalThis.indexedDB = undefined;
    try {
      await closeRecordingDb();
      const failure = await recordingRepository
        .pruneAnchors("moment-1", new Set(), NOW)
        .catch((error: unknown) => error);
      expect(failure).toBeInstanceOf(RecordingStorageError);
      expect((failure as RecordingStorageError).unavailable).toBe(true);
    } finally {
      globalThis.indexedDB = original;
      await closeRecordingDb();
    }
  });
});

describe("reads before anything has been recorded", () => {
  const databaseNames = async () =>
    (await indexedDB.databases()).map((info) => info.name);

  it("do not create the database", async () => {
    // Opening an entry looks for unfinished recordings and stale anchors; that
    // must not leave an empty database behind for someone who never records.
    expect(await recordingRepository.listUnfinished("user-1")).toEqual([]);
    expect(
      await recordingRepository.pruneAnchors("moment-1", new Set(), Date.now()),
    ).toBe(0);
    expect(await databaseNames()).not.toContain("journiv-recordings");
  });

  it("still find what was recorded once the database exists", async () => {
    await recordingRepository.createSession(session());
    expect(await databaseNames()).toContain("journiv-recordings");
    expect(await recordingRepository.listUnfinished("user-1")).toHaveLength(1);
    await closeRecordingDb(); // a fresh page load: no cached connection
    expect(await recordingRepository.listUnfinished("user-1")).toHaveLength(1);
  });

  it("fall back to opening when the browser cannot list databases", async () => {
    const original = indexedDB.databases;
    // @ts-expect-error simulating a browser without IDBFactory.databases()
    indexedDB.databases = undefined;
    try {
      await recordingRepository.createSession(session());
      await closeRecordingDb();
      expect(await recordingRepository.listUnfinished("user-1")).toHaveLength(
        1,
      );
    } finally {
      indexedDB.databases = original;
    }
  });
});

describe("unavailable storage", () => {
  it("reports unavailable rather than pretending it stored something", async () => {
    const original = globalThis.indexedDB;
    // @ts-expect-error simulating a browser with no IndexedDB
    globalThis.indexedDB = undefined;
    try {
      await closeRecordingDb();
      const failure = await recordingRepository
        .createSession(session())
        .catch((error: unknown) => error);
      expect(failure).toBeInstanceOf(RecordingStorageError);
      expect((failure as RecordingStorageError).unavailable).toBe(true);
    } finally {
      globalThis.indexedDB = original;
      await closeRecordingDb();
    }
  });
});

describe("file naming", () => {
  it("names by container, not by request", () => {
    expect(
      recordingFileName({
        mimeType: "audio/webm;codecs=opus",
        startedAt: "2026-09-19T14:30:00",
      }),
    ).toMatch(/\.webm$/);
    expect(
      recordingFileName({
        mimeType: "audio/mp4",
        startedAt: "2026-09-19T14:30:00",
      }),
    ).toMatch(/\.m4a$/);
  });

  it("tolerates an unparseable start time", () => {
    expect(
      recordingFileName({ mimeType: "audio/webm", startedAt: "nope" }),
    ).toBe("voice-note-recording.webm");
  });

  it("returns null for no chunks", () => {
    expect(
      buildRecordingFile(
        { mimeType: "audio/webm", startedAt: "2026-09-19T14:30:00" },
        [],
      ),
    ).toBeNull();
  });
});
