import "fake-indexeddb/auto";
import { openDB } from "idb";
import { afterEach, describe, expect, it } from "vitest";
import type { DurableDraftDelta } from "./draftCanonical";
import {
  closeDraftDb,
  DRAFT_DB_VERSION,
  DRAFT_STORE,
  DRAFT_USER_INDEX,
  draftRepository,
  DraftStorageError,
  type EditorDraftV1,
  upgradeDraftDb,
} from "./draftRepository";

const body = (text: string) =>
  ({ ops: [{ insert: text }] }) as unknown as DurableDraftDelta;

const record = (over: Partial<EditorDraftV1> = {}): EditorDraftV1 => ({
  key: "user-1:entry:entry-1",
  userId: "user-1",
  entryId: "entry-1",
  journalId: "journal-1",
  title: "A rainy morning",
  contentDelta: body("Coffee while the rain moved past.\n"),
  baseUpdatedAt: "2026-08-24T08:30:00Z",
  modifiedAt: "2026-08-24T08:31:00Z",
  dirty: true,
  ...over,
});

afterEach(async () => {
  await closeDraftDb();
  await new Promise<void>((resolve) => {
    const request = indexedDB.deleteDatabase("journiv");
    request.onsuccess = () => resolve();
    request.onerror = () => resolve();
    request.onblocked = () => resolve();
  });
});

describe("draftRepository", () => {
  it("writes, reads back and deletes a draft", async () => {
    expect(await draftRepository.read("user-1:entry:entry-1")).toBeNull();

    await draftRepository.write(record());
    expect(await draftRepository.read("user-1:entry:entry-1")).toEqual(
      record(),
    );

    await draftRepository.delete("user-1:entry:entry-1");
    expect(await draftRepository.read("user-1:entry:entry-1")).toBeNull();
  });

  it("overwrites the record under one key rather than accumulating", async () => {
    await draftRepository.write(record({ title: "First" }));
    await draftRepository.write(record({ title: "Second" }));

    expect((await draftRepository.read("user-1:entry:entry-1"))?.title).toBe(
      "Second",
    );
    expect(await draftRepository.listForUser("user-1")).toHaveLength(1);
  });

  it("deleting a key that is not there is not an error", async () => {
    await expect(
      draftRepository.delete("user-1:new:nothing"),
    ).resolves.toBeUndefined();
  });

  it("preserves the momentId a new-entry draft acquired from a media upload", async () => {
    await draftRepository.write(
      record({
        key: "user-1:new:local-1",
        entryId: "draft-entry-9",
        momentId: "moment-9",
        localDraftId: "local-1",
      }),
    );

    const stored = await draftRepository.read("user-1:new:local-1");
    expect(stored?.momentId).toBe("moment-9");
    expect(stored?.entryId).toBe("draft-entry-9");
    expect(stored?.localDraftId).toBe("local-1");
  });

  it("survives a close and reopen, which is the whole point", async () => {
    await draftRepository.write(record());
    await closeDraftDb();

    expect(await draftRepository.read("user-1:entry:entry-1")).toEqual(
      record(),
    );
  });
});

describe("user scoping", () => {
  it("never shows one user's drafts to another", async () => {
    await draftRepository.write(record());
    await draftRepository.write(
      record({
        key: "user-2:entry:entry-2",
        userId: "user-2",
        entryId: "entry-2",
        title: "Someone else's writing",
      }),
    );

    const mine = await draftRepository.listForUser("user-1");
    expect(mine).toHaveLength(1);
    expect(mine[0]?.title).toBe("A rainy morning");

    const theirs = await draftRepository.listForUser("user-2");
    expect(theirs).toHaveLength(1);
    expect(theirs[0]?.title).toBe("Someone else's writing");

    expect(await draftRepository.listForUser("user-3")).toEqual([]);
  });

  it("keeps both users' drafts across a sign-out and sign-in on one device", async () => {
    // Phase D never deletes on logout: sign-out here is frequently involuntary
    // (an expired token clears the session), and erasing would destroy the
    // exact work this feature protects. Isolation is what keeps accounts apart.
    await draftRepository.write(record());
    await draftRepository.write(
      record({ key: "user-2:entry:e2", userId: "user-2", entryId: "e2" }),
    );
    await closeDraftDb();

    expect(await draftRepository.listForUser("user-1")).toHaveLength(1);
    expect(await draftRepository.listForUser("user-2")).toHaveLength(1);
  });

  it("can remove one user's drafts without touching another's", async () => {
    await draftRepository.write(record());
    await draftRepository.write(
      record({ key: "user-1:new:local-2", localDraftId: "local-2" }),
    );
    await draftRepository.write(
      record({ key: "user-2:entry:e2", userId: "user-2", entryId: "e2" }),
    );

    await draftRepository.deleteForUser("user-1");

    expect(await draftRepository.listForUser("user-1")).toEqual([]);
    expect(await draftRepository.listForUser("user-2")).toHaveLength(1);
  });
});

describe("schema", () => {
  it("creates the store and the user index on a fresh database", async () => {
    await draftRepository.write(record());
    await closeDraftDb();

    const db = await openDB("journiv", DRAFT_DB_VERSION);
    try {
      expect([...db.objectStoreNames]).toContain(DRAFT_STORE);
      const tx = db.transaction(DRAFT_STORE);
      expect([...tx.store.indexNames]).toContain(DRAFT_USER_INDEX);
      expect(tx.store.keyPath).toBe("key");
    } finally {
      db.close();
    }
  });

  it("opening an existing database again does not clear it", async () => {
    await draftRepository.write(record());
    await closeDraftDb();
    // A second open at the same version must not re-run creation destructively.
    await draftRepository.write(
      record({ key: "user-1:new:local-3", localDraftId: "local-3" }),
    );

    expect(await draftRepository.listForUser("user-1")).toHaveLength(2);
  });

  it("upgrade is a no-op when the store already exists", () => {
    // Guards the v1 -> v2 path: the `case 0` branch must never recreate a store
    // an earlier version already made, or a later upgrade would drop drafts.
    const created: string[] = [];
    const stub = {
      objectStoreNames: { contains: () => true },
      createObjectStore: (name: string) => {
        created.push(name);
        return { createIndex: () => undefined };
      },
      // biome-ignore lint/suspicious/noExplicitAny: minimal stand-in for IDBPDatabase.
    } as any;

    upgradeDraftDb(stub, 0);
    upgradeDraftDb(stub, 1);
    expect(created).toEqual([]);
  });
});

describe("when the browser will not store anything", () => {
  it("reports storage as unavailable instead of failing silently", async () => {
    await closeDraftDb();
    const real = globalThis.indexedDB;
    // Private browsing, blocked site data, or a runtime with no IndexedDB.
    Object.defineProperty(globalThis, "indexedDB", {
      configurable: true,
      value: undefined,
    });

    try {
      const failure = await draftRepository
        .write(record())
        .then(() => null)
        .catch((error: unknown) => error);

      expect(failure).toBeInstanceOf(DraftStorageError);
      expect((failure as DraftStorageError).unavailable).toBe(true);
    } finally {
      Object.defineProperty(globalThis, "indexedDB", {
        configurable: true,
        value: real,
      });
    }
  });
});
