import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  isOldRootFlutterRegistration,
  retireRootFlutterWorker,
} from "./retireRootFlutterWorker";

const migrationKey = "journiv.flutter-root-worker-retired.v1";

function registration(scope: string, scriptURL: string) {
  return {
    scope,
    active: { scriptURL },
    waiting: null,
    installing: null,
    unregister: vi.fn(async () => true),
  } as unknown as ServiceWorkerRegistration;
}

describe("root Flutter worker retirement", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("identifies only the old root-scoped Flutter worker", () => {
    expect(
      isOldRootFlutterRegistration(
        registration(
          `${window.location.origin}/`,
          `${window.location.origin}/flutter_service_worker.js?v=old`,
        ),
      ),
    ).toBe(true);
    expect(
      isOldRootFlutterRegistration(
        registration(
          `${window.location.origin}/legacy/`,
          `${window.location.origin}/legacy/flutter_service_worker.js`,
        ),
      ),
    ).toBe(false);
    expect(
      isOldRootFlutterRegistration(
        registration(
          `${window.location.origin}/`,
          `${window.location.origin}/service-worker.js`,
        ),
      ),
    ).toBe(false);
  });

  it("unregisters the old worker and deletes only Flutter cache names", async () => {
    const old = registration(
      `${window.location.origin}/`,
      `${window.location.origin}/flutter_service_worker.js`,
    );
    const current = registration(
      `${window.location.origin}/`,
      `${window.location.origin}/service-worker.js`,
    );
    const getRegistrations = vi.fn(async () => [old, current]);
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: { getRegistrations },
    });
    const deleteCache = vi.fn(async (_name: string) => true);
    Object.defineProperty(window, "caches", {
      configurable: true,
      value: { delete: deleteCache },
    });

    await retireRootFlutterWorker();

    expect(old.unregister).toHaveBeenCalledOnce();
    expect(current.unregister).not.toHaveBeenCalled();
    expect(deleteCache.mock.calls.map(([name]) => name)).toEqual([
      "flutter-app-cache",
      "flutter-app-manifest",
      "flutter-temp-cache",
    ]);
    expect(localStorage.getItem(migrationKey)).toBe("done");
  });

  it("clears stale Flutter caches even when the worker was already removed", async () => {
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: { getRegistrations: vi.fn(async () => []) },
    });
    const deleteCache = vi.fn(async (_name: string) => true);
    Object.defineProperty(window, "caches", {
      configurable: true,
      value: { delete: deleteCache },
    });

    await retireRootFlutterWorker();

    expect(deleteCache.mock.calls.map(([name]) => name)).toEqual([
      "flutter-app-cache",
      "flutter-app-manifest",
      "flutter-temp-cache",
    ]);
  });
});
