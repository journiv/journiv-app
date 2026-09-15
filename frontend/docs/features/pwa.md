# PWA feature contract

Journiv installs as a standalone app on iOS and Android: its own icon, no
browser chrome, a session that survives closing the app, an app shell that
boots without the network, and a controlled update path that never destroys
unsaved writing.

Read [`authentication.md`](authentication.md) first for the session model
(in-memory access token, `HttpOnly` refresh cookie, boot restore) that an
installed app's persistent login depends on.

## Manifest and icons

`vite.config.ts` configures `vite-plugin-pwa`'s `VitePWA({ manifest: {...} })`
and is committed as `manifest.json` (not the plugin's default
`manifest.webmanifest`) -- the backend's `NO_CACHE_FILENAMES`
(`app/frontend.py`) already no-caches that exact filename, so a stale
manifest can never survive a redeploy.

Two icon families exist because Android's maskable mask would crop the
identity mark's deliberately asymmetric tile (`DESIGN.md`, "The identity
mark"):

- **`any`** -- `public/pwa-192x192.png` / `public/pwa-512x512.png`, generated
  from `public/favicon.svg` (the same tile `BrandMark.tsx` renders), via
  `pwa-assets.config.ts`.
- **`maskable`** -- `public/pwa/maskable-icon-192x192.png` /
  `.../512x512.png`, generated from a dedicated full-bleed source,
  `public/pwa/maskable.svg`, via `pwa-assets.maskable.config.ts`. That source
  is `#405DE6` edge-to-edge with the glyph pre-scaled to sit inside the
  central 80% "safe zone" every platform mask respects -- the tile silhouette
  is deliberately absent; the platform's mask supplies the shape.

Regenerate both with `npm run pwa:assets` (it runs both configs in sequence)
whenever the mark's geometry changes, alongside `favicon.ico` and
`apple-touch-icon.png` (`DESIGN.md`). Both preset files set `padding: 0` --
the tool's 0.3 default would re-inset art that is already safe-zone-aware,
shrinking the mark and adding an unwanted border.

Manifest colours (`theme_color`, `background_color`) are literal hex in
`vite.config.ts`, commented with the token they mirror
(`src/styles/tokens.css` `--background`) -- `npm run lint:design` does not
scan that file, so keeping them in sync is manual. The same is true of the
dark `theme-color` `<meta>` in `index.html`; resolve a token's real sRGB hex
with `getComputedStyle` in an actual browser (draw it to a `<canvas>` and read
`getImageData`, since modern browsers echo `oklch(...)` back unresolved from
plain computed style) -- do not eyeball an oklch-to-hex conversion.

**Shortcuts** (Android long-press icon menu; iOS ignores them): New entry
(`/timeline/new`), Timeline (`/timeline`), Insights (`/insights`), each
reusing the `any` 192 icon. Never add a Quick Log shortcut -- it ships behind
`QUICK_LOG_ENABLED = false` (`src/features/shell/shellContext.ts`).

## Service worker and offline shell

`vite-plugin-pwa`'s `generateSW` strategy (`vite.config.ts`) produces
`service-worker.js` at scope `/` -- the exact filename and root scope the
backend already special-cases (`app/frontend.py` `NO_CACHE_FILENAMES` and its
`Service-Worker-Allowed: /` header). `registerType: "prompt"` with
`clientsClaim: false` / `skipWaiting: false` is load-bearing, not stylistic:
either set true and a new worker takes over mid-session, serving new assets to
an old page on the next navigation -- effectively reloading a user out from
under themselves while they are mid-sentence in the editor.

`src/app/pwa/registerServiceWorker.ts` wraps the vanilla
`virtual:pwa-register` (not the React `useRegisterSW` hook) and is called
once from `main.tsx`, after `retireRootFlutterWorker()` resolves and after
first render -- registering earlier would compete with the boot session
restore for the connection and slow down what the user sees first. It is the
single source of truth for update state (`needRefresh` / `offlineReady`); a
future update-bar UI reads `getUpdateState()` / `subscribeToUpdateState()`
rather than mounting the React hook, which would register the worker a
second time.

**No `/api`, `/media`, `/pub`, or any authenticated response ever enters
Cache Storage.** `workbox.runtimeCaching` is deliberately `[]` and
`navigateFallbackDenylist` excludes those prefixes (plus `/legacy/` and
`/flutter_service_worker.js`, so the root worker never answers a Flutter
navigation with the React shell). Offline reading is a separate, bounded
IndexedDB query cache (`src/app/offline/`), not Cache Storage. Verify this
by pathname, not raw URL -- `Request.url` is absolute, so a
`/^\/(api|media|pub)\//` test against it silently never matches.

`/legacy/` keeps its own service worker at `/legacy/flutter_service_worker.js`,
scoped to `/legacy/`. That more specific scope wins control there regardless
of the root worker's registration; the root worker's own fetch handler must
still never claim a `/legacy/` navigation, which is what the denylist entry
guarantees.

## Deployment security

The shipped deployment is same-origin: FastAPI serves both the frontend and
API. An explicit cross-origin API is supported only over HTTPS or on a loopback
address because session restore sends the refresh cookie with credentialed
requests. Same-origin LAN HTTP requires the backend's explicit
`ALLOW_INSECURE_COOKIE_AUTH_OVER_HTTP=true` opt-in and does not provide the
installed-app experience because service workers require a secure context
(except on loopback origins).
