import { fileURLToPath } from "node:url";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { VitePWA } from "vite-plugin-pwa";
import { manifestShortcuts } from "./src/app/pwa/manifestShortcuts.ts";

const srcDir = fileURLToPath(new URL("./src", import.meta.url));
const shortcutIcons = [
  { src: "/pwa-192x192.png", sizes: "192x192", type: "image/png" },
];

// Manifest colours are not scanned by npm run lint:design (raw colours are a
// source-tree rule). Keep them mirroring the real tokens by hand:
// src/styles/tokens.css `--background` -- oklch(1 0 0) light, oklch(0.205 0 0)
// dark, resolved to sRGB via getComputedStyle in a real browser (do not trust
// an eyeballed conversion — oklch does not map to hex by inspection).
const LIGHT_BACKGROUND_HEX = "#ffffff";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "JOURNIV_");
  const backendProxy = env.JOURNIV_BACKEND_PROXY_URL ?? "http://127.0.0.1:8000";

  return {
    base: "/",
    plugins: [
      react(),
      tailwindcss(),
      VitePWA({
        // We register the worker explicitly in src/app/pwa/registerServiceWorker.ts,
        // after retireRootFlutterWorker() and after first render -- injecting it
        // here would race the boot session restore. See docs/features/pwa.md.
        injectRegister: null,
        registerType: "prompt",
        // The backend no-caches this exact filename (app/frontend.py
        // NO_CACHE_FILENAMES) and sets Service-Worker-Allowed: / for it.
        filename: "service-worker.js",
        manifestFilename: "manifest.json",
        scope: "/",
        base: "/",
        includeAssets: ["favicon.svg", "favicon.ico", "apple-touch-icon.png"],
        manifest: {
          id: "/",
          name: "Journiv",
          short_name: "Journiv",
          description: "Your private journal.",
          start_url: "/",
          scope: "/",
          display: "standalone",
          display_override: ["standalone", "minimal-ui", "browser"],
          theme_color: LIGHT_BACKGROUND_HEX,
          background_color: LIGHT_BACKGROUND_HEX,
          lang: "en",
          dir: "ltr",
          categories: ["lifestyle", "productivity"],
          launch_handler: { client_mode: "navigate-existing" },
          handle_links: "preferred",
          prefer_related_applications: false,
          icons: [
            {
              src: "/pwa-192x192.png",
              sizes: "192x192",
              type: "image/png",
              purpose: "any",
            },
            {
              src: "/pwa-512x512.png",
              sizes: "512x512",
              type: "image/png",
              purpose: "any",
            },
            {
              src: "/pwa/maskable-icon-192x192.png",
              sizes: "192x192",
              type: "image/png",
              purpose: "maskable",
            },
            {
              src: "/pwa/maskable-icon-512x512.png",
              sizes: "512x512",
              type: "image/png",
              purpose: "maskable",
            },
          ],
          // Android long-press shortcuts only; iOS ignores this. Reuses the
          // `any` 192 icon rather than drawing three new glyphs. Never add
          // Quick Log here -- it ships behind QUICK_LOG_ENABLED = false
          // (src/features/shell/shellContext.ts). The list itself lives in
          // manifestShortcuts.ts so manifestShortcuts.test.ts can assert
          // every url resolves in the router.
          shortcuts: manifestShortcuts.map((shortcut) => ({
            ...shortcut,
            icons: shortcutIcons,
          })),
        },
        devOptions: { enabled: false },
        workbox: {
          globPatterns: ["**/*.{js,css,html,svg,png,ico,woff2}"],
          // Install art, not shell: manifest screenshots are shown once, by
          // the browser's install dialog, while online. They are not worth
          // precaching into the offline shell.
          globIgnores: ["**/pwa/screenshot-*"],
          maximumFileSizeToCacheInBytes: 4 * 1024 * 1024,
          inlineWorkboxRuntime: true,
          cleanupOutdatedCaches: true,
          // Not stylistic: with either set true, a new worker takes over
          // mid-session and the next navigation serves new assets to an old
          // page -- reloading out from under a user who is mid-sentence in
          // the editor. registerType: "prompt" requires both false.
          clientsClaim: false,
          skipWaiting: false,
          navigateFallback: "/index.html",
          navigateFallbackDenylist: [
            /^\/api\//,
            /^\/media\//,
            /^\/pub\//,
            // Reserved by the backend (app/frontend.py BACKEND_ROOTS) and
            // 404s there today. Without this the worker would answer a
            // /plus navigation with the React shell from precache, so the
            // first real Plus page shipped would be shadowed by the shell
            // for every already-installed client.
            /^\/plus(?:\/|$)/,
            /^\/static\//,
            /^\/docs/,
            /^\/redoc/,
            /^\/openapi\.json$/,
            // Stops the root worker from answering a Flutter navigation with
            // the React shell mid-rollback; /legacy/ has its own SW scope.
            /^\/legacy\//,
            /^\/flutter_service_worker\.js$/,
          ],
          // Deliberate and load-bearing, not an oversight: no /api, /media or
          // /pub response may ever enter Cache Storage. Offline reading goes
          // through the IndexedDB query cache (src/app/offline/) instead --
          // per-user, bounded, allowlisted, and clearable.
          runtimeCaching: [],
        },
      }),
    ],
    resolve: {
      alias: { "@": srcDir },
    },
    server: {
      port: process.env.PORT ? Number(process.env.PORT) : undefined,
      proxy: {
        "/api": backendProxy,
        "/media": backendProxy,
      },
    },
    // The service worker is disabled in dev (devOptions.enabled: false), so
    // PWA/offline behaviour can only be exercised against a real build via
    // `vite preview` (e2e/pwa/*, docs/features/pwa.md) -- it needs the same
    // proxy `server` has.
    preview: {
      proxy: {
        "/api": backendProxy,
        "/media": backendProxy,
      },
    },
  };
});
