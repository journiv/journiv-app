import { type DBSchema, type IDBPDatabase, openDB } from "idb";
import { type DictationAnchor, extensionForMime } from "./dictationFormat";

/**
 * Crash-safe staging for dictation.
 *
 * A dictation can run for minutes. If the PWA is killed by the OS, the tab is
 * suspended, the page reloads, or the upload fails after Stop, the only copy of
 * someone's speech would be gone — for a journal, the worst thing this feature
 * can do. So every chunk `MediaRecorder` hands over is written here as it
 * arrives, and the staged copy is deleted only after the media upload has
 * succeeded (docs/features/editor.md, Voice notes).
 *
 * IndexedDB, never Cache Storage: the service worker contract forbids `/api`,
 * `/media` and `/pub` responses in Cache Storage, and offline data lives in
 * IndexedDB (docs/features/pwa.md).
 *
 * A database of its own, not another store in `journiv` (drafts) or
 * `journiv-offline`. Both are owned by other modules with their own version
 * ladders, and a header comment in `app/offline/db.ts` warns that two modules
 * opening one database at different expected versions is a live footgun.
 * Recordings are large, short-lived binary data with a different lifecycle from
 * writing, so they get their own database and their own ladder.
 *
 * Chunks are stored as `ArrayBuffer`, not `Blob`: it is the value every
 * IndexedDB implementation stores reliably, including Safari's.
 */

export type RecordingStatus = "recording" | "stopped";

export type RecordingSession = {
  id: string;
  userId: string;
  /** The editor's local-draft key — which entry this recording belongs to. */
  draftKey: string;
  /** The container the recorder actually wrote (its `mimeType`, not the request). */
  mimeType: string;
  startedAt: string;
  updatedAt: string;
  durationMs: number;
  chunkCount: number;
  status: RecordingStatus;
  /** Where the caret was when recording started. */
  anchor: DictationAnchor;
};

/**
 * Where in the entry a finished recording was made.
 *
 * Kept per media id after the staged audio is deleted: the staged copy is upload
 * plumbing, the anchor belongs to the media. Nothing reads it today. It is device-local: nothing about
 * it is sent to the server or lives in the document. It lives as long as its
 * server media does and no longer: `pruneAnchors` removes it once the media is
 * gone (docs/features/editor.md, Voice notes).
 */
export type RecordingAnchorRecord = {
  mediaId: string;
  userId: string;
  draftKey: string;
  momentId: string;
  anchor: DictationAnchor;
  capturedAt: string;
};

type ChunkRecord = { sessionId: string; index: number; data: ArrayBuffer };

interface RecordingDb extends DBSchema {
  sessions: {
    key: string;
    value: RecordingSession;
    indexes: { "by-user": string };
  };
  chunks: {
    key: [string, number];
    value: ChunkRecord;
  };
  anchors: {
    key: string;
    value: RecordingAnchorRecord;
  };
}

const DB_NAME = "journiv-recordings";
/** A local structural version only; it says nothing about any server format. */
export const RECORDING_DB_VERSION = 1;
const SESSIONS = "sessions";
const CHUNKS = "chunks";
const ANCHORS = "anchors";

export function upgradeRecordingDb(
  db: IDBPDatabase<RecordingDb>,
  oldVersion: number,
) {
  if (oldVersion < 1) {
    if (!db.objectStoreNames.contains(SESSIONS)) {
      db.createObjectStore(SESSIONS, { keyPath: "id" }).createIndex(
        "by-user",
        "userId",
      );
    }
    if (!db.objectStoreNames.contains(CHUNKS)) {
      db.createObjectStore(CHUNKS, { keyPath: ["sessionId", "index"] });
    }
    if (!db.objectStoreNames.contains(ANCHORS)) {
      db.createObjectStore(ANCHORS, { keyPath: "mediaId" });
    }
  }
}

/**
 * A staging operation that did not happen. `unavailable` separates "this browser
 * will not store anything" (private browsing, blocked site data) from "this
 * write failed" — recording still works in the first case, it is just not
 * crash-safe, and the UI must not promise otherwise.
 */
export class RecordingStorageError extends Error {
  readonly unavailable: boolean;
  constructor(
    message: string,
    options?: { cause?: unknown; unavailable?: boolean },
  ) {
    super(message, { cause: options?.cause });
    this.name = "RecordingStorageError";
    this.unavailable = options?.unavailable ?? false;
  }
}

let connection: Promise<IDBPDatabase<RecordingDb>> | null = null;

