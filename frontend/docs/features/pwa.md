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

## Same-origin only

Session restore and the manifest/service-worker topology assume the frontend
and API share an origin -- the shipped deployment (FastAPI serves both). A
plain-HTTP deployment gets no installed-app experience: service workers
require a secure context, and this is accepted, not worked around
(`docs/known-gaps.md`).
