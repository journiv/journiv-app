# journiv-backend/frontend

This is the React/Tailwind/shadcn web frontend — the one being actively built
and the one that replaces the Flutter app. See the root `CLAUDE.md` for how
this fits into the rest of the monorepo.

## Before writing any UI here

Read [`DESIGN.md`](DESIGN.md) §1–9, §16–18 and §20 first. They are the rules
that apply to everything: tokens, typography, shape, states, iconography,
motion, responsive behaviour, accessibility, file placement, and the checklist.

Then read the section for the surface you are touching (§10–§15, §21–§26).
Do not skip this because the change looks small — inventing a colour, size,
spacing value or radius instead of using a token is the single most common way
this codebase drifts from its own design system.

**When DESIGN.md and the code disagree, the code is the fact and DESIGN.md is
the bug.** Fix DESIGN.md in the same change that touches the code, or that you
notice the disagreement in. Do not silently follow a stale rule, and do not
silently ignore one you know is wrong.

## Verify before reporting anything done

```bash
npm run verify
```

Runs formatting, lint, the design guard (`lint:design` —
`scripts/check-design-system.mjs`), types, tests, the production build and the
OpenAPI drift check. A green run is not proof the UI looks right — open the
screen at 1440 / 1024 / 390, in light and dark, and look.

If the visuals changed, regenerate the design reference screenshots (see
DESIGN.md §19) and review the diff before calling the work finished.

## Browser tests

`npm run verify` and `npm run test:e2e` are **two separate commands**, and
`verify` deliberately does not run the browser suite — E2E needs a running
backend and an installed Chromium, so folding it in would make the routine
command fail for environmental reasons.

```bash
npm run test:e2e     # Playwright, needs a backend (see e2e/README.md §5)
```

**Before writing or changing any Playwright test, read
[`e2e/README.md`](e2e/README.md).** It is the contract: how authentication and
test data work, which locators are allowed, how time and theme are pinned, and
what belongs in Vitest or the design guard instead.

## Common commands

```bash
npm run dev          # vite dev server
npm test             # vitest
npm run lint:design  # design-system guard only
npm run api:pull     # refresh openapi/openapi.json from the running backend
npm run api:generate # regenerate src/api/generated/ from openapi.json
npm run test:e2e     # playwright (needs a backend)
```

Both `openapi/openapi.json` (minified to one line) and the generated client
under `src/api/generated/` are committed — the root `.gitignore` has a generic
`generated/` rule with explicit `!frontend/src/api/generated/**` negations
below it. After any backend API change: restart the backend, `api:pull`,
re-minify `openapi.json`, `api:generate`, then commit the regenerated
`src/api/generated/` output alongside `openapi.json`.