function open(): Promise<IDBPDatabase<RecordingDb>> {
  if (connection) return connection;
  if (typeof indexedDB === "undefined") {
    return Promise.reject(
      new RecordingStorageError("IndexedDB is not available in this browser", {
        unavailable: true,
      }),
    );
  }
  connection = openDB<RecordingDb>(DB_NAME, RECORDING_DB_VERSION, {
    upgrade: (db, oldVersion) => upgradeRecordingDb(db, oldVersion),
    blocking: () => void closeRecordingDb(),
  }).catch((cause: unknown) => {
    connection = null;
    throw new RecordingStorageError("Recording storage could not be opened", {
      cause,
      unavailable: true,
    });
  });
  return connection;
}

export async function closeRecordingDb() {
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
  run: (db: IDBPDatabase<RecordingDb>) => Promise<T>,
): Promise<T> {
  const db = await open();
  try {
    return await run(db);
  } catch (cause) {
    throw new RecordingStorageError(what, { cause });
  }
}

/**
 * Whether `journiv-recordings` exists yet, without opening (and so creating) it.
 *
 * The editor and the reader look for unfinished recordings and stale anchors on
 * every mount. Opening the database for that would create an empty one for a
 * writer who has never recorded anything, and its first-time upgrade competes
 * with the editor's own IndexedDB work. Only recording creates it.
 *
 * Where the browser cannot say (`indexedDB.databases()` is missing or throws) the
 * answer is "yes": the caller then opens it as before, which is correct, just
 * not free.
 */
async function databaseExists(): Promise<boolean> {
  if (connection) return true;
  const factory = indexedDB as IDBFactory & {
    databases?: () => Promise<Array<{ name?: string }>>;
  };
  if (typeof factory.databases !== "function") return true;
  try {
    return (await factory.databases()).some((info) => info.name === DB_NAME);
  } catch {
    return true;
  }
}

/**
 * A read that has nothing to say until a recording has been made: returns
 * `whenAbsent` instead of creating the database. Unavailable storage still
 * rejects, exactly as `withDb` does.
 */
async function withExistingDb<T>(
  what: string,
  whenAbsent: T,
  run: (db: IDBPDatabase<RecordingDb>) => Promise<T>,
): Promise<T> {
  if (typeof indexedDB === "undefined") {
    throw new RecordingStorageError(
      "IndexedDB is not available in this browser",
      {
        unavailable: true,
      },
    );
  }
  if (!(await databaseExists())) return whenAbsent;
  return withDb(what, run);
}

const chunkRange = (sessionId: string) =>
  IDBKeyRange.bound([sessionId, 0], [sessionId, Number.MAX_SAFE_INTEGER]);

