# Insights feature contract

Insights is a read-only analysis workspace: how a person's journaling is going —
writing rhythm, streaks, this month's output, per-journal totals, and mood over
time. It is a way of *looking at* your own writing, not a Library entity to
manage.

## Placement

- Route `/insights`, a child of the protected route, rendered as one component
  (no `Workspace`, no detail pane). It reuses `LibraryWorkspace` — the generic
  wide span-2 canvas with a compact `PageBar` and one scroll owner — because
  that composition is not Library-specific. Do not invent a new page structure.
- Sidebar entry lives in the **Views** group (after Timeline / Calendar /
  Media), as a standalone link because its `{ tab, period }` search differs from
  the timeline `NavItem` contract.
- Compact widths get the single pane, like every other Library-style workspace.

## URL state

`validateSearch` guarantees both params:

| Param | Values | Default | Meaning |
| --- | --- | --- | --- |
| `tab` | `overview` \| `mood` \| `journals` | `overview` | Which panel is shown. |
| `period` | `7` \| `30` \| `90` \| `365` | `30` | The shared **Trend period**. |

Switching tabs preserves `period` and vice versa (both are merged into the
existing search on navigate). A direct link is shareable.

## Period semantics

The **Trend period** control shares the tab-strip row (tabs left, control
right), below the summary strip and not in the page header, so it cannot imply
the summary strip is period-scoped. It is shown for Overview and Mood; the
Journals tab shows a static "All time" note in its place. It scopes only:

- the Overview writing-frequency trend (`GET /analytics/writing-patterns?days=`),
- the Mood window (`GET /moods/analytics/statistics?start_date&end_date`,
  computed as the inclusive `period` calendar dates ending today in the viewer's
  zone).

Everything else is fixed by the API: the summary strip and writing streak are
all-time, "This month" productivity is the calendar month, and the Journals tab
is all-time (it shows a plain "All time" caption, no control).

## Endpoints

All are free — **not** Plus-gated (unlike tag analytics), so there is no
`usePlusCapability` gate.

| Endpoint | Used for |
| --- | --- |
| `GET /analytics/writing-streak` | Summary strip (streak, entries, words, avg). |
| `GET /analytics/writing-patterns?days=` | Overview writing-frequency area chart. |
| `GET /analytics/productivity` | Overview "This month" metrics + MoM delta. |
| `GET /analytics/journals` | Journals tab table. |
| `GET /moods/analytics/statistics?start_date&end_date` | Mood overview, stacked-area trend by category, distribution bars. |
| `GET /moods/analytics/streak` | Mood current streak / days logged. |

These endpoints return explicit Pydantic models (`app/schemas/analytics.py`,
`app/schemas/mood_analytics.py`) with `response_model_exclude_none=True`, so the
generated client types are real and a missing optional key stays absent on the
wire. `GET /analytics/dashboard` bundles the four writing endpoints but is not
used here — per-section queries keep each panel's loading/error independent.

## Charts

Recharts via the Base Vega `Chart` primitive (DESIGN.md "Data visualization").
Chart code is feature-local (`src/features/insights/charts/`); it is not promoted
to a shared abstraction until a second feature needs the same mark. Series
colours: `--chart-1` for the single-series writing trend; the three mood
categories map to existing semantic roles (`--success` / `--muted-foreground` /
`--destructive`) via `moodCategories.ts` — no new global palette role. Each chart
ships a visually-hidden table.

Mood colours are identity, not valence (docs/features/library.md), so every mood
mark groups by the backend **category**, never by a mood's own colour.

## Loading, empty, error

Per section: shape-matching `Skeleton` while loading; `StatusView` (tone
`danger`, retry) on error; a short sentence when the API returned nothing for
the window. The Mood tab is entirely empty-stated when `total_logs === 0`.

## Known gaps

- No mood calendar heatmap and no average-mood-by-weekday yet (the legacy
  Flutter screen had placeholders for both). Deferred, not refused.
- `GET /moods/analytics/streak` has no `longest_streak` field; only the current
  streak and total days logged are shown.
- "Entries this week" is not shown — it would be a fixed 7-day figure next to a
  user-selectable period.
