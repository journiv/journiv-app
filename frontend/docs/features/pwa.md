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

## Update UX

`registerType: "prompt"` means a waiting worker never takes over on its own.
`src/app/pwa/usePwaUpdate.ts` exposes `{ updateReady, applyUpdate }`, read by
`UpdateBar` (`src/features/shell/UpdateBar.tsx`) -- persistent chrome in a
reserved bottom row of the shell, not a toast (DESIGN.md: a waiting update is
standing state, not a one-shot outcome). `applyUpdate` is never called without an
explicit click. When the mounted editor has unsaved changes
(`ShellContext.hasUnsavedDraft`, set by `EntryEditorPage.tsx`), clicking
"Restart to update" shows an `AppConfirmDialog` first, warning that unsaved
changes may be lost. `hasUnsavedDraft` reports dirty editor state, not proof
that the latest local-draft write succeeded, so the UI must not promise
restoration from that flag alone. Only confirming calls `applyUpdate`.
Dismissing the bar hides it until the next page load, not forever.

## Install

`src/app/pwa/installPrompt.ts` captures `beforeinstallprompt` at module load
(`preventDefault()`, keep the deferred event) so the event is never missed
before Settings mounts, and clears it on `appinstalled`. `isStandalone()`
checks `display-mode: standalone` and iOS's `navigator.standalone`;
`isIosSafari()` exists because iOS never fires `beforeinstallprompt` at all --
the only install route there is Share → Add to Home Screen.

Settings → **Install & offline** (`src/features/settings/app/AppSettingsPage.tsx`,
after Appearance in `settingsNav.ts`) is the only place install ever appears --
never an unsolicited banner or interstitial (DESIGN.md product character). Its
Install row shows exactly one of: already-installed, the Share instructions
(iOS), an "Install Journiv" button (a captured prompt is available), or an
honest sentence when none applies (an unsupported browser, or plain HTTP) --
never a disabled button with no reason.

**iOS + plain HTTP is the one case that looks like it works but doesn't.**
"Add to Home Screen" needs no service worker, so it succeeds over plain HTTP
-- but nothing was ever precached, so the installed icon has no offline
fallback at all: a real user hit this as a launch-time black screen with no
error, not a graceful degrade. The Share instructions therefore carry an
explicit caveat on an insecure context (`window.isSecureContext === false`)
rather than silently implying full offline support. There is no code fix for
the underlying limitation -- service workers require a secure context, full
stop (`docs/known-gaps.md`) -- only for making sure the person installing
finds out before they rely on it offline.

## Bounded offline read cache

`src/app/offline/` persists a bounded, per-user slice of the TanStack Query
cache to a dedicated IndexedDB database, `journiv-offline` (version 1, one
`queryCache` object store) -- deliberately separate from the `journiv`
database `draftRepository.ts` owns, since that database's version ladder
belongs to drafts.

**Allowlist, never denylist** (`persistedQueries.ts`). A query persists only
when its key is one of: `current-user`, `user-settings`, `instance-config`,
`journals`, `tags`, `people`, `moods`, `activities`, `goals`, the *unfiltered*
`["moments", {}]` timeline, and `["moment", id]` for an entry the user
actually opened. Everything else -- `["export", …]`, `["import", …]`,
`["admin", …]`, `["integrations", …]`, `["prompts","library",…]`, any
*filtered* `["moments", {...}]`, and `["moment", id, "media"]` (offline media
viewing is out of scope) -- is excluded by construction. A query must also
have `status: "success"` with data present and be no older than
`MAX_AGE_MS` (7 days). A hand-maintained `CACHE_SCHEMA_VERSION` buster in
`offlineCache.ts` invalidates old shapes on a format change -- never the
build hash, which would wipe the cache on every deploy, precisely when
offline capability matters most. A 120-query cap (`MAX_PERSISTED_QUERIES`)
is enforced by a custom `serialize` in the persister, the only place that
can act across the whole dehydrated client rather than per-query.

**No Cache Storage entry, ever, for `/api`, `/media`, or `/pub`** (Phase 3's
guard). This is the IndexedDB-only alternative for offline *reading*.
Cached `["moment", id]` entries still carry inline signed media URLs baked
into the Delta by the backend (`docs/features/reader.md`) -- there is no
allowlist rule that strips them, so the reader must render its existing
media-placeholder fallback when a persisted URL has expired, keyed by media
id the same way a live re-sign already reloads a slide in place. See
`docs/known-gaps.md` for the follow-up that would remove this residue
entirely (canonicalising stored Deltas the way drafts already do).