export const recordingRepository = {
  createSession: (session: RecordingSession) =>
    withDb("Recording could not be staged", async (db) => {
      await db.put(SESSIONS, session);
    }),

  /** Persists one recorder chunk. Resolves only once it is durably written. */
  appendChunk: (sessionId: string, index: number, data: ArrayBuffer) =>
    withDb("Recording could not be staged", async (db) => {
      await db.put(CHUNKS, { sessionId, index, data });
    }),

  /** Merges `changes` into a staged session; a session already gone is a no-op. */
  updateSession: (
    id: string,
    changes: Partial<
      Pick<RecordingSession, "durationMs" | "chunkCount" | "status">
    >,
  ) =>
    withDb("Recording could not be staged", async (db) => {
      const tx = db.transaction(SESSIONS, "readwrite");
      const current = await tx.store.get(id);
      if (current) {
        await tx.store.put({
          ...current,
          ...changes,
          updatedAt: new Date().toISOString(),
        });
      }
      await tx.done;
    }),

  readSession: (id: string) =>
    withDb("Recording could not be read", async (db) => {
      return (await db.get(SESSIONS, id)) ?? null;
    }),

  /**
   * Every staged session for one user. A staged session is by definition
   * unfinished: it is deleted the moment its upload succeeds. Newest first.
   */
  listUnfinished: (userId: string) =>
    withExistingDb<RecordingSession[]>(
      "Recordings could not be listed",
      [],
      async (db) => {
        const sessions = await db.getAllFromIndex(SESSIONS, "by-user", userId);
        return sessions.sort((a, b) => b.startedAt.localeCompare(a.startedAt));
      },
    ),

  /**
   * The staged audio as one `File`. `extra` supplies chunks that never reached
   * storage (it failed mid-recording) so a partial failure loses nothing.
   */
  assemble: (session: RecordingSession, extra?: ReadonlyMap<number, Blob>) =>
    withDb("Recording could not be read", async (db) => {
      const stored = await db.getAll(CHUNKS, chunkRange(session.id));
      const parts = new Map<number, BlobPart>();
      for (const chunk of stored) parts.set(chunk.index, chunk.data);
      for (const [index, blob] of extra ?? []) parts.set(index, blob);
      // A stopped session knows how many chunks the recorder produced. If a
      // write disappeared, do not upload a plausible but truncated recording.
      if (session.chunkCount > 0 && parts.size !== session.chunkCount)
        return null;
      return buildRecordingFile(session, [...parts.entries()]);
    }),

  /** Removes a staged session and all its chunks. Safe to call twice. */
  deleteSession: (id: string) =>
    withDb("Recording could not be removed", async (db) => {
      const tx = db.transaction([SESSIONS, CHUNKS], "readwrite");
      await tx.objectStore(SESSIONS).delete(id);
      await tx.objectStore(CHUNKS).delete(chunkRange(id));
      await tx.done;
    }),

  saveAnchor: (record: RecordingAnchorRecord) =>
    withDb("Recording position could not be kept", async (db) => {
      await db.put(ANCHORS, record);
    }),

  readAnchor: (mediaId: string) =>
    withDb("Recording position could not be read", async (db) => {
      return (await db.get(ANCHORS, mediaId)) ?? null;
    }),

  deleteAnchor: (mediaId: string) =>
    withDb("Recording position could not be removed", async (db) => {
      await db.delete(ANCHORS, mediaId);
    }),

  /**
   * Drops the anchors of one Moment whose media no longer exists.
   *
   * An anchor must outlive the *staged audio* (deleted after upload) but never
   * the *server media* it points at. Nothing in the app
   * deletes a dictation recording directly, so this runs against a media list
   * the caller already has: `presentMediaIds` is every media id the server
   * returned for the Moment, in any status — a `pending` or `processing` item is
   * present and so is never pruned.
   *
   * A list can be stale, or can be in flight while an upload finishes, so an
   * anchor is only eligible once it is `ANCHOR_PRUNE_GRACE_MS` older than the
   * moment the list was fetched (`listedAt`, epoch ms). A too-young anchor is
   * kept and simply considered on a later load; pruning is housekeeping and must
   * never cost a live anchor.
   *
   * Returns how many were removed.
   */
  pruneAnchors: (
    momentId: string,
    presentMediaIds: ReadonlySet<string>,
    listedAt: number,
  ) =>
    withExistingDb<number>(
      "Recording positions could not be pruned",
      0,
      async (db) => {
        const tx = db.transaction(ANCHORS, "readwrite");
        let removed = 0;
        for (const record of await tx.store.getAll()) {
          if (record.momentId !== momentId) continue;
          if (presentMediaIds.has(record.mediaId)) continue;
          const capturedAt = Date.parse(record.capturedAt);
          // An unreadable timestamp is not evidence of age: keep it.
          if (Number.isNaN(capturedAt)) continue;
          if (capturedAt + ANCHOR_PRUNE_GRACE_MS > listedAt) continue;
          await tx.store.delete(record.mediaId);
          removed += 1;
        }
        await tx.done;
        return removed;
      },
    ),
};

/**
 * How much older than the media list an anchor must be before it can be pruned.
 * Long enough to cover an upload finishing while a list request is in flight or
 * a cached list that predates it.
 */
export const ANCHOR_PRUNE_GRACE_MS = 60_000;

export type RecordingRepository = typeof recordingRepository;

/**
 * `Blob.arrayBuffer()` where it exists, `FileReader` where it does not (older
 * Safari). Chunks are stored as buffers, so every chunk goes through this.
 */
export function blobToArrayBuffer(blob: Blob): Promise<ArrayBuffer> {
  if (typeof blob.arrayBuffer === "function") return blob.arrayBuffer();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as ArrayBuffer);
    reader.onerror = () => reject(reader.error);
    reader.readAsArrayBuffer(blob);
  });
}

/** A real file name and the recorder's actual MIME, in chunk order. */
export function buildRecordingFile(
  session: Pick<RecordingSession, "mimeType" | "startedAt">,
  chunks: ReadonlyArray<readonly [number, BlobPart]>,
): File | null {
  if (!chunks.length) return null;
  const ordered = [...chunks].sort((a, b) => a[0] - b[0]);
  // A crash may leave a valid prefix; a hole in the middle is corrupted audio.
  if (ordered.some(([index], position) => index !== position)) return null;
  return new File(
    ordered.map(([, part]) => part),
    recordingFileName(session),
    {
      type: session.mimeType,
    },
  );
}

/** `voice-note-2026-09-19-1430.webm`, in the writer's local time. */
export function recordingFileName(
  session: Pick<RecordingSession, "mimeType" | "startedAt">,
): string {
  const started = new Date(session.startedAt);
  const stamp = Number.isNaN(started.getTime())
    ? "recording"
    : [
        started.getFullYear(),
        String(started.getMonth() + 1).padStart(2, "0"),
        String(started.getDate()).padStart(2, "0"),
        `${String(started.getHours()).padStart(2, "0")}${String(started.getMinutes()).padStart(2, "0")}`,
      ].join("-");
  return `voice-note-${stamp}.${extensionForMime(session.mimeType)}`;
}
