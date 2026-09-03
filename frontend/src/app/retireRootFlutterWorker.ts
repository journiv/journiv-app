const migrationKey = "journiv.flutter-root-worker-retired.v1";
const flutterCacheNames = [
  "flutter-app-cache",
  "flutter-app-manifest",
  "flutter-temp-cache",
] as const;

function isOldFlutterWorker(worker: ServiceWorker | null): boolean {
  if (!worker) return false;
  return new URL(worker.scriptURL).pathname === "/flutter_service_worker.js";
}

export function isOldRootFlutterRegistration(
  registration: ServiceWorkerRegistration,
): boolean {
  if (registration.scope !== `${window.location.origin}/`) return false;
  return [
    registration.active,
    registration.waiting,
    registration.installing,
  ].some(isOldFlutterWorker);
}

/**
 * One-release migration for users whose browser still has Flutter's old `/`
 * worker. It deliberately ignores every other scope and script URL so a future
 * React PWA worker can coexist with this cleanup.
 */
export async function retireRootFlutterWorker(): Promise<void> {
  if (!("serviceWorker" in navigator)) return;

  try {
    if (localStorage.getItem(migrationKey) === "done") return;

    const registrations = await navigator.serviceWorker.getRegistrations();
    const oldRegistrations = registrations.filter(isOldRootFlutterRegistration);

    if (oldRegistrations.length > 0) {
      await Promise.all(
        oldRegistrations.map((registration) => registration.unregister()),
      );
    }
    // CacheStorage can outlive an unregistered worker (for example after a
    // manual unregister), so clear Flutter's exact legacy names independently.
    if ("caches" in window) {
      await Promise.all(flutterCacheNames.map((name) => caches.delete(name)));
    }

    localStorage.setItem(migrationKey, "done");
  } catch {
    // Cleanup is best-effort. The server-side retirement worker is the primary
    // path for browsers still controlled by cached Flutter before React runs.
  }
}
