import {
  type DBSchema,
  type IDBPDatabase,
  type IDBPTransaction,
  openDB,
} from "idb";
import type { DurableDraftDelta } from "./draftCanonical";

/**
 * Local persistence for unsaved writing. Nothing more.
 *
 * This module is deliberately ignorant of Journiv's media pipeline: it stores a
 * `DurableDraftDelta` and has no idea that media signing exists, that URLs
 * expire, or how a document is translated on the way in and out. That
 * translation lives in `draftCanonical.ts`, and the editor performs it before
 * calling here. The type import is the enforcement — a hydrated `QuillDelta`
 * carrying signed URLs will not typecheck as a record field.
 *
 * If this file ever needs to match a URL, the boundary has been broken.
 */

/** The record the plan specifies (build plan §6), plus the protection count. */
export interface EditorDraftV1 {
  /** `${userId}:entry:${id}` | `${userId}:moment:${id}` | `${userId}:new:${id}` */
  key: string;
  userId: string;
  entryId?: string;
  /**
   * The server Moment this draft belongs to, when one exists. Load-bearing:
   * a new entry that attached media already owns a draft Moment, and recovery
   * must continue using it or Done would create a second one and orphan the
   * media.
   */
  momentId?: string;
  localDraftId?: string;
  journalId?: string;
  title: string;
  /**
   * The date/time the entry will be logged at, when the writer has chosen one
   * that is not "now". Only meaningful for a NEW entry before a server Moment
   * exists — once a Moment owns the draft, the Moment holds the real value.
   * Absent on records written before this field existed; recovery then falls
   * back to the current instant.
   */
  loggedAtUtc?: string;
  loggedTimezone?: string;
  contentDelta: DurableDraftDelta;
  /** `entry.updated_at` when the editor opened, for the changed-server check. */
  baseUpdatedAt?: string;
  modifiedAt: string;
  dirty: boolean;
  /**
   * Uploads that were still in flight when this draft was written, and so are
   * not in it. Recovering will not bring those files back — they have to be
   * attached again — and the editor says so rather than letting the writer
   * discover a missing photo later.
   *
   * Only TRANSIENT omissions are ever recorded here. Durable content a draft
   * cannot represent does not produce a record at all; see `useLocalDraft`.
   */
  omittedTransientUploads?: number;
}

interface JournivDraftDb extends DBSchema {
  editorDrafts: {
    key: string;
    value: EditorDraftV1;
    indexes: { "by-user": string };
  };
}

const DB_NAME = "journiv";
export const DRAFT_STORE = "editorDrafts";
export const DRAFT_USER_INDEX = "by-user";

/**
 * IndexedDB schema version.
 *
 * This is a LOCAL migration concern only. It is not a Journiv content format
 * version and has nothing to do with the server's Delta contract — bumping it
 * migrates this browser's store and says nothing about what the API accepts.
 */
export const DRAFT_DB_VERSION = 1;

/**
 * Structural migration, as an ordered ladder of steps.
 *
 * Each step runs when the browser's database predates it, so a store two
 * versions behind is brought forward through every intermediate step in one
 * open. Version 2 is a new `if (oldVersion < 2)` block appended here and a bump
 * of `DRAFT_DB_VERSION` — nothing else. `oldVersion` is 0 for a fresh database.
 *
 * Every step must be safe to meet an object it already created: a browser can
 * arrive here having been upgraded by an older build.
 */
export function upgradeDraftDb(
  db: IDBPDatabase<JournivDraftDb>,
  oldVersion: number,
) {
  if (oldVersion < 1 && !db.objectStoreNames.contains(DRAFT_STORE)) {
    const store = db.createObjectStore(DRAFT_STORE, { keyPath: "key" });
    // Every read is scoped by user; the index is what makes that cheap and what
    // a future "clear local drafts from this device" control needs.
    store.createIndex(DRAFT_USER_INDEX, "userId");
  }
}

/**
 * A local-draft operation that did not happen.
 *
 * `unavailable` distinguishes "this browser will not store anything" (private
 * browsing, blocked site data, no IndexedDB at all) from "this write failed",
 * because those are two different honest messages on screen. Neither may be
 * swallowed: a silent no-op under a "Saved locally" label is the worst possible
 * outcome of this feature.
 */
