// Retires the root-scoped Flutter service worker shipped before React owned `/`.
// This file must remain at /flutter_service_worker.js for the browser's normal
// service-worker update check to find it. A future React worker should use a
// different script URL (for example /service-worker.js).
const FLUTTER_CACHE_NAMES = [
  "flutter-app-cache",
  "flutter-app-manifest",
  "flutter-temp-cache",
];

self.addEventListener("install", (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      await Promise.all(FLUTTER_CACHE_NAMES.map((name) => caches.delete(name)));
      await self.clients.claim();

      const clients = await self.clients.matchAll({
        includeUncontrolled: true,
        type: "window",
      });
      await self.registration.unregister();

      // A cached Flutter index may have initiated this update. Navigating the
      // existing window after unregistering gives it the React document without
      // requiring the user to discover that a manual hard refresh is needed.
      await Promise.all(
        clients.map((client) =>
          "navigate" in client ? client.navigate(client.url) : undefined,
        ),
      );
    })(),
  );
});
