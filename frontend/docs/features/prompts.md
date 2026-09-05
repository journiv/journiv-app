# Prompts feature contract

Prompts are journaling starters: a browsable library of short questions, a
rotating "prompt of the day", and a way to begin an entry from one. The library
is read-only in the current iteration — the prompts come from the backend's
system set (`user_id IS NULL`). User-authored prompts, a Plus prompt library,
and a future authoring workflow are planned; see
[`prompts-backend-followups.md`](prompts-backend-followups.md).

## Placement

Two surfaces, one shared component:

- **`/library/prompts`** — a child of the protected route, rendered as one
  component. It reuses `LibraryWorkspace` (the wide span-2 canvas with a compact
  `PageBar` and one scroll owner), the same shell People / Tags / Moods /
  Activities / Goals and Insights use. Do not invent a new page structure. The
  sidebar entry sits in the **Library** group, nested, like Tags — the route
  name mirrors how Tags graduated to `/library/tags`.
- **The editor prompt picker** — `PromptPickerDialog`, an `AppAdaptiveDialog`
  (centred dialog above 860px, bottom sheet at/below), opened from the "Write
  from a prompt" control between the entry header and the body.

Both mount `PromptBrowser` (`src/features/prompts/PromptBrowser.tsx`). Its
Discover tab owns the daily hero, filter bar, results grid and paged loading;
its Insights tab shows the signed-in writer's prompt-answer history. They pass
only a `variant` (`page` widens the grid; `overlay` is single-column), the row
action label, and the `onSelectPrompt` effect. The page keeps its active tab in
the URL; the editor picker owns its tab locally.

## URL state

`/library/prompts` validates `tab` as `discover` or `insights`, defaulting to
`discover`. Switching tabs replaces only that search value, so a direct link to
the Insights view is shareable. The inactive Base UI `Tabs` panel unmounts, so
the Discover and Insights queries never run together.

## Endpoints

All are free — not Plus-gated.

| Endpoint | Used for |
| --- | --- |
| `GET /prompts/` | The library's offset pages (`items`, `total`, `next_offset`) and single browse/search/filter endpoint. `q`, category, difficulty, and inclusive `min_minutes` / `max_minutes` filters are server-side; the browser loads subsequent pages on demand. |
| `GET /prompts/daily` | The "prompt of the day" hero. **204** once the writer has started an entry from it today → rendered as a "done for today" note. |
| `GET /prompts/random` | Shuffle. **404** (no prompts) disables the control rather than erroring. |
| `GET /prompts/{id}` | The editor reads one prompt to seed the heading and show the banner. |
| `GET /prompts/analytics/statistics` | The Insights tab's current-writer summary, category preferences, and weekly completion trend. |

`GET /prompts/search` remains available for compatibility, but the browser
uses `GET /prompts/` for every search and filter.

`PromptResponse` carries `text`, `category`, `difficulty_level`,
`estimated_time_minutes`, `is_active`, legacy global `usage_count`, and
`answered_count`: the signed-in writer's number of Moments linked to that
prompt. `PromptCard` renders the latter as "Written N times" only when it is
positive. There is no guidance/description field.

## Filtering

The filter bar (`PromptFilters`) sends every active filter to `GET /prompts/`:

- **search** — substring over prompt text and category label (`q`);
- **level** — sent to the API as `difficulty_level`, labelled 1 Gentle · 2
  Thoughtful · 3 Deep · 4 Searching · 5 Profound (frontend labels — the API
  ships only the number; the seed library uses 1–3);
- **duration** — inclusive `estimated_time_minutes` buckets (1–5 / 6–10 /
  11–15 / 20+) sent as `min_minutes` / `max_minutes`;
- **category** — sent to the API as `category`; the response's `category_counts`
  and `all_count` keep the `ToggleGroup` chip row complete while switching
  categories. Counts reflect the active difficulty level and do not narrow as
  the category changes. They also reflect active text and duration filters,
  even when those results span unloaded pages.

## Starting an entry from a prompt

Choosing a prompt links it to the entry through `Moment.prompt_id` (already on
`MomentCreate` / `MomentUpdate` / `MomentResponse`). "Answering" a prompt is an
entry that carries its id.

- **From the library page** → navigates to `/timeline/new?prompt=<id>`.
  `editorSearch` validates `prompt` as a UUID (same rule as `draft`).
- **In the editor** → the picker seeds inline via
  `QuillSurfaceHandle.seedPromptHeading`.

In both cases:

1. the prompt text is placed as a level-3 heading at the top of the document
   (`prependPromptHeading` before mount for the `?prompt=` path;
   `seedPromptHeading` on the live editor for the picker) — `header: 3` is
   inside the editor's Gate-1 delta profile, so a seeded document still saves;
2. `PromptBanner` names the prompt above the body; removing it clears
   `prompt_id` but leaves the seeded heading for the writer to keep or delete;
3. on save, `prompt_id` is sent on `MomentCreate` whenever a prompt is set, and
   on `MomentUpdate` only when it changed (so an ordinary edit never rewrites
   it).

The Reader resolves a saved `prompt_id` with the same single-prompt query and
shows the text in a read-only "Written from a prompt" banner. It intentionally
does not offer a remove control or make a missing prompt a reader error.

`?prompt=` rides along with `?draft=` in `rememberDraftInUrl`, so a reload
before the first save keeps the prompt context. A prompt picked from the
in-editor picker (no URL param) is component state only — a reload keeps the
seeded heading via the local draft but not the `prompt_id` link.

## Loading, empty, error

`PromptBrowser` owns them: shape-matching `Skeleton` while the library loads;
pane-level `StatusView` (tone `danger`, retry) on error; a "no prompts match
those filters" `StatusView` with a clear-filters action when the filtered set
is empty. The daily hero is hidden (not errored) if `GET /prompts/daily` fails —
it is a bonus, not the surface. The Insights tab has separate loading, empty,
and retry states, because it is a separate request.

## Known gaps

- No create / edit / delete UI, no "My prompts", and no Plus prompt library.
- The category count numbers can look surprising when a level or duration
  filter is also active (they describe that narrowed set, by design).

See [`prompts-backend-followups.md`](prompts-backend-followups.md) for the
backend changes each of these needs and how the UI surfaces them.
