# Journiv React frontend

These instructions apply to `frontend/`: the active React,
TypeScript, Vite, Tailwind, and shadcn frontend.

## Context loading

1. Read this file.
2. For UI work, read [`DESIGN.md`](DESIGN.md).
3. Read [`docs/README.md`](docs/README.md).
4. Load only the feature, domain, or engineering documents that the task
   touches.
5. Inspect the current implementation and nearby tests.
6. If the task expands into another concern, load that document then.

Do not recursively read `docs/` or unrelated feature contracts for
completeness. Documentation is progressive-disclosure context; it does not
replace investigating the code and actual API.

## Preserve the existing architecture

Use React, TypeScript, Vite, TanStack Router, TanStack Query, the generated
OpenAPI client, the existing authentication abstraction, design tokens, UI
primitives, and responsive route model. Do not introduce another router, API
client, component library, or client-state framework unless the task explicitly
changes the architecture.

Frontend behaviour must match the actual backend and generated API. If a
requested behaviour needs a missing backend contract, report that gap; do not
invent a fake client behaviour or conceal the missing API.

## Documentation ownership

| Information | Canonical location |
| --- | --- |
| Global visual and interaction design | [`DESIGN.md`](DESIGN.md) |
| Frontend engineering architecture | [`docs/architecture/`](docs/architecture/) |
| Shared product/domain semantics | [`docs/domain/`](docs/domain/) |
| Feature behaviour | [`docs/features/`](docs/features/) |
| E2E harness rules | [`e2e/README.md`](e2e/README.md) |
| Feature-specific known gaps | the feature/domain contract |
| Cross-cutting blockers | [`docs/known-gaps.md`](docs/known-gaps.md) |

Do not add feature implementation detail to `DESIGN.md`. A rule belongs there
only when someone implementing an unrelated screen reasonably needs it.
Document durable contracts, not implementation details already obvious from
code.

## Verification and handoff

Run `npm run verify` before reporting frontend changes. Playwright is separate:
read [`e2e/README.md`](e2e/README.md) before adding or changing a browser test.
For visual work, review the affected surface at 1440, 1024, and 390 pixels in
light and dark themes. Do not claim browser review or tests that were not run.

Report only relevant details: the implementation and routes changed, endpoints
and cache/validation behaviour when relevant, backend gaps, tests and the exact
`npm run verify` result, visual checks for visual work, documentation changes,
and intentionally unsupported behaviour.

