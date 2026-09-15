import { type DBSchema, type IDBPDatabase, openDB } from "idb";

/**
 * The offline read-cache's own IndexedDB database -- deliberately separate
 * from the `journiv` database `draftRepository.ts` owns. That database's
 * version ladder belongs to drafts; two modules opening the same database at
 * different expected versions is a live footgun (docs/features/pwa.md).
 *
 * Unlike drafts, a failed read or write here only costs offline capability,
 * never unsaved writing, so this module degrades quietly (private browsing,
 * blocked site data, no IndexedDB at all) rather than throwing.
 */

interface JournivOfflineDb extends DBSchema {
  queryCache: {
    key: string;
    value: string;
  };
}

const DB_NAME = "journiv-offline";
const DB_VERSION = 1;
const STORE = "queryCache";

let connection: Promise<IDBPDatabase<JournivOfflineDb>> | null = null;

function open(): Promise<IDBPDatabase<JournivOfflineDb>> {
  if (connection) return connection;
  if (typeof indexedDB === "undefined") {
    return Promise.reject(new Error("IndexedDB is not available"));
  }
  connection = openDB<JournivOfflineDb>(DB_NAME, DB_VERSION, {
    upgrade(db) {
      if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE);
    },
    blocking: () => void closeOfflineDb(),
  }).catch((cause: unknown) => {
    connection = null;
    throw cause;
  });
  return connection;
}

/** Closes the shared connection. Used between tests. */
export async function closeOfflineDb() {
  const pending = connection;
  connection = null;
  if (!pending) return;
  try {
    (await pending).close();
  } catch {
    // A connection that cannot be closed is already gone.
  }
}

/** The `AsyncStorage<string>` shape `@tanstack/query-async-storage-persister`
 *  expects. Reads and background writes degrade quietly because losing them
 *  only costs offline capability. Explicit removal rejects so Settings never
 *  claims private journal data was erased when the browser refused it. */
export const offlineKv = {
  async getItem(key: string): Promise<string | null> {
    try {
      const db = await open();
      return (await db.get(STORE, key)) ?? null;
    } catch {
      return null;
    }
  },
  async setItem(key: string, value: string): Promise<void> {
    try {
      const db = await open();
      await db.put(STORE, value, key);
    } catch {
      // Best-effort: losing a write only costs a future offline read.
    }
  },
  async removeItem(key: string): Promise<void> {
    const db = await open();
    await db.delete(STORE, key);
  },
};
