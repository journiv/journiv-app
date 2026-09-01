import "fake-indexeddb/auto";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
import { closeDraftDb } from "../features/editor/draftRepository";
import { installMatchMediaStub, resetTestViewportWidth } from "./viewport";

/**
 * jsdom ships no IndexedDB, and the editor keeps local drafts in one. Without
 * this every test would exercise only the "this browser will not store
 * anything" path, and the real behaviour would go unverified.
 */
const realSetTimeout = globalThis.setTimeout;

afterEach(async () => {
  // An adaptive-overlay test that narrows the viewport must not leak that
  // width into the next test.
  resetTestViewportWidth();
  // Unmount first: leaving the editor flushes a draft, so a component still
  // mounted would write a record after the database was cleared.
  cleanup();
  await new Promise<void>((resolve) => {
    realSetTimeout(resolve, 0);
  });
  // Close first: an open connection blocks `deleteDatabase`, which would then
  // leave every record in place for the next test to trip over.
  await closeDraftDb();
  await new Promise<void>((resolve) => {
    const request = indexedDB.deleteDatabase("journiv");
    request.onsuccess = () => resolve();
    request.onerror = () => resolve();
    request.onblocked = () => resolve();
  });
});

const localValues = new Map<string, string>();
const memoryLocalStorage: Storage = {
  get length() {
    return localValues.size;
  },
  clear: () => localValues.clear(),
  getItem: (key) => localValues.get(key) ?? null,
  key: (index) => [...localValues.keys()][index] ?? null,
  removeItem: (key) => localValues.delete(key),
  setItem: (key, value) => localValues.set(key, value),
};
Object.defineProperty(window, "localStorage", {
  configurable: true,
  value: memoryLocalStorage,
});
Object.defineProperty(window, "scrollTo", {
  configurable: true,
  value: () => undefined,
});

if (!Range.prototype.getBoundingClientRect) {
  Object.defineProperty(Range.prototype, "getBoundingClientRect", {
    configurable: true,
    value: () => new DOMRect(),
  });
}
if (!Range.prototype.getClientRects) {
  Object.defineProperty(Range.prototype, "getClientRects", {
    configurable: true,
    value: () => Object.assign([], { item: () => null }),
  });
}

/* Width-aware `matchMedia` (see src/test/viewport.ts). Installed
 * unconditionally, so behaviour does not depend on the jsdom version. */
installMatchMediaStub();
