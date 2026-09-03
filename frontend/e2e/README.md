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

## Completion checklist

Run the focused spec, state whether the backend and browser were available,
and report any existing fixture or infrastructure failure separately from the
product result. Do not claim E2E coverage that was not executed.