**Hydrate before first render, never `PersistQueryClientProvider`.** That
provider restores inside a `useEffect`, so children render before
restoration finishes and an offline launch paints an empty shell that fills
in a frame later -- exactly what this phase exists to avoid. `main.tsx`
instead calls `hydrateOfflineCache` (a 2s-bounded, try/catch'd
`persistQueryClientRestore`) concurrently with the session restore via
`Promise.all`, resolves the boot mode, and only then renders once. A slow or
blocked IndexedDB degrades to an empty cache rather than holding the boot
splash open. Restoration is staged in a temporary `QueryClient`; only a
result that completes before the timeout and still belongs to the active
session/preference lifecycle is committed to the live client. A late IndexedDB
read therefore cannot repopulate data after sign-out, a user switch, or an
offline-reading opt-out.

Persisted Moment readers are stale-while-revalidate: cached detail paints on
the first render, but `momentQuery` always revalidates when the reader mounts.
This is required even inside the normal query freshness window because the
IndexedDB persister throttles writes; a reload immediately after saving can
otherwise restore the pre-save snapshot and mistake it for current data. When
offline, TanStack pauses that request and the cached reader remains available.

**Boot mode** (`offlineMode.ts`) is derived once from the restore result and
the session hint, then kept current without a reload: `"restored"` → normal;
`"unauthenticated"` → the login route; `"offline"` with a hint → offline-
restricted (the shell renders with cached content); `"offline"` with no hint
→ the login route too, since `LoginPage` already fails closed honestly when
`instanceConfig` can't load offline. The router's `protectedRoute` guard
allows both a live access token and offline-restricted; nothing else. A
later successful `attemptRefresh()` (the original background attempt from
boot, or the retry an `online` event triggers -- `useOnlineStatus.ts`)
upgrades offline-restricted to normal in place; a definite 401/403 or an
explicit sign-out moves to unauthenticated the same way. `navigator.onLine`
never decides any of this by itself -- Journiv is self-hosted and frequently
LAN-reachable while the OS reports no connectivity; it only ever decides
*when* to check, both at boot and while running.

The route guard admits only cached reading destinations while the mode is
offline-restricted: timeline and journal lists plus their Moment readers.
Editor deep links redirect to the corresponding reader; new-entry, Settings,
Import, Library-management, and other mutation-oriented routes redirect to a
cached read route. Normal authenticated routing and unauthenticated login
redirects are unchanged.

In offline-restricted mode, `OfflineBar` (`src/features/shell/`) states
plainly that content is cached, with a relative timestamp from the freshest
query in the cache. The sidebar's "New entry" action is disabled with a
reason rather than left to fail; controls embedded inside otherwise readable
routes still have the narrower gap documented in `docs/known-gaps.md`.

**A fresh sign-in has no hint yet at boot.** `main.tsx` subscribes the
offline cache to whatever `userId` the session hint names *at boot* --
`undefined` for a browser that has never signed in. `sessionStore.adopt()`
(login, signup, OIDC finish) therefore also fires a registered callback
(`registerOfflineCacheSubscribe`) that (re)subscribes with the newly-known
`userId`, or nothing would ever be persisted for a session that started with
a fresh login rather than a cookie-restored one.

**Settings → "Install & offline"** carries the disclosure and controls
(§8.5 of the implementation plan): offline reading ships **on by default** --
an explicit owner decision, disclosure plus an opt-out, not an opt-in
privacy control, and there is no first-run consent prompt. Turning the
switch off purges the cache immediately and stops persisting
(`setOfflineReadingEnabled`). A storage-used estimate reads
`navigator.storage.estimate()`; `navigator.storage.persist()` is requested
once real usage exists, never on a blank first launch. **What this means for
security**: cached entries are protected by the device and browser profile,
not the server session -- someone with the unlocked device can read them in
airplane mode after the server-side session has expired. That is inherent to
any useful offline reading, not a defect, and is written down here rather
than left to be discovered.

## Deployment security

The shipped deployment is same-origin: FastAPI serves both the frontend and
API. An explicit cross-origin API is supported only over HTTPS or on a loopback
address because session restore sends the refresh cookie with credentialed
requests. Same-origin LAN HTTP requires the backend's explicit
`ALLOW_INSECURE_COOKIE_AUTH_OVER_HTTP=true` opt-in and does not provide the
installed-app experience because service workers require a secure context
(except on loopback origins).