export class DraftStorageError extends Error {
  readonly unavailable: boolean;

  constructor(
    message: string,
    options?: { cause?: unknown; unavailable?: boolean },
  ) {
    super(message, { cause: options?.cause });
    this.name = "DraftStorageError";
    this.unavailable = options?.unavailable ?? false;
  }
}

let connection: Promise<IDBPDatabase<JournivDraftDb>> | null = null;

function open(): Promise<IDBPDatabase<JournivDraftDb>> {
  if (connection) return connection;
  if (typeof indexedDB === "undefined") {
    return Promise.reject(
      new DraftStorageError("IndexedDB is not available in this browser", {
        unavailable: true,
      }),
    );
  }
  connection = openDB<JournivDraftDb>(DB_NAME, DRAFT_DB_VERSION, {
    upgrade: (db, oldVersion) => upgradeDraftDb(db, oldVersion),
    // Another tab is upgrading. Let go of the connection rather than wedging
    // it; the next call reopens.
    blocking: () => void closeDraftDb(),
  }).catch((cause: unknown) => {
    connection = null;
    throw new DraftStorageError("Local draft storage could not be opened", {
      cause,
      unavailable: true,
    });
  });
  return connection;
}

/** Closes the shared connection. Used on teardown and between tests. */
export async function closeDraftDb() {
  const pending = connection;
  connection = null;
  if (!pending) return;
  try {
    (await pending).close();
  } catch {
    // A connection that cannot be closed is already gone.
  }
}

async function withDb<T>(
  what: string,
  run: (db: IDBPDatabase<JournivDraftDb>) => Promise<T>,
): Promise<T> {
  const db = await open();
  try {
    return await run(db);
  } catch (cause) {
    throw new DraftStorageError(what, { cause });
  }
}

export const draftRepository = {
  /** The stored draft under this key, or null when there is none. */
  read: (key: string) =>
    withDb("Local draft could not be read", async (db) => {
      const record = await db.get(DRAFT_STORE, key);
      return record ?? null;
    }),

  write: (record: EditorDraftV1) =>
    withDb("Local draft could not be saved", async (db) => {
      await db.put(DRAFT_STORE, record);
    }),

  delete: (key: string) =>
    withDb("Local draft could not be removed", async (db) => {
      await db.delete(DRAFT_STORE, key);
    }),

  /**
   * Every draft belonging to one user.
   *
   * Records are only ever reachable through a `userId`, so one account's
   * writing is never visible to another on a shared device. Phase D never
   * deletes on logout — losing work to an involuntary sign-out is the failure
   * this feature exists to prevent — so isolation, not erasure, is what keeps
   * accounts apart.
   */
  listForUser: (userId: string) =>
    withDb("Local drafts could not be listed", (db) =>
      db.getAllFromIndex(DRAFT_STORE, DRAFT_USER_INDEX, userId),
    ),

  /** Removes every draft belonging to one user. Not used by Phase D. */
  deleteForUser: (userId: string) =>
    withDb("Local drafts could not be removed", async (db) => {
      const tx: IDBPTransaction<JournivDraftDb, ["editorDrafts"], "readwrite"> =
        db.transaction(DRAFT_STORE, "readwrite");
      const index = tx.store.index(DRAFT_USER_INDEX);
      for await (const cursor of index.iterate(userId)) await cursor.delete();
      await tx.done;
    }),
};

export type DraftRepository = typeof draftRepository;

/**
 * Where a draft for this editing session lives.
 *
 * Deterministic, so reopening the same entry finds the same record, and scoped
 * to the user so one account's writing is unreachable from another. An existing
 * Entry keys on its own id; a Moment that has no Entry yet keys on the Moment;
 * a brand-new entry keys on a local id the URL carries across a reload.
 *
 * Returns null when there is nothing safe to key on — no signed-in user, or no
 * identity at all. Callers must not write in that case.
 */
export function draftKeyFor(identity: {
  userId?: string;
  entryId?: string;
  momentId?: string;
  localDraftId?: string;
}): string | null {
  const { userId, entryId, momentId, localDraftId } = identity;
  if (!userId) return null;
  if (entryId) return `${userId}:entry:${entryId}`;
  if (momentId) return `${userId}:moment:${momentId}`;
  if (localDraftId) return `${userId}:new:${localDraftId}`;
  return null;
}
