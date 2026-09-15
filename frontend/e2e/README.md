# Playwright E2E tests

Read this before adding or changing a browser test. Playwright owns real-browser
journeys, persistence, responsive behaviour, runtime accessibility, and visual
regression. It does not replace the static design guard, Vitest, or backend
pytest.

## Run from the frontend directory

```bash
npm run test:e2e
npm run test:e2e:smoke
npx playwright test e2e/<feature>/<spec>.spec.ts
```

The backend must already be running; Playwright starts Vite but not the API.
`npm run verify` is deliberately separate and does not run browser tests.
Install Chromium with `npm run test:e2e:install` when needed.

## Test placement and fixtures

Place specs in `e2e/<feature>/`. Import `test` and `expect` from
`e2e/fixtures/test`, not directly from Playwright. The fixtures provide
authenticated worker users, API-backed data factories, deterministic time,
theme and personalization reset, and cleanup. Use their documented environment
variables in `e2e/env.ts`; never commit credentials.

Use API fixtures for setup and cleanup. A spec should create only the data it
needs, use deterministic dates, and clean up through the fixture rather than
depending on pre-seeded state. Do not add `storageState`; the suite's auth model
is worker-scoped and intentionally explicit.

### Session model

The app's durable credential is the `journiv_refresh` `HttpOnly` cookie
(`docs/features/authentication.md`); the access token lives only in memory and
is never written to storage, so no page script can seed it. `test.ts`'s
`context` fixture instead injects the refresh cookie directly with
Playwright's `context.addCookies()` — a browser-context API, not page script,
so the `HttpOnly` flag does not block it. The app's own boot sequence
(`main.tsx`) then exchanges that cookie for a fresh access token on first
load, exactly as it would for a real returning user.

The same fixture also seeds `journiv.session-hint.v1` in `localStorage` via
`buildInitScript`'s `sessionHint` option (`e2e/fixtures/determinism.ts`). This
hint is an ordinary (non-credential) breadcrumb a real signed-in browser
already carries from having gone through the login UI once; it is what lets a
boot with no reachable network land in offline-restricted mode instead of
bouncing to `/login` (`src/app/offline/offlineMode.ts`). Injecting only the
cookie without the hint understates what a real returning user's browser
looks like — keep both in sync if the session model changes again.

## What to assert

- Prefer role, label, and test-id locators; do not use brittle CSS or text
  fragments where an accessible locator exists.
- Wait for an observable condition, response, or locator state. Never use a
  sleep as synchronisation.
- Pin the supplied viewport and theme helpers when responsive or visual state
  matters. The canonical viewports are 1440×900, 1024×768, and 390×844.
- Keep validation permutations, pure logic, mocked render states, and static
  token rules in Vitest or the design guard.
- Add an E2E test only when a real browser plus backend proves something those
  layers cannot.

## Screenshots

Use screenshot assertions only for stable, deterministic visual contracts. Pin
clock, theme, fonts, data, and viewport first. Review snapshot updates manually;
never update baselines merely to make a failing test pass. The current manual
reference captures live in `docs/design/reference/`; use them for visual work
until committed Playwright baselines cover the same scene.

## PWA suite

`e2e/pwa/` covers service worker registration/scope, the Cache Storage
allowlist, offline reads and boot behaviour, and the update bar — the
automated portion of `docs/features/pwa.md`. It runs against a real build,
not `vite dev`: with `devOptions.enabled: false`, development resolves the
registration helper to a development-only no-op stub and never runs the
production worker. `npm run build` generates that worker, and `vite preview`
serves it:

```bash
npm run test:e2e:pwa
```

This uses a dedicated `playwright.pwa.config.ts`, whose `webServer` runs
`npm run build && vite preview` instead of `vite dev`. It is `workers: 1`
because Cache Storage and IndexedDB state persist across reloads within a
context and the specs rely on that. The default `playwright.config.ts`
excludes `e2e/pwa/**` (`testIgnore`) so the two suites never run against the
same server.

`vite preview` only serves the React `dist/` output, so it cannot exercise
anything that depends on the full FastAPI-fronted deployment routing both the
React and legacy Flutter builds (`app/frontend.py`). Specs that need that —
such as service-worker.spec.ts's `/legacy/` scope-isolation check — guard
themselves with the same `test.skip(!SKIP_WEB_SERVER, ...)` pattern
`e2e/smoke/cutover.spec.ts` uses, and are skipped under `test:e2e:pwa`.

## Completion checklist

Run the focused spec, state whether the backend and browser were available,
and report any existing fixture or infrastructure failure separately from the
product result. Do not claim E2E coverage that was not executed.
