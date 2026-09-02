# Journiv Design System — v0.2

**Status:** v0.3 — Base Vega + Minimal Neutral is the default visual language
across the whole product: foundation, shell, Timeline, reader, editor, Journals,
Library, Settings and Personalization are all built on it. What is still
provisional is called out in §21, not left for you to discover.

**Audience:** anyone — human or agent — building UI in `journiv-backend/frontend`.
Read sections 1–9 before writing any component. Read the specification for the
surface you are touching (§10–§26) before changing it.

**The one rule that matters most:** if you are about to invent a value — a colour,
a font size, a spacing number, a radius — stop. Use a token or a role. If none
fits, add one here first and explain why.

**When this file and the code disagree, the code is the fact and this file is
the bug.** Fix this file in the same change — do not silently follow a rule you
can see the code has outgrown, and do not silently ignore one you know is being
violated. If you cannot fix it in the same change, record it under §21 as a
release blocker, not as a footnote.

**Verify with one command:** `npm run verify`. It runs formatting, lint, the
design guard, types, tests, the production build and the OpenAPI drift check.
`scripts/check-design-system.mjs` is a **static, source-level** guard — it
parses `.css`/`.ts`/`.tsx` files and this file's own prose, and never launches
a browser. It mechanically enforces: raw colours (in CSS, inline styles, and
bracketed Tailwind utilities), px font sizes, stray `!important`, arbitrary
spacing/font-size Tailwind values, direct `crypto.randomUUID` calls, an
undefined CSS custom property (a `var(--x)` that resolves to nothing), a dead
token (declared, never consumed), an unlisted `@media` breakpoint, a broken
link from this file to a `src/...` path, and a handful of literal token facts
(the radius scale, the spacing scale, `--bar-height`, `--tap-target`, …) that
must match between `tokens.css` and this file's prose — all fail the build
with the fix printed. **What it does not check:** anything that requires a
rendered page — computed contrast, actual visual layout, whether a component
looks right. That is Playwright's job (§19); this script stays
static and cheap. A green run is not proof the UI looks right: open the screen
at 1440 / 1024 / 390,
in light and dark, and look.

---

## 1. What Journiv is

Journiv is a private personal journal. The nearest relatives are Day One and
Apple Journal. It is **not** Linear, Notion, Jira, an analytics dashboard, or an
email client, even though the desktop layout happens to have three panes.

The product exists for one loop:

> I sit down. I write about my day. I come back months later. I enjoy reading it.

Every visual decision is judged against that loop.

**It should feel:** calm, personal, refined, quiet, trustworthy, content-first,
excellent to read and to write in for half an hour at a time.

**It should not feel:** sterile, characterless, prototype-like, enterprise,
busy, or decorative or flat.

---

## 2. Design principles

Five rules, and they are the whole set. Resist growing them.

1. **Vega builds the control _and composes the screen_; Minimal Neutral colours
   it.** A generic control's markup, variants, sizes, states and class strings
   come from `https://ui.shadcn.com/r/styles/base-vega/<name>.json`,
   unmodified. Its appearance comes from the token values in
   [`tokens.css`](src/styles/tokens.css). If you are editing a Tailwind class
   inside `src/components/ui/`, you are probably making a mistake — change a
   token instead. The same applies one level up: where a generic _arrangement_
   has a registry primitive that fits — a titled group of controls, a labelled
   field, a list of settings, an empty state, a set of related actions — use it
   rather than rebuilding it from a `<div>` and a stylesheet (§18). Where
   Journiv's layout is genuinely its own, compose it yourself; the registry is
   the default vocabulary, not a catalogue of permitted screens.
2. **Journiv CSS expresses product, not appearance.** Layout, the reading
   measure, journaling semantics, responsive behaviour, journal and mood
   colour, editor and media workflows. It does not redefine buttons, inputs,
   menus, rows, chips, checkboxes or segmented controls.
3. **Interactive things look interactive at rest.** Every control carries at
   least one of: a border, a filled surface, or `shadow-xs` — _before_ hover.
   Hover and focus add to that; they are never what first reveals the
   affordance.
4. **Elevation has four working steps and each has one job** (§5). A shadow is
   a statement about what a surface is, not decoration.
5. **Content is quieter than chrome — and chrome is as composed as Vega is.**
   This rule has two halves and neither may be quoted without the other.
   _Content:_ the reader is the most content-focused surface in the product —
   no cards around entries, no dividers between paragraphs, no chips where
   prose will do. _Chrome:_ everything that is not the reading experience —
   Settings, Journals, the Library, dialogs, admin — gets the standard Base
   Vega treatment, and a group of controls that clearly belongs together,
   sitting loose on a canvas with nothing to bound it, is a defect rather than
   restraint. The content half is a licence to be quiet **inside the reading
   measure**; it is never a reason to leave a chrome surface unstructured. It
   does not follow that every chrome surface must be a card — see §5 for which
   surface is which, and for when a card is decoration.

Two older principles survive intact and are folded in above:

- **Never invent data.** If the API did not return it, it does not appear on
  screen. A missing title is a missing title, not "Untitled".
- **Honest states.** Loading, empty and error are designed screens, not
  leftover sentences (§16).

---

## 3. Tokens

The foundation is **shadcn Base Vega** component construction (preset
`bIkeymG`, the registry configured in `components.json`) coloured by the
**TweakCN Minimal Neutral** theme (`cmho4nr9l000h04l1gu419ckw`), defined in
[`src/styles/tokens.css`](src/styles/tokens.css) + the `@theme` / `@theme
inline` blocks in [`src/styles/index.css`](src/styles/index.css). Components
consume the stock semantic names — `--background`, `--card`, `--popover`,
`--muted`, `--primary`, `--border`, `--ring`, `--sidebar` … — never a raw
colour.

Minimal Neutral's contribution over stock neutral is entirely tactility, and
every one of its moves matters: `--secondary` at `oklch(0.87 0 0)` rather than
`0.97` (so a secondary button is visible at rest), `--muted` / `--accent` at
`0.95`, a lifted `--accent` in dark, solid dark borders instead of 10% white, a
`--card` that differs from `--background`, `--radius: 1rem`, and a real shadow
scale. Do not "simplify" any of them back toward stock neutral.

**`--primary` is neutral**, as it is in both references. Journiv's blue is
`--brand`, and §"Journiv's own values" below lists every place it may appear.

Dark mode is the **`.dark` class** on `<html>` (set by
[`src/app/theme.ts`](src/app/theme.ts)), matched by `@custom-variant dark` in
`index.css`. The `system` / `light` / `dark` tri-state and the per-device
storage key are unchanged.

### Journiv's own values

Only a handful. Everything else is stock. Anything not on this list is drift
and should be removed, not documented.

- **Brand** — `--brand` / `--brand-foreground` are Journiv's blue (hue 269, the
  `#405DE6` the Flutter client ships), and they are what a user's accent picker
  rewrites (§25). `--primary` is **neutral**, as in both references. Blue is
  allowed in exactly four places, and a fifth is a bug:
  1. **The one filled brand control** — `Button variant="brand"`, used only for
     the sidebar's "New entry". Writing is the thing Journiv exists for; every
     other surface-primary action is `variant="default"` (neutral).
  2. **The focus ring** — `--ring: var(--brand)`. This is the product's single
     global focus affordance, and Minimal Neutral's neutral ring at Vega's
     `ring-ring/50` × 3px reads too faint to serve as one. Both an identity
     moment and an accessibility improvement.
  3. **The selection rail** — the 3px `::before` on a selected nav item,
     Timeline row or Settings nav item. The selected _background_ is neutral
     `--accent`; only the rail is blue.
  4. **Text that is a link** — prose links (`prose.css`) and inline text links
     that _navigate_. A near-black link is not a link. This does not extend to
     `Button variant="link"`, which is a control wearing link styling; that
     stays on neutral `--primary` like every other control.

  Because three of those four put text on or beside the accent, `--brand` is
  the one token in the system with a hard contrast obligation in both
  directions: it must clear AA against `--background` and `--card` (as link
  text) _and_ against its own `--brand-foreground` (as a filled control). Light
  and dark therefore need different lightnesses and opposite foregrounds — see
  §25, and [`src/features/theme/accent.ts`](src/features/theme/accent.ts),
  which is where that rule is enforced rather than restated.

  Explicitly **not** blue: hover surfaces, selected backgrounds, badges,
  checkboxes, switches, toggle-group selection, progress, charts, status pills,
  calendar "today", or any `default` Button.

- **Fonts** — `--font-sans` is DM Sans (bundled); `--font-reader` is the
  reader/editor prose font (falls back to `--font-sans`). Alternates load lazily
  via [`src/features/theme/fonts.ts`](src/features/theme/fonts.ts). No remote
  fonts. The `bIkeymG` preset names Inter, but Minimal Neutral — which is
  authoritative for theme values — ships DM Sans, and DM Sans is already
  bundled. A deliberate, reasoned divergence from the preset code.
- **Derived roles** — `--line-strong`, `--danger-surface`, `--danger-border`.
  That is all of them. Each is a **`color-mix` of a stock token**, so an
  imported user theme flows through for free. `--line-strong` is for the two
  places a rule must read heavier than a structural hairline (the prose
  blockquote and the reader's note). `--danger-surface` / `--danger-border`
  match Vega's own `bg-destructive/10` and `border-destructive/40`, so a
  hand-built surface and a `Button variant="destructive"` cannot drift apart.
  There is no `--state-hover`, `--state-selected`, `--accent-surface`,
  `--accent-border` or `--focus-ring`: hover is `--muted`, selection is
  `--accent`, the ring is `--ring`. Those are stock roles and need no alias.
  One stock slot, `--sidebar-border`, is _also_ defined as a `color-mix` rather
  than a literal — Minimal Neutral's dark values would leave it invisible where
  it is used (the Settings nav seam); see §3 "Surfaces".
- **`--success`** — a semantic colour used for a saved/success `role="status"`
  notice (editor autosave-style confirmations) and the Integrations
  "Connected" dot. It is not a general "positive" accent.
- **Layout / motion constants** — `--nav-width`, `--bar-height`,
  `--reader-measure`, `--reader-gutter`, `--tap-target`,
  `--overlay-max-height`, `--space-*`, `--ease`, `--duration-*`. Not theming.
  `--overlay-max-height` (85svh) caps an adaptive dialog; it is `svh` rather
  than `vh` because iOS Safari's `vh` measures the largest viewport, which
  would put a dialog's footer under the browser chrome.
- **On-media** — `--overlay-scrim`, `--text-on-overlay` are deliberately
  theme-independent (they sit on a photograph, not a Journiv surface).

`--journal-accent`, `--mood-accent` and `--entity-accent` are **not** defined
globally. They are set inline from API data by `JournalDot`, `MomentMeta` and
`EntityGlyph`, and fall back to `--muted-foreground` when absent. They are the
only hue besides `--brand` that enters the chrome. ARGB→hex is `colorFromArgb`
in [`src/lib/color.ts`](src/lib/color.ts).

### Surfaces

The canvas is `body`, painted `--muted` by the one deviation from base-vega's
own reset (`@layer base` in [`index.css`](src/styles/index.css)). Everything
else lifts off it:

| Role                               | Token          | light | dark  |
| ---------------------------------- | -------------- | ----- | ----- |
| App canvas / `body`                | `--muted`      | 0.95  | 0.269 |
| Nav pane — quietest chrome         | `--sidebar`    | 0.985 | 0.269 |
| List pane — workspace              | `--background` | 1.0   | 0.205 |
| Reader / detail — content          | `--card`       | 0.995 | 0.165 |
| Popovers, menus, dialogs           | `--popover`    | 1.0   | 0.205 |
| Settings canvas — inside the modal | `--muted`      | 0.95  | 0.269 |
| Cards and panels on a canvas       | `--card`       | 0.995 | 0.165 |

**Management surfaces are a canvas plus raised `--card` panels** (§5). Settings
uses `--muted` for that canvas, because every control inside it is in a card.
Journals and the Library use `--background` instead — `.jv-library` sets it on
itself rather than inheriting the reader's `--card`, and Journals simply keeps
its column's own surface.

**Why not `--muted` everywhere:** Minimal Neutral's dark palette gives
`--muted`, `--secondary`, `--border` and `--input` the _same_ value,
`oklch(0.269 0 0)`. A `--muted` canvas is therefore only safe under content
that is entirely inside cards. Put a bare control on it — a `secondary` button,
an `Input`, anything whose resting affordance is a `--border` — and in dark it
loses its edge completely, breaking principle 3. Journals and the Library carry
their primary action and their search field directly on the canvas, so they get
`--background`, where those tokens still separate. Check any new canvas
decision in dark before shipping it; light mode will not show this.

The same collision hits the **seam between a `--sidebar` nav pane and a
`--muted` canvas beside it**: in dark `--sidebar`, `--muted` and `--border` are
all `oklch(0.269 0 0)`, so a `--border` hairline there is invisible and the two
panes read as one flat surface (the app shell escapes this because its nav sits
next to `--background`, a real fill step; Settings' nav sits next to `--muted`).
`--sidebar-border` carries that seam — a `color-mix` toward `--foreground`,
~0.918 in light and ~0.326 in dark, lighter than `--line-strong` because it is
structure, not emphasis. It is the only place that token is used.

The `--sidebar` == `--muted` half of that collision also swallows the **selected
item of a stock `ToggleGroup` on the nav** — its default `bg-muted` fill is a
visible step on `--sidebar` in light but the same colour in dark, so you cannot
tell which option is active. The sidebar theme control (`.jv-theme-control`)
therefore takes `--accent` for the selected segment — the product's selection
role (§6), which lifts off `--sidebar` in both themes.

**Minimal Neutral inverts the tonal direction in dark**, on purpose: chrome is
the lightest tint and content is the deepest, so the reader is still the
surface furthest from the chrome in both themes. Do not "correct" dark to
match light. `--muted` as the canvas is not an invention — it is the ground the
Minimal Neutral reference itself sits on, and the only MN token that reads as a
real canvas tint in light mode.

### Rule

Product CSS goes through `var(--token)` — never a raw `#hex` / `oklch()` /
`rgb()` (the design guard enforces this in every `.css` outside the value
layer). This is what keeps the app themeable: a pasted theme reaches the reader
and editor only because they resolve from the same stock tokens. shadcn
registry components in `src/components/ui/` are Tailwind-class-only and read the
`--color-*` map in `index.css`; do not add a scoped stylesheet for one.

**The one sanctioned exception is a data palette, not a theme colour.**
[`src/lib/journalColors.ts`](src/lib/journalColors.ts) (22 `JournalColor`
presets) and `ENTITY_COLOR_PRESETS` (people/activity/goal-group colours) are
literal hex arrays. They are content a user picks per-journal or per-group —
matching the Flutter client's own fixed palette — not a piece of Journiv's
theme, so they sit outside `color-mix`/token derivation on purpose. Do not add
a third such array without naming it here; do not use either array's literals
for anything that _is_ chrome.

### Shape, depth, spacing, layout

Shape: one root radius, `--radius` 1rem — Minimal Neutral's own — and Base
Vega's derived scale on top of it, declared in the `@theme inline` block in
[`index.css`](src/styles/index.css): `--radius-sm` (×0.6) · `--radius-md`
(×0.8, the radius of every button and input) · `--radius-lg` (×1) ·
`--radius-xl` (×1.4, dialogs and drawers) · `--radius-2xl` · `--radius-3xl` ·
`--radius-4xl` (pills). **`calc()` is how this scale is built.** The steps must
stay in fixed proportion, or upstream's `rounded-md` button and `rounded-xl`
dialog stop meaning what the registry intends — which is exactly the bug the
previous four-literal scale caused. There is no `--radius-xs`: Vega's smallest
named step is `sm`. Shape is not user-configurable.

Elevation: Minimal Neutral's `--shadow-2xs` … `--shadow-xl`, declared in the
plain `@theme` block in [`index.css`](src/styles/index.css) (not tokens.css —
the Tailwind utility namespace and the custom property share the name
`--shadow-*`, so bridging them would be self-referential). Four steps have a
job and the rest exist only for completeness — see §5.

Overlay backdrops carry the stock base-vega treatment: a `bg-black/10` scrim
plus a progressive-enhancement `backdrop-filter` blur behind
`supports-backdrop-filter:`. `Dialog`, `AlertDialog`, `Drawer` and the two
hand-built Base UI surfaces (Settings, the AppShell nav drawer) all share the
same class string, so the scrim does not change as an adaptive overlay crosses
860px (§9). **That is the only blur in Journiv** — do not add another, and
never put one on a non-overlay surface.

Spacing: 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64 as `--space-1 … --space-16`. Do not
write `mt-[13px]`.

Layout: `--nav-width`, `--list-width-min/max`, `--bar-height` 52px,
`--reader-measure` 68ch, `--reader-gutter`, `--tap-target` 44px.

### Measured contrast

"page" is `--background` (the reader/card reading surface); "canvas" is
`--sidebar` (the app shell ground behind the panes, and `body`'s own
background — see `base.css`). Ratios are WCAG relative-luminance contrast,
computed from the `oklch` literals in `tokens.css` — Oklab → linear sRGB →
relative luminance, not eyeballed.

|                                | light  | dark   |
| ------------------------------ | ------ | ------ |
| `--foreground` on page         | 19.8:1 | 19.0:1 |
| `--foreground` on canvas       | 19.0:1 | 17.2:1 |
| `--muted-foreground` on page   | 5.5:1  | 7.6:1  |
| `--muted-foreground` on canvas | 5.3:1  | 6.9:1  |

All four clear AA (4.5:1) with real margin in both themes. `--muted-foreground`
is the tightest pair by design — it is metadata, not body copy — so treat
anything below **5:1** on either surface as a regression, not a rounding error.

Disabled text (`opacity: 0.55` on `--foreground`, §6) lands around 4.4:1 in
light mode, under the AA floor. This is expected and not a bug: WCAG 1.4.3
explicitly exempts inactive UI components and their text, precisely because a
disabled control's whole job is to read as visually muted. Do not "fix" a
disabled state by boosting its contrast — that defeats the state.

These numbers describe the _stock_ tokens. A user's imported accent or theme
(§25) can shift any of them; personalization is opt-in and deliberately not
contrast-checked on the way in.

---

## 4. Typography

DM Sans is the default for everything, self-hosted. Chrome (`--font-sans`) is
DM Sans and nothing else. The **reader and editor prose font** (`--font-reader`,
consumed by `prose.css` and — since it carries the headline too —
`.jv-entry-title`) defaults to DM Sans but is opt-in re-fontable through
Personalization (§25) over the bundled set: DM Sans plus one serif alternate,
Lora. **Do not add a third family**, and do not add a monospace face until a
real product feature needs one.

Roles are classes in [`src/styles/base.css`](src/styles/base.css). Compose them;
do not invent size/weight pairs.

| Role                | Size / weight / leading  | Used for                           |
| ------------------- | ------------------------ | ---------------------------------- |
| `.jv-display`       | 28 / 680 / 1.2           | pane titles                        |
| `.jv-entry-title`   | clamp 30–39 / 650 / 1.14 | entry title, **reader and editor** |
| `.jv-section-title` | 15 / 620                 | section headings                   |
| `.jv-body`          | 15 / 400 / 1.55          | UI prose                           |
| `.jv-moment-title`  | 15 / 600 / 1.35          | Timeline row title                 |
| `.jv-excerpt`       | 14 / 400 / 1.5           | Timeline excerpt                   |
| `.jv-label`         | 13 / 500                 | form labels, nav                   |
| `.jv-meta`          | 12.5 / 500, tabular-nums | metadata, times                    |
| `.jv-caption`       | 12 / 400                 | captions, notices                  |

**Sentence case everywhere.** Journiv has no uppercase letterspaced eyebrows.

Long-form prose lives in [`src/styles/prose.css`](src/styles/prose.css) as
`.jv-prose`: **17.5px / 1.7 / 68ch**, paragraph spacing 0.85em, in-body headings
at 1.4 / 1.2 / 1.05em. In-body headings must stay visually subordinate to the
entry title.

Two specificity conventions you must not remove:

- `.jv-prose.jv-prose <element>` — doubled so these rules beat a vendor editor
  reset (`.ql-editor p { margin: 0 }`) regardless of import order.
- `.jv-prose.jv-prose` base — doubled because the editor adds its own class to
  the _same_ element (`ql-container` ships a 13px `font-size`).

Both are commented in place. Deleting the doubling silently reverts the reader
to 13px with no paragraph spacing.

---

## 5. Shape, surfaces and elevation

**Elevation has four working steps and each has one job.** This replaces the
old "no shadow outside overlays" rule, which is what stripped `shadow-xs` out
of four upstream components and made resting controls unreadable.

| Step        | Job                                                                                                                                                         |
| ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `shadow-xs` | A resting control: `outline` Button, Select, Combobox, InputGroup, ToggleGroup. This is base-vega's own choice — never remove it from a registry component. |
| `shadow-sm` | A grouped or detached surface: a `Card`, a floating pane, the application shell.                                                                            |
| `shadow-md` | Popovers, dropdown menus, tooltips.                                                                                                                         |
| `shadow-lg` | Dialogs, drawers, sheets, the Settings modal.                                                                                                               |

`shadow-2xs` and `shadow-xl` exist in the scale for completeness and currently
have no consumer. Nothing else gets a shadow — a shadow is a statement about
what a surface _is_, not decoration. No gradient, no glow. The one blur is the
overlay backdrop's `backdrop-filter` (§3).

### The content / chrome line

Every surface in Journiv is on one side of a single line, and the line decides
its treatment. Ask: **is the user reading, or operating?**

|                       | **Content** — reading and writing                                                                                         | **Chrome** — operating                                                                              |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Where                 | The reader column, prose, the editor's writing area, Timeline rows and the Media grid (the list of what there is to read) | Settings, Journals, the Library, dialogs, sheets, menus, admin, auth, the shell itself              |
| Surface               | No card, no panel, no box. The page **is** the surface.                                                                   | Base Vega's own surfaces where they fit: `Card` for a coherent group, a panel for a list of objects |
| Separation            | Whitespace, rhythm, typography. Hairlines only where a real boundary exists                                               | Edges, hairlines, dividers, `shadow-xs` — the standard registry treatment                           |
| Density of affordance | As little as the job allows                                                                                               | As much as Base Vega itself uses; a control is identifiable at rest (§2.3)                          |
| When in doubt         | Quieter                                                                                                                   | **Reach for the registry first**                                                                    |

The two "when in doubt" cells point in opposite directions on purpose. On the
content side, the burden of proof is on adding structure. On the chrome side it
is on inventing something instead of using what Base Vega already provides.

**This is a default, not a template.** Base Vega is the vocabulary chrome is
written in; it is not a specification for what every page must look like.
Journiv composes its own screens — the three-pane shell, the settings modal,
the Library workspace and its push-detail, the editor — and none of those are
registry examples. Hand-roll composition when Journiv has a real product or
layout requirement, and do it without apology or paperwork: **a screen does not
need a §27 divergence because its legitimate layout has no registry
counterpart.** §27 is for diverging on a _component or token_ the registry does
define. What is being ruled out is the other thing — reaching past a primitive
that fits, and rebuilding it in a stylesheet, to preserve a look.

**A journal entry is never in a card**, and nothing inside the reading measure
is. That is the line the product turns on. It is a statement about _reading
content_ only. Do not generalise it into "no boxes anywhere": a previous
revision did, and the result was a Settings screen, a Journals screen and a
Library that were flat sheets of text with nothing to grip — technically
token-correct and visually unfinished.

**Cards and panels.** A `Card` earns its place by grouping — it says "these
things belong together, and they are separate from those". Use it where that is
true: a settings section, the auth surface, a stat block, a form, the reader's
"write about this" invitation. It is wrong around a single value (the card is
around the _group_, never around one row) and it is equally wrong as
decoration — a card around a lone paragraph, or around content that has no
sibling to be distinguished from, adds a border and no meaning. Chrome is not
required to be cardified; it is required to be _structured_, and sometimes a
heading and a divider are the honest structure. A list of objects being managed
(journals, the Library directories) is a **panel**: `--card` fill, a `--border`
edge, `--radius-lg` and `shadow-xs`, rows flush inside and divided by hairlines.
A card with actions ends in a `CardFooter` carrying `border-t`; a button left on
the canvas below a card reads as belonging to the page rather than to the form
it submits.

**Rows.** One row treatment across the product, and it is base-vega's `Item`:
a resting surface, `--muted` on hover, `--accent` when selected. Timeline rows,
Library rows, Journal rows, Settings rows and action-sheet rows all read the
same way.

Two things about a row's surface, and both have been got wrong:

1. **The surface belongs to the row, not to a child of it.** If the whole row
   navigates, the hover covers the whole row — the trailing `⋯`, the status
   pill, and anything that wraps onto a second line at narrow widths. Putting
   it on the inner link instead leaves a grey block over part of the row that
   does not match the hit area. `.jv-lib-row--link` owns it, not
   `.jv-lib-row__hit`.
2. **A row's shape follows its container.** Flush inside a panel that clips to
   its own radius (the Settings index, Journals) — no per-row radius and no
   inner padding on the panel, or the highlight floats inset with a second
   radius inside the first. Rounded when the rows are gapped items in a group
   (Library grids, nav rails) or sit on an open canvas (Timeline — content
   side, where rhythm and the hover target separate them).

`ItemSeparator` is for genuinely distinct groups.

**Borders.** `--border` for every structural edge — pane, bar, card, row group.
`--line-strong` only where a rule must read heavier than a hairline: the prose
blockquote and the reader's note. `--input` is the border of an input, and only
that.

**The shell is one surface, not three.** The application canvas is `body`
(`--muted`); the shell is a single rounded, bordered surface sitting on it with
`shadow-sm`, and the three panes are flush inside it, divided by `--jv-seam` —
a _faded_ `--border` (`color-mix` toward transparent), declared once on
`.jv-shell` in [`shell.css`](src/features/shell/shell.css). A three-way A/B
test (§25) put hard `--border` hairlines, these faded seams and a no-frame
"airy" split side by side; the faded seams keep every pane's edge while
reading calmer, and the airy split reproduced the old failure — the gaps read
as a dashboard, and the journal is not one. The frame and its `shadow-sm`
stay; only the internal division softened.

Below 860px the shell goes full-bleed — no margin, no radius, no shadow. A
phone should not spend 16px of its width on a frame, and a rounded corner on a
full-height pane reads as a mistake rather than as elevation.

**The outer border is invisible in light, and that is correct.** Minimal
Neutral gives `--border` and `--muted` the same value (`oklch(0.95 0 0)`), so
the shell's edge against the canvas is carried by `shadow-sm` rather than by
the line (the shell fades it one step further toward transparent so it never
reads as a hard rectangle around the app). The same border _is_ visible on the
panes inside, which are lighter. Do not invent a darker edge token to "fix"
this — it is the reference's own relationship between the two, and the internal
seams plus the shadow carry the structure.

---

## 6. Interaction states

| State         | Recipe                                                           |
| ------------- | ---------------------------------------------------------------- |
| rest          | a border, a filled surface, or `shadow-xs` — always at least one |
| hover         | `--muted` background; text lifts to `--foreground`               |
| pressed       | shadcn `Button`'s own `active:translate-y-px` — see below        |
| selected      | `--accent` background **plus** a 3px `--brand` rail              |
| focus-visible | see below — it is not the same treatment everywhere              |
| disabled      | opacity 0.55, `cursor: not-allowed`                              |
| loading       | `StatusView` with a spinner, or a shape-matching `Skeleton`      |
| error         | `StatusView` with `tone="danger"` and a retry action attached    |

**Selection is never communicated by colour alone.** The sidebar and the Timeline
both pair the tinted background with an accent rail. Both also set
`aria-current="page"`.

**Secondary row actions may rest hidden on a pointer device.** A Library or
Journals row's `⋯` is `opacity: 0` until the row is hovered or something inside
it takes focus. This does **not** contradict "interactive things look
interactive at rest" (§2.3): that rule is about the control the row is _for_ —
opening the person, the journal, the tag — and that control is a whole row with
a title, a mark and a hover surface. The `⋯` is the secondary action on top of
it, and a list of eight people should read as eight people, not as eight people
and eight menu buttons.

The permission is narrow and comes with all of these, together:

- Hiding is scoped to `@media (hover: hover) and (pointer: fine)`. Where the
  primary pointer cannot hover — a phone, a tablet, a touchscreen laptop — the
  action is never hidden at all.
- `opacity: 0`, never `display: none` or `visibility: hidden`. The control stays
  in the tab order and in the accessibility tree.
- It reveals on `:focus-within` as well as `:hover`, so a keyboard user sees
  what they have landed on.
- It stays visible while its own menu is open (`:has([aria-expanded="true"])`).
- Everything it offers is reachable another way — the row opens to a detail
  view with the same actions.

Anything that is the _only_ route to a capability is not a secondary action and
does not get this treatment. Verified rendered, not assumed: see the note in
[`journiv.css`](src/components/journiv/journiv.css).

**Pressed is a shadcn behaviour, not a Journiv token.** Every `Button` nudges
down one pixel on `:active`. Hand-built product rows (nav items, Timeline rows,
Library rows) have hover and selected states but no separate pressed treatment
today — do not invent a `--state-pressed`-style token for them without a real
design reason; there was one and it had no consumer.

**Focus is two treatments, by design, not by drift.** Native and
product-pattern elements (`base.css`) get a 2px `--ring` outline, 2px
offset. Every `src/components/ui/*` registry component gets its own upstream
treatment instead — `outline-none` plus a 3px `focus-visible:ring-ring/50` and
a border-colour change — because the shadcn ring pattern (`focus-visible:ring`)
needs the border+ring pairing to read correctly on small controls, and
rewriting it would violate §18's "keep close to upstream" rule. Both resolve
from `--ring`, so a personalized accent reaches both; do not mix the two
treatments on one control, and do not add a third.

**Actions.** The stock base-vega vocabulary, plus one documented Journiv
variant. The `primary` / `danger` aliases are gone — use the registry's names.

| Variant       | Use                                                                                                                                                                                 |
| ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `default`     | The one primary action on a surface. Filled, neutral `--primary`.                                                                                                                   |
| `brand`       | **Journiv's one filled blue control**: the sidebar's "New entry". Nowhere else.                                                                                                     |
| `secondary`   | The workhorse — an action that is not the surface primary.                                                                                                                          |
| `outline`     | A secondary action that needs a visible boundary (dialogs, toolbars).                                                                                                               |
| `ghost`       | Tertiary — icon buttons, inline row actions.                                                                                                                                        |
| `destructive` | The destructive action on a surface, including the final confirm in a confirmation dialog. Tinted, never filled — destructive should read as serious, not as the surface's primary. |
| `link`        | Inline text acting as a control.                                                                                                                                                    |

Exactly one `default` (or `brand`) per surface. `default` is the registry's own
default variant, exactly as upstream — so **every `<Button>` states its variant
explicitly** rather than relying on a Journiv-flavoured default. Cancel and Done
must never look identical. `IconButton`'s own `variant` prop (`ghost` |
`secondary`) is a narrower, icon-only vocabulary that maps its `secondary` to
the Button's `outline` — an icon control almost never wants a filled
`secondary` background.

---

## 7. Iconography

Lucide only. Sizes: 13 (inline metadata), 15–16 (buttons), 19 (bar controls),
20–22 (`StatusView`). Default stroke.

Every icon-only control uses `IconButton`, which **requires** a `label` and
projects a `::after` hit area of at least `--tap-target` (44px) regardless of the
visual box. A 30px toolbar button still has a 44px touch target. Never shrink the
hit area to match the icon.

**The 44px rule is about the target, not the control.** Base Vega's sizes are
compact on purpose — `h-9` buttons, 32px `icon-sm` — and Journiv keeps them.
Inflating every control to 44px to satisfy a checklist would be a different
design system, and a worse one. Meet the number by growing the _hit area_
instead. In order of preference:

1. `IconButton`'s projected `::after` — the default for any icon-only control.
2. A row or list item whose own `min-height` is `--tap-target`, with the
   control stretched inside it.
3. A transparent target box around a small visual mark. The accent swatches are
   the example: a 28px dot inside a 44px button, drawn by `::before`
   (`settings.css`).

There is one case where projecting a hit area is **wrong**: controls that sit
flush against each other, like the three segments of `ListViewSwitch`. A 44px
`::after` on a 32px segment overlaps its neighbours, and the last one in the
DOM wins — the user aims at Calendar and gets Media. There, grow the control
itself, and only where the pointer is coarse (`@media (pointer: coarse)`).

Text controls at Vega's 36px are accepted as they are. They clear WCAG 2.5.8
(24×24) comfortably, they are separated by real spacing, and their label is a
much larger target than an icon.

**A journal is identified by its own colour, never by a repeated glyph.** The
sidebar's Journals group is dots (or a chosen icon in the journal's own hue,
below), never a book icon repeated down the list — a shared icon would tell
journals apart from everything else, not from each other, which is not the
job. Fixed destinations that are not journals (Timeline, Calendar, Media,
People, Tags, Moods, Activities, Goals) may carry a distinguishing icon each,
because there the icon's job is exactly to tell different _kinds_ of
destination apart.

> **A journal may carry a chosen icon.** `JournalResponse.icon` holds one key
> from the curated Lucide set in [`src/lib/journalIcons.ts`](src/lib/journalIcons.ts).
> When present, `JournalDot` draws that glyph **in the journal's own hue** in
> place of the dot; it is still the one place colour enters the chrome (§3), and
> it is still exactly one mark per journal. The picker offers only that set.
> An unrecognised value — notably the Material Symbols names the Flutter client
> writes to the same field — falls back to the plain dot on the web. There is no
> shared icon vocabulary between the clients yet; the colour dot is the common
> ground.

> **Mood icons are not renderable with Lucide.** `MoodResponse.icon` is a
> Material Symbols name (`sentiment_very_satisfied`). Render mood as its colour
> dot plus its name. Do not guess a mapping.

---

## 8. Motion

One duration (`--duration-fast` 110ms) and one easing curve for
product-pattern colour transitions (hover, selected). Dialog and drawer entry
animate too, but through the registry's own Tailwind `duration-100` utility,
not this token — see §18 on not re-skinning `components/ui/*`. Motion is
allowed for: hover/selected colour transitions, drawer and dialog entry, and a
loading spinner. Nothing else animates.
`prefers-reduced-motion` is honoured globally in `base.css` — the only sanctioned
`!important` in the product.

---

## 9. Responsive behaviour

Two _layout_ breakpoints, expressed in CSS, and no more. **Do not introduce JS
breakpoint state** for layout. Two narrow exceptions, both named here and
nowhere else: Settings' single `matchMedia` read at navigation time (§23),
which is not reactive; and
[`useCompactViewport()`](src/lib/useCompactViewport.ts), which _is_ reactive but
chooses an overlay's **primitive**, not a layout — see "Adaptive overlays"
below. Only the three adaptive overlays may call it; feature code never asks
how wide the window is.

| Width      | Layout                                                           |
| ---------- | ---------------------------------------------------------------- |
| > 1100px   | nav ∥ list ∥ page, all persistent                                |
| 861–1100px | list ∥ page; nav moves into a drawer, reached from the `PageBar` |
| ≤ 860px    | one pane per screen; browser history is the navigation           |

**A component may reflow at its own width — a third kind of breakpoint, not a
layout one.** A settings row switching from stacked to two-column, a stat grid
dropping from four columns to two, a toolbar wrapping — none of that is "the
app's layout changing," and none of it needs to line up with 860/1100.
Current examples: `settings.css` (620px row layout, a container query on the
named `jv-settings-body` container), `users.css` (620/470px column budget,
container queries on the named `jv-users-table` container), `tags.css` (520px
stat grid, 640px controls wrap), `editor.css` (34rem, conflict banner).

**Use a container query, not a viewport query.** The component lives inside a
pane whose width it does not control, and inside the settings modal that width
is a fixed fraction of a fixed-width dialog — so a viewport query is measuring
the wrong thing entirely.

The Users table is the worked example, and it is worth reading before writing
one of these. Its viewport queries were wrong twice over. At 1440px the modal
caps at 1050px, the nav takes 220 and padding takes the rest, so the table gets
**732px** — but a `max-width: 860px` _viewport_ query does not fire at 1440, so
six columns laid out into 732 and the last two ran off the end. Below 1101px
the modal goes full-bleed and the nav collapses, so the same table gets
**928px** — wider at a _narrower_ viewport. Any rule keyed to the window was
going to be wrong at one end or the other.

Three things follow, and all three are the actual fix:

1. **Put the container on the box the content must fit**, not on a convenient
   ancestor. The queries are on the shadcn table container, because that is the
   element whose width the table has to live within — not on the page root two
   levels up with a card's padding in between.
2. **Name the container** (`container: jv-users-table / inline-size`) and query
   it by name. An unnamed `@container` silently binds to the nearest container
   ancestor, which changes the moment someone adds one in between.
3. **Measure, do not estimate.** 732 and 928 above are read off the rendered
   page, and the numbers are written into the comment beside the query so the
   next person can check them instead of re-deriving them.

When the content genuinely does not fit at any supported width, dropping a
column is a design decision, not a fallback — make it deliberately, and move
the information somewhere it still shows (the Users table folds Authentication
into the identity cell rather than owning a column that could only ever have
existed in a sliver of widths). Relying on horizontal scroll is not the plan:
with overlay scrollbars, an overflowing table reads as a clipped one.

What is not allowed is a new _page_-shaped breakpoint (a pane restructuring, a
pattern moving between stacked and side-by-side across a whole screen) at a
width that is not 860 or 1100.

- `.jv-desktop-only` / `.jv-compact-only` are the sanctioned visibility helpers.
- `PageBar` renders its `leading` slot only below 1100px, so compact layouts
  always expose navigation and desktop relies on the persistent panes.
- **Top-level list mode must always expose navigation** — the Timeline's
  `PageBar` carries the menu button.
- Detail vs list is decided by **route `staticData`**, never by parsing the
  pathname. A new detail route only needs `staticData: detailPane`.
- Every pane has exactly **one scroll owner**. `PageBar` is a flex sibling above
  it, never a sticky overlay, so content cannot scroll through the actions.
- Touch _targets_ ≥ 44px — the hit area, which is routinely larger than the
  visual box (§7). Text inputs ≥ 16px on touch, or iOS zooms the viewport.
- Safe-area insets are applied to the drawer and to the bottom padding of every
  scrolling pane.

### Adaptive overlays

**The semantic interaction chooses the primitive family. The viewport chooses
its presentation.**

| Interaction                     | ≤ 860px             | > 860px        |
| ------------------------------- | ------------------- | -------------- |
| Form / substantial modal        | Drawer              | Dialog         |
| Simple confirmation             | Drawer              | AlertDialog    |
| Overflow / context command menu | Drawer action sheet | DropdownMenu   |
| Popover                         | Popover             | Popover        |
| Routed application surface      | route-specific      | route-specific |

Three components own this:
[`AppAdaptiveDialog`](src/components/journiv/AppAdaptiveDialog.tsx),
[`AppConfirmDialog`](src/components/journiv/AppConfirmDialog.tsx),
[`AppAdaptiveMenu`](src/components/journiv/AppAdaptiveMenu.tsx). Feature code
never learns which branch it got.

- **860px is the only overlay boundary.** 1100px is a layout breakpoint and
  selects no primitive: a 1024px window gets the anchored menu and the centred
  dialog, exactly like 1440px. Never use Tailwind's `sm`/`md`/`lg` as overlay
  architecture, and never detect a device, a touch capability or an orientation.
- **One tree at a time.** The chosen branch mounts; the other does not exist.
  Never render both and hide one — that duplicates every control, accessible
  name and `useId()` in the overlay.
- **State survives the swap by living above it.** Crossing 860px remounts the
  primitive. Form values, drafts and mutations belong in the caller, above the
  adaptive component. `JournalFormDialog` is the reference: it owns the state
  and passes fields down as children.
- **The body is the only scroll owner** (`.jv-overlay`, `.jv-overlay__body` in
  `journiv.css`), so a title and its actions can never scroll out of reach. A
  compact sheet pads its actions with `env(safe-area-inset-bottom)`.
- **Every substantial form is an adaptive overlay. There is no "it is only a
  small dialog" exemption.** The six Library forms were plain centred `Dialog`s
  for exactly that reason, and the longest of them — Add goal, ten fields plus
  two swatch grids — laid out about 1300px tall inside a 390×844 phone. It had
  no scroll owner, so its submit button was simply off the bottom of the screen
  and the form could not be completed at all. The rule is not "long forms
  scroll"; it is that a modal that is not an adaptive overlay has no header,
  body or footer contract, and nothing catches this.
  [`long-form-overlay.spec.ts`](e2e/overlays/long-form-overlay.spec.ts) holds
  the line at 390×844 and 1024×768.
- **Actions live in `footer`, and the form keeps its own `id`.** The footer is
  a sibling of the scrolling body, so a submit button in it reaches the form
  through `form={formId}` rather than by being inside it. Cancel calls the
  caller's `onClose`; `DialogClose` does not exist in the sheet branch.
- **Do not `autoFocus` the first field.** Use
  [`useOverlayAutoFocus()`](src/components/journiv/AppAdaptiveDialog.tsx), which
  is `true` only in the centred presentation. A sheet opens from a tap, so
  focusing a text input happens inside the user gesture and summons the
  on-screen keyboard — roughly a third of an 844px viewport gone before the
  user has decided to type, and on a long form it pushes the surface out from
  under them. The centred dialog has no such cost and does focus.
- **`dismissible` is presentation, not policy.** `false` turns off Escape,
  outside press and swipe. It is not a Base UI prop — none of the three roots
  has one — but implemented in
  [`overlayDismissal.ts`](src/components/journiv/overlayDismissal.ts) by
  cancelling implicit close reasons. The caller still owns dirty state, discard
  prompts and cleanup; the generic components do not know what "dirty" means.
- **A confirmation is an `alertdialog` above 860px and a `dialog` below it.**
  Base UI's Drawer reads its role from the shared dialog store and never becomes
  an `alertdialog`; the compact branch does not claim semantics the primitive
  does not implement. What holds on both branches is the behaviour §17 asks
  for: an accessible name from the title, a description, a real focus trap
  (`modal` defaults to `true`), an inert background, and focus returned to the
  trigger on close.
- **A typed or multi-step destructive flow is not a confirmation.** Anything
  needing typed confirmation, an acknowledgement, an alternative action
  ("Archive instead") or a form input uses `AppAdaptiveDialog`.
  `DeleteJournalDialog` (§22) and `DeleteUserDialog` are the two.
- **Menus are declared as data.** `AppAdaptiveMenu` takes a typed
  `AppMenuAction[]` (`kind: "command" | "link"`), not children — a rendered
  `DropdownMenuItem` is meaningless inside the compact action sheet. There is
  deliberately no `render` or `children` escape hatch; add a third `kind` when
  a real menu needs one. A destructive action keeps **its own** icon: the
  destructive treatment is colour, not an icon override (§17), so Archive keeps
  `Archive` and only deletion uses `Trash2`.
- **Popovers stay popovers.** A Popover is anchored, lighter, and semantically
  distinct from both a dialog and a menu. `MomentDetailsPopover` and
  `EntryDateControl` keep the Popover at every width. There is no
  `AppAdaptivePopover` — §18's two-feature threshold is unmet, and turning a
  small picker into a sheet for consistency's sake is a regression.
- **Two exceptions, both application shell, both unchanged.** `SettingsModal`
  is a routed surface with its own 1100px boundary, history and
  unsaved-changes blocking (§23). The `AppShell` nav drawer is navigation. Each
  may reuse the underlying primitives but keeps its own product behaviour.

---

## 10. Moment rendering semantics

**A Moment is a container. An Entry is optional, and so is everything else.** The
backend treats a Moment as non-empty if it has _any_ of: entry, note, mood,
prompt, pin, media, location, weather, tags, people.

Classification lives in [`src/lib/moment.ts`](src/lib/moment.ts) and is covered by
tests. Never re-derive it inline.

| Kind               | Condition                        | Timeline row                                  | Reader                                                 |
| ------------------ | -------------------------------- | --------------------------------------------- | ------------------------------------------------------ |
| **titled entry**   | entry with a title               | time · title · excerpt · meta                 | date line, `<h1>` title, meta, prose                   |
| **untitled entry** | entry, no title                  | time, then the entry text at **body weight**  | **date becomes the `<h1>`**, then prose                |
| **note-only**      | no entry, has `note`             | time · `Note` chip · note text at body weight | date `<h1>`, note in a quote rule, invitation to write |
| **media-only**     | no entry/note, `media_count > 0` | time · `N photos` chip · thumbnail            | date `<h1>`, media, invitation to write                |
| **marker-only**    | only pin/mood/tags/location      | time · `No writing yet` chip · meta           | date `<h1>`, meta, invitation to write                 |

Rules:

- **Never render a placeholder title.** No "Untitled moment". When there is no
  title, the date is the page heading and the Moment's own content takes the
  primary slot.
- **A note is not a title.** It may be the most prominent text in a row, but it
  is styled as body text, never with `.jv-moment-title` or `.jv-entry-title`.
- Every kind must reach the editor through the same "write about this moment"
  path.

---

## 11. Metadata priority by surface

`MomentMeta` takes a `surface` prop and enforces a budget. It is not a single
overloaded row.

| Surface   | Budget                     | Priority order                      |
| --------- | -------------------------- | ----------------------------------- |
| `row`     | 3 (2 below 860px, via CSS) | journal → location → mood → weather |
| `compact` | 2                          | as above                            |
| `reader`  | unlimited, one row         | as above                            |

Overflow in list surfaces is **dropped silently** — a "+2" badge is noise in a
row whose job is to be scannable. The reader shows everything.

People and tags are **not** metadata. They render at the foot of **both the
reader and the editor** via the shared `MomentChips` — `PersonChip`
(avatar + name) and `TagChip` (`#word`), deliberately different objects, never
the same chip. `MomentChips` renders nothing when a Moment has neither, so it is
dropped in unconditionally.

Before adding a field here, confirm the API actually returns it in that response.
`location_json` keys are documented on the backend Moment model as
`{name, street, locality, admin_area, country, latitude, longitude, timezone}`;
`locationLabel()` reads `name → locality → admin_area → country` and nothing else.

**Editing** all of it — mood, location, weather, people, tags — lives in the
editor's Details popover (§14), never in the reader. The reader only shows.
Reader and editor render the same values the same way: `EntryHeader` +
`MomentMeta` for mood/location/weather, `MomentChips` at the foot for
people/tags. Restyle one and you restyle both.

---

## 12. Time and grouping

- Every Moment date is rendered **in the timezone the Moment happened in**, not
  the viewer's. Helpers live in [`src/lib/datetime.ts`](src/lib/datetime.ts).
- The Timeline groups by `logged_date_tz`, the Moment's own local calendar day. A
  trip across timezones must not re-shuffle history.
- "Today" / "Yesterday" are used **only** when `logged_timezone` matches the
  viewer's timezone. Across timezones those words are ambiguous, so the explicit
  date is shown. This is deliberate and covered by a test.
- Times use tabular numerals.

### List pane modes

The middle pane (`Workspace`) has three ways to see the same moments — the
chronological Timeline, a month Calendar, and a Media grid — chosen by the
`view` search param (`undefined` | `"calendar"` | `"media"`, validated by the
router's shared `timelineSearch` schema). All three are moments seen
differently; the detail pane beside them is untouched by a mode change — a
moment open in the reader stays open while the left pane changes, exactly like
Day One. Every list-header carries a `ListViewSwitch`: three router `<Link>`s in a stock
`ButtonGroup`, changing only the `view` param and staying on whatever route is
current. Selection is the neutral `--muted` fill **plus** `aria-current="page"`
(§6).

It is deliberately **not** a `ToggleGroup`. Slotting the links into toggle
items asked one element to be a pressed button and a link at the same time,
and the rendered anchors showed it: `aria-pressed`, which ARIA does not allow
on `role="link"`; a stray `type="button"`; and the group's roving `tabindex`
taking two of the three links out of the tab order in exchange for arrow keys
that drove nothing. Nothing here is _pressed_ — one of three destinations is
_current_. When a registry control's semantics and the interaction disagree,
change the control, not the ARIA. The sidebar's "Views" group (Timeline /
Calendar / Media) links to the same three modes from the nav.

- **Timeline** (`view` unset) — the default, specified fully in §15.
- **Calendar** (`CalendarPane`, `?view=calendar&month=YYYY-MM&date=YYYY-MM-DD`)
  navigates with a month `<select>` + a year `<select>` (`NativeSelect`,
  1970 → next year, ascending — the same range as `EntryDateControl`'s
  caption) flanked by prev/next-month arrows and "Today". The selected month
  lives in the URL; a `role="status"` sr-only line still announces it. Grid
  maths is pure and UTC-noon based in
  [`calendarGrid.ts`](src/features/calendar/calendarGrid.ts). Clicking a day
  sets `date` in the URL and shows that day's moments below the grid, without
  leaving the calendar.
- **Media** (`MediaPane`, `?view=media`) — a grid of every Moment with
  `media_count > 0`, grouped by month, an infinite query over
  `GET /media/library`, journal-scoped when the route names a journal. Each
  tile is a square `object-fit: cover` thumbnail — a navigational affordance
  to the Moment, not the content itself, so §13's no-crop rule does not apply
  here (see the reader-media layout note). A signed thumbnail that expires
  between response and render gets the same first-failure-refetch,
  second-failure-broken handling as `useMomentMedia`. Loading is a
  shape-matched skeleton grid; empty and error are `StatusView`.

> **Open hypothesis:** day headers are currently `position: sticky`. Sticky
> headers inside a nested scroll container behave differently on iOS Safari.
> Verify on a real phone; if it misbehaves, make them static rather than
> reaching for JavaScript.

---

## 13. Reader specification

Reference: `docs/design/reference/02-reader-rich-*`, `03-reader-plain-*`,
`04-reader-note-only-*`.

- `PageBar`: compact-only Back, journal badge, and Edit (or a primary **Write**
  when the Moment has no entry).
- One scroll owner: `.jv-reader__scroll`. The bar is above it.
- Column: `max-width: 47rem`, centred, `--reader-gutter` sides. The column owns
  the measure, so `.jv-prose { max-width: none }` inside it.
- `EntryHeader` (shared with the editor) renders: date line (`Monday, 17 August
2026 · 7:04 AM`), title, then `MomentMeta` at `reader` budget. The date line is
  **display-only here** — the editable `EntryDateControl` is passed only by the
  editor (§14 "Entry date & time").
- Body: `.jv-prose` via `QuillReader`. Never `dangerouslySetInnerHTML`.
- Foot: people, then tags, above a `--border` rule.
- Malformed stored content falls back to `content_plain_text` inside a bordered
  notice; it must never crash or render raw HTML.

### Delete entry

The reader `PageBar` shows one ghost trash `IconButton` immediately before Edit
when the Moment has an Entry. It is the same direct action at every width; there
is no compact overflow menu, Timeline-row action or swipe gesture. Confirmation
is `AppConfirmDialog` — an `AlertDialog` above 860px, a Drawer below (§9,
"Adaptive overlays") — with a danger final action, a disabled pending state and
an inline human error that leaves the surface open.

`DELETE /entries/{entry_id}` permanently removes the Entry's writing, **not the
Moment**. Photos, moods, tags, people, location and other Moment context remain,
so a successful delete refetches the Moment in place and the reader becomes the
corresponding quick log. The backend prunes a Moment that has no meaningful
context left; a 404 from that refetch returns to the same list mode, search and
entity scope. The mutation invalidates every Moment list, Calendar, Media
library, journal count and tag preview affected by the change.

There is no Undo: the endpoint is a hard delete and the API exposes no restore
contract. Recreating cached writing would produce a different Entry identity
and is not presented as recovery.

### Reader media

Media appears in two places, and never in both at once:

- **Inline**, inside the prose, where the writer placed it.
- **The gallery** (`EntryMedia`), between the entry header and the prose, for
  media attached to the Moment but not referenced by the text. For Moments with
  no writing, this places photos above the "write about this moment" invitation.

#### Data contract — verified against the live API, do not re-derive

- `GET /moments/{id}` returns `media[]` as **thumbnails only** —
  `{id, media_type, signed_thumbnail_url}` — plus `media_count`.
- The gallery uses a **second query**, `momentMediaQuery` →
  `GET /moments/{id}/media`, returning `signed_url`, `width`, `height`,
  `alt_text`, `duration`, `mime_type`, `upload_status`,
  `signed_url_expires_at`. It is enabled only when `media_count > 0`.
- **Inline embeds are hydrated by the backend.** The database stores
  `{ insert: { image: "<media id>" } }`, but the API returns
  `{ insert: { image: "/api/v1/media/<id>/signed?uid=..&exp=..&sig=.." } }`.
  The client renders the URL it is given and never resolves ids. A hydrated URL
  must never be written back to the server in place of the id.
- `media_count` is **denormalised on the Moment row**. When the media list
  disagrees with it, the list wins.

#### Layout — a photograph is never cropped where it _is_ the content

The rule is about role, not surface: **wherever media is the thing being
looked at, it is shown whole; wherever a thumbnail is a navigational
affordance that leads to the uncropped original one click away, a crop is
fine.** There is no full-image viewer yet, so a cropped preview with no way to
inspect the original would hide part of a memory. The reader gallery is
content, so:

- One column, one item per row, at the item's own aspect ratio from
  `width`/`height` (3:2 when dimensions are missing).
- `object-fit: contain`, and `max-height: 78svh` so a tall portrait cannot take
  over the page — it letterboxes rather than cuts.
- The frame reserves its ratio before the image decodes, so prose never jumps.

The Timeline's 68px row thumbnail and the Media grid's square tile (§15, and
the list-pane Media mode above) are navigational, not content — both are links
to the Moment or its uncropped original, so `object-fit: cover` there is
correct today, lightbox or no lightbox.

A compact cropped **gallery** grid — replacing the reader's one-column list
above — becomes acceptable **once a full-image viewer exists**, and not
before: cropping the one place media _is_ the content, with no way to see the
uncropped version, is what this rule forbids. Until then, a Moment with
several photos pushes the prose a long way down; that is the accepted trade.

#### States

- **`alt_text` is alt text.** It goes in the `alt` attribute. Journiv has no
  caption field, and nothing is rendered under an image. A test asserts the alt
  string never appears as visible text.
- `upload_status` `pending`/`processing` renders a "Processing" frame; `failed`
  renders "<Photo|Media> unavailable". `processing_error` is never displayed.
- **A failed media request is never silent.** Known user content must not
  disappear without a word, so the gallery shows a quiet inline
  "Media couldn't be loaded · Retry" notice. It is deliberately _not_ a
  pane-filling `StatusView`: the writing must keep reading.
- **An empty list with a non-zero `media_count`** renders nothing and shows no
  error. The request succeeded; the count is the stale value, and there is
  nothing for the reader to retry.
- One item failing never removes the others.

#### Signed-URL expiry

Signatures expire, and recovery is explicit — it never relies on the query's
`staleTime`:

- **Proactively**, `useMomentMedia` compares `signed_url_expires_at` against the
  clock and calls `refetch()` once per data snapshot to re-sign.
- **Reactively**, the first image load failure per item forces a refetch; a
  second is treated as genuinely broken. Never a retry loop, never a broken
  image left on screen.
- **Inline** sources live inside the document, so re-signing them means
  refetching the _entry_, not the media. `QuillReader` listens for image errors
  in the capture phase and asks the reader to refetch the entry once.

#### Inline rendering rules

- Reader guard is `isReaderDocumentDelta` — Gate-1 text plus `image`, `video`
  and `audio` embeds. The editor shares it via the `isEditableDocumentDelta`
  alias, so both surfaces accept exactly the same documents.
- **Only same-origin relative URLs are rendered.** Fetching a third-party URL
  found in stored content would tell that host the entry had been opened.
- `formula`, `divider`, an embed carrying real attributes, or an unsafe source
  sends the whole document to the plain-text fallback. Falling back visibly
  always beats dropping content silently.
- Video and audio use Journiv blots in
  [`mediaBlots.ts`](src/features/editor/mediaBlots.ts). Quill's built-in `video`
  format renders an `<iframe>` (for YouTube); Journiv needs a real `<video>`.
  The blots keep the **standard Delta keys**, so the wire format stays
  byte-compatible with `flutter_quill`. Never autoplay.
- The gallery excludes inline media by **URL path** — the signature differs
  between the copy hydrated into the document and the copy from the media
  endpoint, while `/api/v1/media/<id>/signed` is stable.

#### Not yet built

A full-size viewer / lightbox (§21).

## 14. Editor specification

Reference: `docs/design/reference/05-editor-*`, `06-editor-new-*`.

The contract is **reading and writing must look the same**. The editor uses the
same `EntryHeader` and the same `.jv-prose`. If you restyle prose for one, you
have restyled it for both — that is the point.

- `PageBar`: journal selector (when a choice is required), save status, Cancel
  (ghost), Done (primary). **One Cancel control at every width** — two controls
  sharing an accessible name is a trap even when one is `display: none`.
- Title is a `<textarea>` that grows with its content. An `<input>` cannot wrap
  and clipped long titles on mobile.
- New entries show the date they will be logged at, from the browser's timezone.
  The date/time line is **editable in the editor** — see "Entry date & time"
  below. The reader's copy of it is display-only.
- Placeholder is an invitation (`Give this a title (optional)`), never a fake
  title.
- Toolbar: 30px visual buttons, 44px hit areas, active state is `--accent` +
  `--accent-foreground` (not an inverted black block).
- `onPointerDown → preventDefault` on every toolbar button is **load-bearing**:
  it preserves the editor selection. Do not remove it.
- Toolbar positioning is `position: sticky` inside the existing single scroll
  owner. **Keyboard-relative docking is explicitly not a requirement.** Do not
  reach for `visualViewport` until a reproduced real-device failure demands it.

### Entry date & time

Reference: `journiv-frontend` (Flutter) `entry_form_screen._showDateTimePicker`.

The `EntryHeader` date line ("Monday, 17 August 2026 · 7:04 AM") is an
`EntryDateControl` in the editor — a button that opens a popover with a shadcn
`Calendar` and a native time field. The reader passes nothing to
`EntryHeader.dateControl` and keeps a plain `<p>`; restyling one does not touch
the other.

- **Caption.** The `Calendar` runs `captionLayout="dropdown"` — month and year
  are native `<select>`s (rdp's own, styled by `calendar.tsx`), not just
  prev/next chevrons, so backdating a decades-old entry is one click, not forty.
  The range is fixed by `startMonth`/`endMonth` (Jan 1970 → December of next
  year) rather than rdp's default 100-years-ago-to-this-December, which would
  bar scheduling into next year.

- **Timezone.** A new entry defaults to the browser's IANA zone
  (`browserTimeZone()` in [`src/lib/datetime.ts`](src/lib/datetime.ts)); the
  picked wall-clock is converted to UTC in that zone and both `logged_at_utc`
  and `logged_timezone` are sent. Editing an **existing** Moment **preserves its
  own `logged_timezone`** and reinterprets the newly picked wall-clock in it —
  an old Warsaw entry is never silently re-read in today's zone. The effective
  zone is shown in the popover (`8:00 PM · Europe/Warsaw`) only when it differs
  from the browser's. There is no arbitrary timezone selector yet (§21).
- **Conversion.** `zonedWallTimeToUtcIso` / `wallTimePartsInZone` wrap
  `date-fns-tz`; DST is covered by tests. `react-day-picker`'s `Date` is used
  for its y/m/d only — its own `toISOString()` is browser-local midnight and is
  never persisted.
- **Persistence.** For an existing Moment the change is an immediate
  `PUT /moments/{id}` that re-sorts the Timeline and, like every other metadata
  write on an existing Moment (§14 "Dirty tracking"), does **not** mark the form
  dirty. For a new entry it seeds the draft `logged_at_utc` and the eventual
  `MomentCreate`; once a draft Moment exists (media / details) that Moment is
  updated in place too. The picker has **no primary action** — the surface's
  primary is Done — and commits on discrete actions (a day click, a committed
  time change), never per keystroke.
- **Local drafts** carry `loggedAtUtc` / `loggedTimezone` so a reload before the
  server Moment exists does not reset a backdated new entry to "now".

### Media attachment

Reference: `docs/design/reference/08-editor-*`.

**Server identity first.** Media upload needs a `moment_id`, and
`EntryDraftCreate` needs one too, so a new Entry has none until we make one.
[`useEntryDraft`](src/features/editor/useEntryDraft.ts) creates Moment + a
`is_draft` Entry **on first media attach** — not on form open, so an accidental
"New entry" leaves no row. Draft Moments are hidden from the Timeline by
`_apply_draft_filter`. Done finalises with `is_draft: false` in the same call.

**The pipeline:**

```
capture caret → ensureDraft() → placeholder → upload → durable reference → save
```

- The caret is captured **before** the picker opens; it does not survive the
  picker backgrounding the page on mobile. A drop supplies its own index.
- The placeholder ([`uploadPlaceholder.ts`](src/features/editor/uploadPlaceholder.ts))
  carries **only an upload id**. Object URL, filename and status live in a side
  registry, so a `blob:` URL has no path into a document.
- On success the swap is one `updateContents(retain/delete/insert)`, so undo
  treats it as a single step.
- **The race:** a completing upload looks for its placeholder in the _live_
  document. If it is gone — removed, or undone mid-flight — the media is
  **deleted**, never reinserted.
- Object URLs are released when the surface unmounts, not when a placeholder
  disappears: Quill re-creates the blot from its Delta value on undo.
- `getContents()` strips placeholders before validating, so a document that is
  mid-upload still yields a valid saveable Delta.
- Only the **upload** phase blocks Done. Server-side processing does not — the
  reference is already durable and the reader renders a processing state.

**Uploads** use [`mediaUpload.ts`](src/features/editor/mediaUpload.ts): an
isolated `XMLHttpRequest`, because `fetch` cannot report upload progress. The
generated Fetch client is untouched and there is no Axios. Concurrency is capped
at 2. Progress shows a percentage **only** when `lengthComputable`; never invent
one. User abort is a distinct state, not an error.

**The picker filter comes from `GET /media/formats`**, never a hardcoded list, so
the frontend cannot accept what the server rejects. Wildcards are the fallback
while it loads.

**Drop and paste** feed the same `attach(files, index)` entry point. Two
non-obvious safeguards:

- **Quill's `uploader` module is disabled.** It intercepts dropped and pasted
  image files and inlines them as base64 data URLs — bypassing the media
  pipeline and persisting a payload no backup could map to a file.
- **A clipboard matcher strips foreign images.** With `image` in the format
  allowlist, pasting HTML could otherwise embed
  `{image: "https://tracker.example.com/x.png"}`. Only same-origin
  `/api/v1/media/` images survive, normalised to a relative path.

**Removal.** A contextual control appears in the Insert group when the cursor is
on media, labelled for what it removes — "Remove photo" / "Remove video" /
"Remove audio", never a bare "Delete".

- Removing media makes the document dirty. The **backend** deletes media a save
  dropped from the Delta (`delete_orphaned_media_for_delta`), so remove-from-prose
  and delete-the-file are the same action once saved. Before Done it is undoable.
- **`clearHistory()` runs after a successful save** — otherwise undo could
  restore a reference to a file the backend has already deleted.
- Quill is configured `history: { userOnly: true }`. By default it records
  `silent` and `api` changes, which let Ctrl+Z revert the initial load and leave
  the entry empty.

**Cancel.** Uploads in flight are aborted. A draft this session created is
discarded, but **media the user attached is kept** — the Moment survives as a
media-only Moment rather than deleting photographs someone just took. The
confirm says so. Media that existed before this edit is never touched.

**Attaching from Immich.** When the instance provides an Immich server
(`GET /instance/config` → `immich_base_url`), the "Add photo, video or audio"
button opens an `AppAdaptiveDialog` source chooser — a bottom sheet at ≤ 860px,
a centred dialog above it —
([`ImmichPickerDialog`](src/features/editor/immich/ImmichPickerDialog.tsx)) with
a `This device` / `Immich` switch. Its selection state lives above the adaptive
primitive, so crossing the boundary does not lose chosen assets; with no Immich
server it goes straight to the native file input as before. The Immich tab is a
virtualized, infinite-scroll
multi-select grid ([`AssetGridPicker`](src/features/media/AssetGridPicker.tsx),
`@tanstack/react-virtual`) over `GET /integrations/immich/assets` — images and
videos only, newest first, `page`/`limit` paging (the backend exposes no search
or filter yet — §21). Confirming hands the chosen assets to
[`useImmichAttachments`](src/features/editor/immich/useImmichAttachments.ts),
which runs the **same pipeline** as an upload: caret capture → `ensureDraft()` →
placeholders → **one** `POST /media/import-from-immich-async` for the whole
selection → each returned media row matched to its placeholder by
`origin.external_id` → `replacePlaceholder` with the row's `signed_url` → the
shared processing poll
([`mediaProcessingPoll.ts`](src/features/editor/mediaProcessingPoll.ts), also
used by the device path). The race check, the "only the import call blocks
Done" rule, and Cancel keeping attached media are identical. Link-only vs copy
is the integration's setting, applied server-side; the dialog only says which is
in effect.

### Local drafts, and how they meet the server draft

Two different mechanisms, doing two different jobs. Keep them straight.

|                       | Server draft (`is_draft`)                               | Local draft (IndexedDB)                                 |
| --------------------- | ------------------------------------------------------- | ------------------------------------------------------- |
| Made by               | [`useEntryDraft`](src/features/editor/useEntryDraft.ts) | [`useLocalDraft`](src/features/editor/useLocalDraft.ts) |
| Made when             | first media attach or first metadata write              | 500ms after anything worth keeping changes              |
| Holds                 | a Moment id that can own media, and an empty Entry row  | the writing itself, as a durable Delta                  |
| Reaches other devices | yes                                                     | no                                                      |
| Retired by            | Done (`is_draft: false`) or Cancel                      | a confirmed save, or an explicit discard                |

The server draft is **not** cross-device autosave: its Entry is created with
`content_delta: null` and is not written again until Done. Nothing but the local
draft holds unsaved writing, and it is device-local.

**The ownership rule.** `useEntryDraft` cleans up on Cancel, so what it believes
it owns is load-bearing. A local draft records the Moment it belongs to, and for
an entry that is already saved that is the reader's _own_ Moment — so
`initialIdentity` is **refused outright whenever `moment` is set**, and `discard`
returns early on the same condition. Without that guard, recovering a draft on an
existing entry and then cancelling deleted a real journal entry.

**Recovery is a continuation, not a fresh session.** A recovered draft's Moment
is finalised rather than duplicated, and its resolved media ids seed
`sessionMediaRef` — so Cancel keeps the photographs, exactly as it would have if
the tab had never reloaded. A reload must not change what Cancel does.

**Verified, not remembered.** `useDraftRecovery` fetches the Moment a draft
records and hands back `verifiedIdentity`: null when that Moment is definitely
gone (Done then makes a fresh one instead of failing forever), and carrying the
Moment's _own_ `entry` id, so a draft Entry deleted underneath the record stops
being addressed by an update that could only 404. Only a definite 404 clears
it — see "Errors carry their status".

**A retired record stays retired.** `remove()` latches, because both things that
call it (a confirmed save, an explicit discard) then leave the editor — and
leaving is a flush point. A draft that came back from the dead would be offered
again on the next visit.

### Concurrent edits

Journiv has no autosave: the editor holds a whole entry in memory and writes it
back on Done. Two devices open on the same entry therefore used to mean the
second Done replaced everything the first wrote, with nothing on screen to say
it had happened.

`EntryUpdate.expected_updated_at` (optional) closes that. The editor sends the
`updated_at` it opened on; the backend refuses with **409** if the entry has
moved since. Omitting the field keeps last-write-wins, so existing clients —
the Flutter app among them — are unaffected. It is compared as an instant, not
a string: a naive column and an offset-bearing payload are the same moment.

Sent only for an entry that already exists. A draft Entry is invisible to every
other device, so it has no version worth defending, and a spurious refusal there
would block the first real save.

On 409 the editor shows `SaveConflict` — the writing untouched, one action
("Save anyway", which resends without the version). No merge, and no diff:
there is no server-side history to compare against, and inventing one would be
worse than saying plainly that the two versions cannot be combined. Leaving
instead is safe: the local copy stays, and the recovery prompt says the entry
changed elsewhere the next time it opens.

> **Cancel is a discard; navigating away is not.** They must not share a
> sentence. Leaving keeps the local copy; Cancel removes it _and_ cleans up the
> draft this session created. "Your writing is kept on this device" on the
> second one would be a lie told at the moment it matters.

### Errors carry their status

[`ApiError`](src/api/client/errors.ts) wraps every failed request with its HTTP
status; `configureApiClient` installs the interceptor, which is the last place
that still holds the `Response`. The generated client throws the parsed body
alone, and without the status "the Moment is gone" and "the network is gone"
are the same value.

`isNotFound` is deliberately narrow — a thrown value with **no** status is not
a 404. Every caller is about to act on the absence of something, and "I could
not ask" must never be read as "I asked, and it is gone": dropping a draft's
Moment id offline would orphan a Moment nobody would ever finalise.

> Drafts persist **durable media ids only** — never signed URLs, object URLs, or
> base64. [`draftCanonical.ts`](src/features/editor/draftCanonical.ts) owns that
> translation in both directions and is the only file that knows media signing
> exists. A document holding durable content a draft cannot represent produces
> **no record at all** rather than a lossy one.

> **Never call `crypto.randomUUID` directly.** It is undefined outside a secure
> context, and a self-hosted Journiv reached over plain HTTP on a LAN is not one.
> Attaching a photo threw there and did nothing at all. Use
> [`uuid()`](src/lib/uuid.ts). The same caution applies to any other
> secure-context-gated API.

**Toolbar growth.** Insert actions live in a `role="group"` inside
`role="toolbar"`. Metadata editing joins _that_ group, never the formatting
controls — but five separate buttons (mood, location, weather, people, tags)
would crowd the bar, so they collapse into **one "Moment details" control**
(`MomentDetailsPopover`, a `SlidersHorizontal` `IconButton`) that opens a
popover. The popover is a base-ui `Popover`, an overlay with its own scroll
container, so the "one scroll owner per pane" rule does not apply to it.

### Metadata editing

Reference: the reader specification (§11, §13) — the popover writes what the
reader shows, and nothing else.

**Server identity first, exactly like media.** Every write needs a `moment_id`.
A new entry has none until real intent, so `ensureMomentId` runs the same
lazy-draft path as the first media attach (`useEntryDraft.ensure`): the draft
Moment is created on the first metadata write, not on popover open. A brand-new
entry the user only _looked_ at leaves no row. `onSaved(id)` refreshes the
editor's live Moment (a query on the draft id; an existing Moment is already
refetched by the parent), so the header `MomentMeta` and foot `MomentChips`
update the instant a write lands.

**Mood.** `MoodResponse.icon` is a Material Symbols name and is **not** Lucide
(§7). Mood is rendered as its colour dot (`moodColor(color_value)`, a Flutter
ARGB int) plus its name, in the popover and in `MomentMeta`. `primary_mood_id`
is set with `PUT /moments/{id}` — accepted on update even when the mood is not
yet in the Moment's mood set (it is **rejected** on create; see
`scripts/seed_dev_data.py`). Because the popover always goes through the draft
or existing Moment, it always takes the update path. "None" clears it.

**Location** geocodes free text via `POST /location/search` and stores the
chosen result's `location_json` (the documented keys only) plus `latitude` /
`longitude`. **"Use current location"** ([`geolocation.ts`](src/lib/geolocation.ts))
reads the device position, reverse-geocodes it (`POST /location/reverse`, falling
back to a `"lat, lon"` label), saves the place, and then fills weather for it in
the same action — the user can still override any of it with the manual
controls. The browser Geolocation API is secure-context-only, so on a plain-HTTP
LAN it fails rather than prompting; that is tolerated **only** because the
failure is always shown (`geolocationErrorMessage`, never a raw error) and the
manual search is always present — the same "no silent failure" bar as the rest
of §14. **Weather** needs coordinates: `POST /weather/fetch` with the entry's
own timestamp and timezone, then a free-text `weather_summary` in the seed-data
shape (`formatWeatherSummary` → `"Clear 14°C"`), with `weather_json` kept
alongside. The service can be off — `WeatherServiceDisabledResponse` is shown as
a plain notice, nothing is saved. A manual summary field is always available.

**People** is `PUT /moments/{id}/people` with the full `person_ids` set every
time (not a delta). **Tags** are `POST /moments/{id}/tags` by name (comma or
Enter commits) and `DELETE /moments/{id}/tags/{tag_id}` to remove; `GET
/tags/search` feeds inline suggestions. Both pickers filter client-side.

**Suggested from Immich.** When the moment holds Immich-origin media
(`hasImmichMedia`, threaded from the editor — a non-Immich entry makes no
call), a quiet strip above the people list
([`ImmichSuggestedPeople`](src/features/editor/immich/ImmichSuggestedPeople.tsx))
asks `POST /moments/{id}/people/suggestions/immich` which linked, sync-enabled
people Immich's face index matches — add-chips only. Tapping one runs the same
`PUT /moments/{id}/people`; nothing is written without the tap (§2.6). It never
auto-adds. A **fetch failure is not a failed user action**, so it shows a
`jv-caption` + Retry with `role="status"` — never a `role="alert"` or a
pane-filling `StatusView` (the reader-media precedent, §13); the people list and
its own save errors are untouched. Empty and still-loading render nothing.

**Every failure reaches the screen.** Each section owns a `role="alert"` with a
human message; searches show their own inline error and empty states; mood and
people show `Skeleton` while loading and a `StatusView` on error or when the
account has none. The popover has **no primary action** — the surface's one
primary is the editor's Done.

**Dirty tracking.** A metadata write on an _existing_ Moment is persisted
immediately and does not mark the form dirty. A write on a _new_ entry marks it
dirty so the unsaved-changes guard protects the freshly created draft; Cancel
then discards that draft the same way it always has.

### Editor independence

`.jv-prose` styles **semantic elements only** and never mentions Quill.
[`quill-adapter.css`](src/features/editor/quill-adapter.css) and
[`mediaBlots.ts`](src/features/editor/mediaBlots.ts) are the only files that may
reference Quill. If Journiv replaces its editor, those are what get rewritten.

> **`EDITOR_FORMATS` must admit every kind the guard admits.** They are two
> separate lists; when they disagreed, opening a real entry threw
> `[Parchment] Unable to create video blot` and killed the route. It now derives
> from `INLINE_MEDIA_KINDS`, and a test mounts a document of each kind.

---

## 15. Timeline specification

Reference: `docs/design/reference/01-timeline-*`, `07-empty-search-*`.

- Header names the real scope — the journal's title with its colour dot, or
  "All journals" — never a generic "Timeline". Below 1100px the `PageBar` carries
  the scope and the large heading is hidden to avoid repeating it.
- Sticky day headers group the list (see the hypothesis in §12).
- Row: time · optional kind chip · optional pin, then title (or the Moment's own
  text at body weight), a **two-line** excerpt, then `MomentMeta`.
- Excerpts are `.jv-clamp-2`. Never `white-space: nowrap` — a three-line-tall row
  showing one clipped line is wasted space.
- Media: a 68px (80px on mobile) rounded thumbnail with a `+N` badge.
- No dividers and no panel around the list. Selection is `--accent` plus the
  `--brand` rail. **This is a content-side decision** (§5): the Timeline is the
  list of things to read, so its rows keep their own radius and let rhythm and
  the hover target separate them. Do not cite this bullet when composing a
  chrome list — Settings, Journals and the Library are on the other side of the
  line and get a panel.

---

## 16. Empty, loading and error states

One component: `StatusView` (icon, title, optional description, optional action).

- Empty and error states get an action wherever one exists ("Clear search",
  "Write your first entry", "Try again").
- Loading uses either a `StatusView` with a spinner (whole pane) or a `Skeleton`
  that **mirrors the final layout** (list rows, reader header + body).
- A bare sentence floating in a pane is not an acceptable state.
- Never show a raw server message or stack text. Preserve request IDs where the
  API provides them.

---

## 17. Accessibility contract

- Touch _targets_ ≥ 44px — the hit area, not the visual box (§7). `IconButton`
  gives every icon-only control one; small marks get a transparent target box;
  flush-packed segments grow instead, on coarse pointers only.
- A visible focus treatment on every control (two sanctioned variants — §6);
  never remove an outline or ring without replacing it.
- Body text meets AA comfortably in both themes; check any new pair.
- Selection is never colour-only.
- One `<h1>` per screen. When there is no title, the date is the `<h1>`.
- Every icon-only control has a label. Every form control has a `<label>`.
- Formatting buttons expose `aria-pressed`.
- Errors use `role="alert"`; loading regions use `role="status"`.
- Reduced motion is honoured globally.

Automated checks do not replace a keyboard pass and a VoiceOver pass.

---

## 18. Where things live

```
src/styles/tokens.css        stock base-vega tokens (:root + .dark) + Journiv's few
src/styles/index.css          imports, @custom-variant dark, @theme inline map
src/styles/base.css          reset, focus, typographic roles, visibility helpers
src/styles/prose.css         long-form typography — editor-independent
src/styles/fonts.css          --font-sans / --font-reader / --font-mono stacks
src/styles/util.css           .jv-dialog__actions, pane-status, spinner
src/components/ui/            shadcn base-vega primitives: button, input, dialog,
                              alert-dialog, drawer, popover, dropdown-menu, select,
                              combobox, calendar, tooltip, card, item, tabs,
                              toggle/toggle-group, switch, checkbox, avatar,
                              button-group, field, input-group, empty, alert …
                              + Journiv wrappers icon-button, search-input,
                              native-select
src/components/journiv/       cross-feature product patterns: PageBar, EntryHeader,
                              JournalBadge, MomentMeta, PersonChip, StatusView,
                              LibraryRow, EntityGlyph, ListViewSwitch, journiv.css,
                              the adaptive overlays (§9) AppAdaptiveDialog,
                              AppConfirmDialog, AppAdaptiveMenu + overlayDismissal
src/api/                      generated OpenAPI client (`generated/`, gitignored),
                              the hand-written wrapper (`client/`), auth session
                              storage (`auth/`), React Query keys/options (`query/`)
src/app/                      router (`app/router/`), query client, theme.ts
                              (the light/dark/system tri-state — distinct from
                              `features/theme/`, the personalization layer)
src/features/theme/           personalization: UserTheme model, applyUserTheme,
                              parseThemeCss, exportThemeCss, fonts, usePersonalization
src/features/library/         People / Tags / Moods / Activities / Goals (§24)
src/features/library/immich/  the People "Import from Immich" dialog + its pure
                              row→request mapping (§24 People)
src/features/media/           the Media grid list-pane mode; the shared
                              virtualized selection grid (`AssetGridPicker`,
                              `useVirtualGrid` — `@tanstack/react-virtual`) used
                              by the editor's Immich picker
src/features/editor/immich/   the editor's Immich source chooser + attach pipeline,
                              and the "Suggested from Immich" people strip (§14)
src/lib/                      moment semantics, datetime, journal lookup + order,
                              journal colours + icons, `utils.ts` (`cn`), `cx.ts`,
                              useCompactViewport (the one reactive breakpoint read)
src/features/<feature>/       feature UI + its own <feature>.css
src/features/editor/quill-adapter.css   the only file that knows about Quill
src/test/                     vitest setup + the width-aware matchMedia stub
                              (`viewport.ts`) — not a feature directory
```

**Placement rule:** a component goes in `components/journiv/` only when **two or
more features** use it. Otherwise it is feature-local.

**Two class-name joiners, on purpose.** `cn` (`src/lib/utils.ts`, wraps
`clsx` + `tailwind-merge`) is for `components/ui/*` — it resolves conflicting
Tailwind classes so a passed `className` can override the component's own.
`cx` (`src/lib/cx.ts`, a plain falsy-filtering join) is for everything else —
Journiv product code does not fight Tailwind class precedence, so it does not
need `tailwind-merge`'s cost. Reach for `cn` only inside `components/ui/`;
reach for `cx` everywhere in `components/journiv/` and `features/`.

**shadcn-first for generic primitives.** A generic control's markup, variants,
sizes, states and class strings come from
`https://ui.shadcn.com/r/styles/base-vega/<name>.json`, **unmodified**, into the
flat `src/components/ui/`. Its appearance comes from the tokens. **If you are
editing a Tailwind class inside `src/components/ui/`, stop — change a token
instead.** Reconcile only: `cn` from `src/lib/utils.ts`, `lucide-react` in
place of base-vega's `IconPlaceholder`, and any concrete UX fix, documented in
the file with its reason.

**A registry component may not grow a Journiv convenience API.** `Dialog` once
took an optional `title` prop and, when given one, rendered the whole centred
shell around its children so a confirmation could be a single element. It was
three lines and it cost the product six broken forms: it made the _non-adaptive_
primitive the shortest path to a modal, and every Library form took it (§9).
Keeping the registry compositional is not pedantry — the friction is what sends
the next author to `AppAdaptiveDialog`. If a shorthand is genuinely wanted,
build it in `components/journiv/` where it can be the _right_ shorthand, not in
`components/ui/` where it competes with one.

Refresh a component with `npx shadcn@latest add <name> --diff <file>` and read
the diff before overwriting. That command only works because `tsconfig.json`
carries `compilerOptions.paths` — without it the CLI cannot resolve the `@`
alias and writes to a stray `@/` directory. Do not remove it.

**shadcn-first for composition, too.** The rule above is about controls; this
one is about arrangements, and it is the one that gets skipped. Before writing
a `<div>` and a stylesheet for part of a chrome screen, check whether the
registry already names that arrangement:

| You are building                                   | Use                                                                                                                          |
| -------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| A titled group of controls                         | `Card` + `CardHeader` / `CardTitle` / `CardDescription` / `CardContent` / `CardFooter`                                       |
| A labelled control with help text or an error      | `Field` + `FieldLabel` / `FieldDescription`, `FieldGroup` for a form, `FieldSet` + `FieldLegend` for a related set           |
| A row with a mark, text and trailing actions       | `Item` + `ItemMedia` / `ItemContent` / `ItemTitle` / `ItemDescription` / `ItemActions`, grouped by `ItemGroup`               |
| An exclusive choice of 2–7 options                 | `RadioGroup` (stacked, with descriptions) or `ToggleGroup` (compact, segmented) — never a hand-styled `<input type="radio">` |
| An empty, loading-failed or nothing-selected state | `Empty` (via `StatusView`)                                                                                                   |
| Related actions that read as one control           | `ButtonGroup`                                                                                                                |
| Tabular data                                       | `Table`                                                                                                                      |
| Switching between sibling views in one surface     | `Tabs`                                                                                                                       |

A hand-rolled version of any of these is drift, exactly like a hand-rolled
button is. It does not become acceptable because the CSS uses tokens.

**The table is about these arrangements, not about page layout.** It says: when
you need a labelled field, use `Field`. It does not say a page may only contain
shapes the registry has an example of. Journiv's own layout — the three-pane
shell, the settings modal, the Library workspace and push-detail, the editor,
the adaptive overlays — is product structure, belongs in Journiv CSS, and needs
no justification beyond doing its job (§2.2). The test is whether you are
_reimplementing_ something the registry provides, not whether the registry has
ever drawn this screen.

Hand-build only Journiv **product** components (`components/journiv/`, feature
dirs) or behaviour the registry lacks — `IconButton`'s 44px hit area,
`SearchInput`, `NativeSelect`, `StatusView`, `EntryDateControl`, the adaptive
overlays. A custom generic primitive needs a one-line reason in the file.

**The Journiv wrapper test.** A wrapper around a registry component is right
when it adds real product behaviour, and wrong when it only changes how
something looks. `IconButton` (a required accessible name + a 44px hit area),
`LibraryRow` (stretched link + rest-hidden `⋯`), `AppAdaptiveMenu` (menu on
desktop, action sheet on touch), `StatusView` (one title, at most one action)
all pass. A component that exists to give a control a different radius, a
different hover colour or a different border does not — delete it and use the
registry component.

**Base UI directly** is allowed only for a product shell that no registry
component fits — today just `SettingsModal` (full-screen routed modal) and
`AppShell`'s nav drawer. Everything else composes `src/components/ui/`.

**CSS rule:** styling lives in scoped stylesheets next to the feature that owns
it, driven by tokens. Tailwind utilities are fine for one-off layout. Do not
mechanically convert working scoped CSS into utilities, and do not add a utility
that duplicates a design decision.

---

## 19. Reference screenshots

`docs/design/reference/` holds desktop (1440×900), tablet (1024×768) and mobile
(390×844) captures in light and dark for: Timeline, a rich reader, a plain
reader, a note-only reader, media-only, a media gallery, inline media, the
editor, a new entry, an empty search, Settings → Profile / Security /
Appearance, Library → People, and Journals.

The tablet viewport exists because the 861–1100px band has its own layout (nav
in a drawer, two panes) and used to be captured nowhere. Settings → Appearance
exists because it carries the densest set of stock controls in the product, so
it is the fastest read on whether controls still look like base-vega.

Regenerate them after any visual change:

```bash
JOURNIV_EMAIL=... JOURNIV_PASSWORD=... \
  node scripts/capture-design-reference.mjs --base http://127.0.0.1:5199
```

Credentials come from the environment. **Never commit an account into this repo.**

> **Migrating to Playwright.** Playwright has landed — see
> [`e2e/README.md`](e2e/README.md) — with the determinism this script lacks:
> fixture data created through the API, pinned viewports, theme and
> personalization reset, a frozen clock, and real waits instead of sleeps.
> **Visual regression itself has not landed yet:** no `toHaveScreenshot()`
> baselines are committed, so `scripts/capture-design-reference.mjs` remains
> the only screenshot tooling and the manual regenerate-and-look step above is
> still what exists. Do not invest further in the script.
>
> Delete the script, and this section's `node scripts/capture-design-reference.mjs`
> instructions with it, once committed Playwright baselines cover the scenes it
> captures.

**What stays a static check regardless of Playwright** (§ preamble, and
`scripts/check-design-system.mjs`): a _documented_ token fact — a literal
value in this file's own prose, like the radius scale — is validated by
parsing `tokens.css`, not by rendering a page. Playwright separately verifies
the _runtime_ result of those tokens — rendered contrast, computed styles,
whether a token actually reached the pixel — which a source-level parse cannot
see (a page-specific override could still make the rendered value wrong even
when the source values match). The two are complementary, not redundant: keep
both. The runtime half is
[`e2e/design/runtime.spec.ts`](e2e/design/runtime.spec.ts); keep that set small
rather than reimplementing the guard in a browser.

---

## 20. Checklist before marking any UI task done

- [ ] No raw colour, font-size, radius or spacing literal — tokens and roles only
- [ ] **No Tailwind class edited inside `src/components/ui/`** — a token was
      changed instead, or the divergence is documented in §27
- [ ] **Every interactive element is identifiable at rest** — a border, a filled
      surface or `shadow-xs`, before any hover. The one sanctioned exception is
      a _secondary_ row action revealed on hover/focus, under all of the
      conditions in §6
- [ ] **Blue appears only where §3 allows it** — count the blue things on
      screen; more than a couple, or any that is not one of the four, is a bug
- [ ] **No journal content inside a card**, no chrome inside the reading measure
- [ ] **Chrome is structured, not loose** — a group that belongs together is
      bounded (a `Card`, a panel) or otherwise clearly grouped (§5). A chrome
      screen that would render just as well as plain text with CSS disabled has
      not been composed. A card around content with nothing to distinguish it
      from is decoration; that fails this too
- [ ] **No hand-rolled generic arrangement** — check the §18 composition table
      before writing a `<div>` + stylesheet for a group, a field, a row, a
      choice, an empty state or a table. Journiv's own page layout is exempt:
      this is about reimplementing a primitive, not about matching a registry
      example
- [ ] **Section actions live in the section's `CardFooter`**, not stranded on
      the canvas below it
- [ ] **A row's hover covers the whole row**, and its shape matches its
      container — flush in a clipping panel, rounded in a gapped group (§5)
- [ ] **Buttons keep their content width.** Stretching them to fill a column
      makes secondaries read as loudly as the one primary
- [ ] Light **and** dark checked — Minimal Neutral inverts the surface order in
      dark, so a light-only review misses half the regressions
- [ ] 1440 / 1024 / 390 checked
- [ ] Loading, empty and error states exist and use `StatusView`/`Skeleton`
- [ ] Exactly one primary action on the surface
- [ ] Selection/active state uses colour **and** a rail, plus `aria-current`
- [ ] Icon-only controls have labels and 44px **hit areas** — not 44px boxes (§7)
- [ ] Keyboard reachable, focus visible
- [ ] Only data the API actually returns is displayed
- [ ] No secure-context-only API (`crypto.randomUUID`, …) — self-hosting is often
      plain HTTP over a LAN
- [ ] No user action can fail silently; every failure reaches the screen
- [ ] One scroll owner per pane; no sticky element overlapping content
- [ ] `npm run verify` passes (format, lint, design guard, types, tests, build,
      OpenAPI drift) — one command, run it before reporting anything done
- [ ] Reference screenshots regenerated if the visuals changed
- [ ] `npm run test:e2e` passes if the change touches a journey Playwright
      covers — see [`e2e/README.md`](e2e/README.md), and §21 for the tests that
      are already failing for reasons that are not yours

---

## 21. Open questions

1. **Sticky day headers** on iOS Safari (§12) — needs a real device.
2. **The reader `PageBar` title is empty** for Moments with no journal
   (note-only, media-only). Acceptable today; revisit if it looks bare.
3. **Editor toolbar overflow** still scrolls horizontally below ~700px. The
   intended fix is an overflow "More" popover, not a smaller hit area.
4. **Mood colours are not a valence scale** in the default data (Awesome is blue,
   Meh is deep orange). Use `category`/`score` for meaning; use `color_value` only
   as identity.
5. **No full-size media viewer.** Reader images are not clickable. Until one
   exists, the reader gallery never crops (§13), which makes photo-heavy
   Moments tall. A lightbox is a deliberate follow-up, not an oversight.
6. **Five Playwright tests, in three files, fail for reasons unrelated to the
   UI**, verified by running them against `bac09a18` (the commit before the
   Minimal Neutral pass) and getting identical failures:
   - `settings.spec.ts:25` "changing the display name **persists across a
     reload**" and `settings.spec.ts:49` "switching the theme to dark **applies
     it and survives a reload**" — both fail only on the post-reload assertion.
     `buildInitScript` in
     [`e2e/fixtures/determinism.ts`](e2e/fixtures/determinism.ts) re-pins
     `localStorage["journiv.theme"]` and clears personalization on _every_
     navigation, so a reload always resets what the test just changed. The
     fixture and these two specs contradict each other; the fixture is right
     and the specs need rewriting to assert persistence some other way.
   - `a11y/focus.spec.ts:4` "opening a dialog moves focus into it", and
     `media.spec.ts:27` and `media.spec.ts:75`, the two uploads.

   None of these are design-system failures. Fix the specs (or the fixture), do
   not "fix" the app to match them.

7. **RELEASE BLOCKER — inline video degrades documents in Flutter.** Verified by
   `journiv-frontend/test/unit/features/entries/journiv_delta_compatibility_test.dart`:
   `flutter_quill` treats a video embed as a block embed and emits an extra line
   terminator on every `Document.fromJson` to `toDelta()` cycle. It never
   converges — one newline, then two, then three. Image and audio embeds are
   stable and idempotent from the first pass.

   Consequence: every time a Flutter client opens and saves an entry containing
   an inline video, the document gains a blank line, permanently.

   This is a pre-existing defect — Flutter authors these embeds itself — and the
   product decision is to ship inline video from the web anyway, with a targeted
   normalisation fix in the Flutter client (collapse a video embed followed by
   two or more newlines down to one, on load) landing BEFORE the new frontend
   reaches users. Until that fix ships this is a release blocker, not a
   known-issue footnote.

   The Dart test pins the divergence with an inverted assertion, so the day
   `flutter_quill` is fixed it fails loudly and this entry can be retired.

8. **Editor media attachment has no real-device coverage.** The pipeline is
   built and unit-tested, but the picker round trip, caret survival, keyboard
   behaviour and slow-network upload have only been exercised in desktop Chrome.
   Drop-path base64 suppression in particular is browser-verified only — jsdom
   lacks `caretRangeFromPoint`, so no test covers it.
9. **Absolute media URLs in legacy content fall back to plain text.** An
   imported entry pointing at a third-party host is not fetched. If real
   imports rely on this, decide on an explicit allowlist rather than loosening
   the rule.
10. **No alt-text editing.** `alt_text` is settable only as an upload form field;
    `/media/{id}` exposes `delete` alone. Existing alt text is respected and
    rendered, but it cannot be changed after upload. Needs a small backend
    endpoint (`PATCH /media/{media_id}`) before an affordance is worth building.
11. **Conflicts are refused, never merged.** A 409 tells the writer the entry
    moved and offers to overwrite; there is no way to see what the other version
    said, or to combine them. That is a deliberate floor, not a finished
    feature — the backend keeps no history to diff against. If entry history
    ever lands, this is the first thing that should use it.
12. **The draft Moment itself has no concurrency protection.** `expected_updated_at`
    is sent only for an entry that already exists. Two tabs recovering the _same_
    local draft would still race on finalising its draft Moment; the loser now
    gets a fresh Moment rather than a dead end (§14), but the two halves of that
    writing end up in two entries. Recovering the same draft twice at once is not
    a flow the UI offers, so this is recorded rather than solved.
13. **No arbitrary timezone selector for a logged date.** `EntryDateControl`
    (§14) records a new entry in the browser's zone and keeps an existing
    Moment's own zone; it cannot record "8 PM in Tokyo" while the writer is in
    Berlin. The backend accepts any `logged_timezone`, so this is a UI
    follow-up if real travel/backfill use cases justify the extra control.
14. **Personalization is device-local.** The `UserTheme` (§25) lives in
    localStorage. A `theme` field on `GET/PUT /users/me/settings` — same JSON
    shape — would sync it across devices; the frontend needs no change for it.
15. **Accent picker sets `--primary` only.** `--primary-foreground` keeps the
    Journiv near-white, which suits saturated hues but not a pale custom accent.
    For per-mode / full control the user imports a theme. A contrast auto-pick
    is a possible refinement.
16. **Admin user pagination exposes no total or continuation token.** `GET
/admin/users` accepts `limit` / `offset` and returns a bare array. Settings →
    Users therefore walks pages until a short response and only then offers
    local search and ten-row presentation paging. A server total or cursor
    would let very large self-hosted instances render progressively.
17. **The Immich asset picker (§14) has no search, type, date or album
    filter.** `GET /integrations/immich/assets` is `page`/`limit` only, so the
    picker is infinite-scroll, newest-first. Real filtering needs the backend to
    forward `query` / `type` / `takenBefore` / `takenAfter` / `albumIds` to
    Immich's `search/metadata`. Tracked as gap G1 in `frontend-immich-v2.md` §7.
18. **Immich assets carry no duration or dimensions.** Video tiles show a play
    glyph with no time and the grid uses a fixed square aspect. `AssetGridItem`
    already has a `durationSec` slot for when the normalized asset gains one
    (G2).
19. **Immich import — resolved.** `MomentMediaResponse.origin.external_id`
    carries the Immich asset id, so `useImmichAttachments` sends one batched
    `import-from-immich-async` for the whole selection and matches each returned
    row back to its placeholder by that id (positional fallback for an older
    backend that omits it). The earlier per-asset approach raced on the SQLite
    write lock and left every asset but the first failing.
20. **No preview inside the Immich picker.** Tiles select on tap; there is no
    enlarged view or in-picker playback (consistent with #7). An Immich
    `original_url` has a 5-minute TTL, so a preview needs a re-fetch strategy —
    a follow-up alongside the lightbox (G4).
21. **G6 — Immich people `sync_enabled` is import-time only.** It is set through
    `POST /integrations/immich/people/import` and nowhere else — there is no
    `PATCH /integrations/immich/people/{id}` and `PersonUpdate` has no
    `sync_enabled`. So a person imported with the auto-suggest box unchecked (or
    one the writer later wants to stop suggesting) cannot be toggled from the
    UI. Mitigated by defaulting the box **on**; a per-person toggle is **not
    built**. Request the field on `PersonUpdate` or a dedicated PATCH.
22. **G7 — `POST /moments/{id}/people/suggestions/immich` refreshes faces
    synchronously.** The first call per asset round-trips to the Immich server
    (`_batch_concurrency = 4`); there is no async/job variant. A moment with
    many Immich photos can make the first "Moment details" open slow. Mitigated
    by `staleTime: 60_000` and the `hasImmichMedia` gate (≈ once per editing
    session).
23. **G8 — an empty suggestion strip is unexplained.** Suggestions only ever
    include people imported with `sync_enabled = true`; the response gives no
    signal distinguishing "no face matched" from "matched people who aren't
    sync-enabled", so the strip can be silently empty with nothing to say why.
24. **G9 — `ImmichPersonResponse` has no appearance count.** The import grid
    can't show "appears in N photos" to help the writer pick who's worth
    importing. Request `asset_count` on the normalized person.

---

## 22. Journal management

Reference: `docs/design/reference/11-journals-*`.

Two concerns, kept apart:

- **Browsing by journal** stays in the shell. The sidebar lists active journals
  in the canonical order — favourites sort to the top, so favouriting a journal
  re-orders the rail rather than hiding the others — each a colour dot / glyph
  plus title linking to the scoped Timeline. The list is capped (`SIDEBAR_MAX`);
  one **"All journals"** row always follows, opening the management screen. The
  rail never grows unbounded and never lists archived journals.
- **Managing journals** — create, rename, description, colour, icon, favourite,
  reorder, archive, delete — all lives on `/journals`, a list-pane route (no
  `staticData`, so it composes as a list, not a detail). It is reached from the
  sidebar and is where a future Settings → Manage section will link.

### The screen

- `PageBar` (compact only) carries the menu button and the pane name. The
  desktop heading is `.jv-display` "Journals". **One primary action: New
  journal.**
- One scroll owner (`.jv-journals__scroll`).
- The pane keeps its column's `--background` canvas and raises the list off it
  (§3, "why not `--muted` everywhere" — the New journal control sits directly on
  this canvas).
- **Active** section first: a **panel** of divided rows (§5) — journals are
  objects being managed, so the list has a real edge — roomier than a Timeline
  row. Each row is the journal's dot/glyph, title, optional
  description, and a metadata line showing `entry_count`, `total_words` and
  `last_entry_at` (see §21.2 — shown despite the known drift). Trailing: a
  favourite star, and a `⋯` menu (Rename · Edit appearance · Move up / Move
  down · Archive · Delete…). The row body links to the scoped Timeline.
- **Archived** section: a `<details>` disclosure, collapsed, labelled with its
  count. Rows there swap the star for **Unarchive** and drop the reorder items.
  This is the only route to an archived journal.
- Loading is shape-matched `Skeleton` rows; error and empty are `StatusView`
  (empty offers the same one primary, New journal).

### Ordering

`is_favorite DESC, position ASC NULLS LAST, created_at DESC` — the backend's own
order, implemented once in [`src/lib/journalOrder.ts`](src/lib/journalOrder.ts)
and shared by the sidebar, this screen and the editor's default journal.
"Move up / down" swaps a journal with its neighbour **within its own
favourite/non-favourite group** (the two the backend positions independently)
and persists the whole group via `PUT /journals/reorder`. There is no
drag-and-drop yet and no "default journal" flag: favouriting and ordering are
how the top journal — the one a new entry is filed in when the route names none
— is chosen.

### Create / edit

An [`AppAdaptiveDialog`](src/components/journiv/AppAdaptiveDialog.tsx) (§9) — a
bottom sheet at ≤ 860px, a centred `Dialog` above it. The form state lives in
`JournalFormDialog`, above the adaptive component, so crossing the boundary
mid-edit does not discard it. Title (required, validated in-form — no native
`required` bubble), description, a colour radio group of the 22 `JournalColor`
presets rendered as `JournalDot` swatches (the only sanctioned swatch — §3), and
an icon radio grid from the curated Lucide set, each option tinted with the
currently chosen colour so the result is previewed. One primary: Create / Save.
Every failure lands in a `role="alert"` with a human sentence.

### Delete

`DELETE /journals/{id}` cascade-deletes every entry's narrative in the journal
(the parent Moments survive as quick logs). The dialog states exactly that,
offers **Archive instead** first, and keeps the destructive button disabled
until the journal's title is typed back. A regression test proves the guard.
It is an `AppAdaptiveDialog`, **not** an `AppConfirmDialog`: a typed guard plus
a reversible alternative is a workflow, not a yes/no question (§9).

---

## 23. Settings

Reference: `docs/design/reference/12-settings-profile-*`,
`13-settings-security-*`.

Settings is a **secondary, contextual activity**. The user is reading or writing;
opening Settings should feel like adjusting Journiv's controls without leaving
the journal, and closing it should put them back exactly where they were. It is
never a permanent third pane.

### Routing is real; the modal is a presentation

`/settings` → `/settings/profile` · `/settings/security`. These are ordinary
routes carrying `staticData.settings`. `AppShell` reads that the same
declarative way it reads `pane: "detail"` and mounts `SettingsModal` over the
running app — the route tree is the source of truth, never component state. A
direct hit on `/settings/security` loads Journiv and opens the modal on
Security. Adding `/settings/tags` later is: register the route with
`staticData: { settings: "tags" }`, add an entry to `SETTINGS_NAV`, build the
page. Nothing about the modal, the responsive behaviour, the active state or the
close behaviour changes.

### Responsive shape — one Dialog, CSS switches the layout

| Width    | Shape                                                                                                                                                              |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| > 1100px | centred modal, `min(1050px, …)` wide, height **between** a 600px floor and a 780px cap. ~220px section nav ∥ content. Matches the persistent-pane breakpoint (§9). |
| ≤ 1100px | full-screen routed flow. `/settings` is the section list; `/settings/profile` is that page with a `‹ Settings` back control.                                       |

**The modal's height follows its content.** It was pinned at the cap, and a
short page — Providers, Appearance — then sat as one card above a tall band of
empty canvas, which reads as a broken layout rather than as breathing room. The
floor exists so the section nav always fits: every page shorter than the nav
gets the same height, so moving between sections does not resize the dialog for
the common case. Do not pin it back to a single value to stop the two long
pages from growing.

The one JS breakpoint read allowed here is a single `window.matchMedia` check
when `/settings` loads, deciding redirect-to-Profile (desktop) vs show-the-list
(compact). It is a one-shot read at navigation time, not reactive breakpoint
state. Everything else is CSS.

### Background context and closing

Opening from within the app stashes the origin href in history `state`
(`settingsFrom`). Closing — X, Escape, backdrop — navigates back to it
(`router.history.replace`), or to `/timeline` when Settings was deep-linked with
no prior in-app route. Successful saves never close Settings. Section switches
and every dismissal run through one `useBlocker` guard: if a page has unsaved
edits, a `window.confirm("Discard your unsaved changes?")` — the same prompt the
editor uses — gates the navigation. Password fields are ephemeral: never written
to any draft or storage.

### Visual treatment

The modal has dialog elevation (`shadow-lg`, `--radius-xl`) because it is a
true overlay — the same treatment upstream's `DialogContent` carries; it is
hand-built only because it is a _routed_ application shell (§18). Inside: a
quiet top bar (title + one close control), a section nav with **restrained**
group labels (sentence case, muted — real hierarchy, not a SaaS eyebrow), and a
content pane whose cards top out at one measure — 46rem — so every section is
the same width. The nav pane is `--sidebar` on the `--muted` settings canvas;
its right edge is a `--sidebar-border` hairline, not `--border`, because in dark
those two surfaces and `--border` are one value and the seam would vanish (§3). Narrow _fields_ inside a card are fine (a password input is not
more usable at 46rem, so `.jv-settings-form` caps at 24rem); a narrow _card_ is
not, because it leaves the pane looking half-empty next to every other page.

The one page that opts out is a **data table**: `.jv-settings__body--wide`
drops the cap so Users gets the whole content pane, and the table then decides
its own column budget from that width with a container query (§9). 46rem is a
_reading_ measure — it is right for a form and wrong for a grid of columns.

On phones the card tightens to `--card-spacing: var(--space-4)` below 620px:
`Card`'s own knob, not a re-skin, because at 390px the page inset and the card
padding are competing for the same width.

The content pane is the **settings canvas** (`--muted`), and every section is a
stock `Card` raised off it: `CardHeader` (title + intro), `CardContent` holding
a divided list of settings, and — when the section has actions — a `CardFooter`
with `border-t` holding them. Each setting is a stock `Item` carrying a `Field`
(label / description / control), flush inside the card and separated from its
neighbour by a hairline.

**A section's actions belong to its card, not to the canvas.** "Save changes",
"Connect", "Create export" go in that section's footer. A button stranded on
the canvas below a card reads as belonging to the page rather than to the form
it submits, and there is no `.jv-settings__actions` any more.

The rule that still holds is the narrow one: **no card around a single
setting's value.** The card is around the group. An earlier revision read the
"paper, not panel" principle as forbidding the group card too, and the result
was every settings screen rendering as unstructured text on a flat sheet — the
opposite of the Base Vega reference this product is built on.

On compact widths `/settings` is the section index, and its nav groups get the
same treatment: the group label sits on the canvas, its destinations sit in a
panel below it.

Controls are the registry's: `Checkbox`, `Switch`, `ToggleGroup`, `Select` /
`NativeSelect`, `Input`, `Textarea`, `Avatar`, `Alert` for a notice or a
success message. Selected nav item: `--accent` **plus** a `--brand` rail plus
`aria-current` (§6). No nested large modals — Profile fields and the password
form edit in place; only small confirmations (discard) may stack.

The row's stacked→two-column reflow is a **container query** at 620px on
`.jv-settings__body`, not a viewport media query: the row reflows at its own
width inside a pane whose width it does not control (§9).

### Functional now

- **Profile** — `GET/PUT /users/me` for the display name; `GET/PUT
/users/me/settings` for the timezone (a native `<select>` over
  `Intl.supportedValuesOf('timeZone')`, canonical IANA values stored). Email is
  read-only (no update path). Avatar is read-only initials/URL — there is no
  user avatar-upload endpoint. Initialises from the shared current-user /
  user-settings queries; a successful save invalidates them so the sidebar
  updates without reload.
- **Security** — capability-aware from `UserResponse.is_oidc_user` and
  `GET /instance/config`. Password accounts get a change-password form (`PUT
/users/me` with `current_password` + `new_password`; client mirrors the
  backend rule of ≥8 chars with a letter and a digit). OIDC accounts get a short
  provider notice, no form. A commented "danger zone" marks where account
  deletion will live; it is not built.
- **Appearance** — `/settings/appearance` uses `GET/PUT /users/me/settings` for
  the account theme default, time format and first day of the week. The existing
  sidebar control remains the explicit per-device override; it is not silently
  moved or replaced. The page submits the three settings together, invalidates
  `queryKeys.userSettings`, and participates in the shared discard guard.
- **Integrations** — a **catalogue → detail** drill-down, both real routes
  (§23 "routing is real"). There is no list-providers endpoint, so the set of
  providers is a frontend registry
  ([`providers.ts`](src/features/settings/integrations/providers.ts)); `immich`
  is the only real one.
  - `/settings/integrations` is the **catalogue**
    ([`IntegrationsCatalogue`](src/features/settings/integrations/IntegrationsCatalogue.tsx)):
    a `LibraryRow` list (§24), one row per provider — icon tile, name, one-line
    blurb, an `IntegrationStatusPill` (a dot **plus** a label, never colour
    alone — §6: `Connected` / `Not connected` / `Paused` / `Attention needed`
    / `Not available` / `Status unavailable`), and an info control linking the
    public setup guide in a new tab. A provider the instance has not enabled
    (`immich_base_url` absent) stays listed but **unlinked**, pill `Not
available`. A trailing muted, non-interactive row states that more
    providers are coming. Reads `GET /instance/config` and
    `GET /integrations/immich/status`; a failed status request degrades the
    pill rather than erroring the page.
  - `/settings/integrations/$provider` is the **detail** — a single-segment
    param route (not a splat), `staticData: { settings: "integrations" }` so
    the modal chrome and the lit "Providers" nav item are unchanged across the
    drill-down; only the content pane swaps, with **no transition** (§8), like
    every other section switch. An unknown or removed provider redirects to the
    catalogue in `beforeLoad` rather than 404ing. Back to the catalogue is an
    in-content `‹ Back to integrations` link on desktop and the modal top-bar
    chevron on compact (`SettingsModal` retargets it) — exactly one affordance
    per breakpoint.
  - The Immich detail
    ([`ImmichConnectForm`](src/features/settings/integrations/ImmichConnectForm.tsx))
    is unchanged: the server (read-only), connection state, and an
    **import-mode** choice — `Link originals` vs `Copy into Journiv`, a radio
    group with descriptions, chosen at connect time (`POST
/integrations/connect` with `import_mode`) and editable afterwards (`PUT
/integrations/{provider}/settings`). Connected, it also offers `Sync now`
    (`POST /integrations/{provider}/sync`) and `Disconnect` (an
    `AppConfirmDialog`: confirmation sheet at ≤ 860px, `AlertDialog` above). A
    `last_error` surfaces an alert and re-reveals the API-key field for
    reconnection; `album_error` shows under the mode control. API keys are
    ephemeral and never written to any draft; the form participates in the
    shared dirty guard; `queryKeys.integrationStatus("immich")` is invalidated
    after every successful write. The same status drives the editor's Immich
    media picker (§14).
  - Backend gaps: `is_active` (paused) is readable but not settable — there is
    no pause/resume endpoint; there is no test-connection endpoint (`connect`
    is the live test); no provider metadata or icons come from the API.
- **Data & backup** — `/settings/data/import` and `/settings/data/export` use the
  general background-job APIs. Both require an explicit start action, poll only
  while a job is pending/running, render progress and a human failure state,
  and never auto-download. Import uses the source types and ZIP contract from
  OpenAPI (Markdown is omitted because the endpoint documents it as coming
  soon); Export exposes the returned download URL only after completion.
- **Support** — `/settings/support/help` contains the project and issue links.
  `/settings/support/about` combines `GET /instance/version/info`, public
  instance config and license info, omitting unavailable optional fields.
- **Administration → Users** — `/settings/admin/users` is registered like every
  other routed Settings page, but its **navigation group is conditional on the
  shared current-user query returning `role: "admin"`**. A non-admin direct hit
  is replaced with `/settings/profile` before the admin list query mounts. The
  page walks `GET /admin/users` to completion through its offset contract (a
  fixed page ceiling guards against a broken short-page response), then searches
  and pages the complete collection locally. Edits send only changed fields, so
  an untouched value never routes through a server protection. `POST
/admin/users` creates local password accounts and applies the same password
  policy as the change-password flow (self-hosted signup intentionally permits
  any non-empty password; §26); `PATCH /admin/users/{user_id}` edits name, email,
  role and active status (plus password for local accounts); `DELETE
/admin/users/{user_id}` is protected by an exact-email confirmation that names
  the full cascade. The server refuses to delete, demote or deactivate the last
  admin who can still sign in; the row menu also **hides Deactivate and Delete
  on the signed-in admin's own row** and disables them while the account is the
  sole active admin. A refused write shows the server's own `detail` verbatim.
  Every successful write invalidates `queryKeys.adminUsers`; writes affecting the
  signed-in account also invalidate `queryKeys.me`, and self-deactivation /
  self-deletion clears the session and hard-navigates to `/login`. OIDC password
  reset is deliberately absent pending the backend contract decision in §22.
  Responsive visual references: `docs/design/reference/12-settings-users-*`.

### Deferred (do not stub pages)

Version-check administration and license registration/reset remain deferred.
Their endpoints exist, but no surface is designed. Account deletion remains
explicitly out of scope. Dead links are not rendered.

---

## 24. Library

People, Tags, Moods, Activities and Goals are journal content, not application
preferences. They live as first-class children beneath a quiet **Library**
label in the primary navigation and never mount the Settings modal. Their
existing `/settings/journaling/*` URLs remain stable for now; the route contract,
not the legacy prefix, determines the surface.

Library is a content-management workspace, not an admin panel, CRM or database
view. It spans the shell's two content columns, has one scroll owner and keeps a
readable maximum measure. At compact widths the standard `PageBar` exposes the
navigation drawer. Exactly one visually dominant action belongs to a Library
surface.

**Library is chrome, so it is composed like Settings** (§5). `.jv-library`
paints its own `--background` management canvas — scoped to itself, because it
occupies the shell's page column and the reader there stays `--card` — and
everything is raised off it in `--card`. It is `--background` rather than
`--muted` because the header actions and the search field sit directly on it
(§3). A directory's group head stays open (dot, name, hairline rule,
count) and its entries sit in a **panel** of `LibraryRow`s: never nested
tables, and never a bare grid of text on the page. A titled block on a detail
view (`Usage`, `Recent moments` on the Tag detail) is a stock `Card`, with its
header-level control — the range `<select>`, "View all" — in `CardAction`.

**List → detail is a push, not a third pane.** Opening an item swaps the
workspace for a detail _page_ on the same span-2 route area (the marketplace
pattern), with a breadcrumb bar as the title and the way back. Two shared
shells carry this: `LibraryWorkspace` (the compact `PageBar`, the header with
the one primary, the scroll owner) and `LibraryDetailView` (the breadcrumb bar

- actions, its own scroll owner). Tags is the reference implementation; People,
  Moods, Activities and Goals adopt `LibraryDetailView` as their `$id` routes
  land. Neither route carries `staticData: detailPane` — there is no side-by-side
  detail here, so the shell's `.is-detail` machinery is not involved.

**Library dialog forms are `AppAdaptiveDialog`s** (§9) — a centred dialog above
860px, a bottom sheet below — with the actions in `footer` and the form reached
by `form={formId}`. They were plain `Dialog`s until the Add goal form was
measured at ~1300px tall on a 390×844 phone with its submit button off-screen;
that is the failure the adaptive contract exists to prevent, and
[`long-form-overlay.spec.ts`](e2e/overlays/long-form-overlay.spec.ts) now keeps
it fixed.

**They use the registry's field layer.** `FieldGroup` holds the
fields, each one a `Field` + `FieldLabel` (+ `FieldDescription` / `FieldError`),
and a related set — the colour swatches, the icon grid, a checklist — is a
`FieldSet` + `FieldLegend`. Checkboxes are `Checkbox`, exclusive choices are
`RadioGroup`, except the swatch and icon pickers where the mark _is_ the value
(§27). What stays Journiv's is the layout around them: `.jv-library-form` (the
dialog's field-group / alert / action-row rhythm) and `.jv-library-form__columns`
(the Goal form's two-up pairing). That split is the §18 rule in practice — the
primitives come from the registry, the page composition is ours.

**Every Library row's ⋯ menu is an
[`AppAdaptiveMenu`](src/components/journiv/AppAdaptiveMenu.tsx)** (§9): an
anchored `DropdownMenu` above 860px, a bottom action sheet at or below it. The
actions are declared as data, and "View moments" is the shared
[`viewMomentsAction()`](src/features/library/viewMomentsAction.ts) descriptor so
every entity reaches its moments the same way. Deletions and archives are
`AppConfirmDialog`s.

**The scoped Timeline stays three-pane.** "View moments" on any Library item
opens `/timeline` filtered to that entity — the ordinary nav ∥ list ∥ reader
Timeline — so a tag's or person's moments are browsable beside the reader. That
is deliberately _not_ the `LibraryDetailView`.

### People

`/settings/journaling/people` is functional. **Add person** is the one primary
action; **Manage groups** is secondary. The header and its primary sit above the
scroll owner (as on the Journals surface), so "Add person" is always reachable.
Search is local over the complete active People response and group names. The
page combines `GET /people` (full person metadata) with `GET /people-groups`
(ordered group membership):

- A group is a **directory section**, not the absence of one: a header of
  `chevron · EntityGlyph colour dot · sentence-case name · hairline rule ·
server count · ⋯` (the same dot + rule + count device as §22), then a panel
  holding a responsive grid of people (`repeat(auto-fill, minmax(15rem, 1fr))`,
  one column below the two-pane breakpoint). The head carries the grouping; the
  panel gives the rows an edge so one is recognisable at rest (§5). Named
  groups are open by default; the chevron
  collapses a section; the count is the **server** figure (`people.length`) and
  does not change when search narrows the grid.
- Group overflow actions are Add person to group, Rename group (opens the
  groups manager on that group), Manage people and Delete group. Deleting a
  group never deletes its people.
- **Manage groups** is one `Dialog` with three in-place views — the group list
  (each row: glyph, name, count, edit, delete, plus New group), an appearance
  form (name + colour swatches from `ENTITY_COLOR_PRESETS` + icon grid from the
  curated Lucide set; writes `PersonGroupCreate/Update` including `color_value`
  via `argbFromHex` and `icon`), and a delete confirmation. Views swap, never
  stack (§22). Membership is **not** edited here.
- A person is a rich row (the shared `LibraryRow`): avatar or initials, display
  name, then `nickname · N moments` — the moment count is shown only when the
  API returns `memory_count`. One overflow menu: Edit, Manage groups, Upload /
  Remove image, Merge duplicate, Archive. Actions use only the existing edit,
  group membership, profile image, merge and archive endpoints.
- Membership is many-to-many (`PersonCreate/Update.group_ids` and the
  `person_group_link` model), so every person-facing control says **Manage
  groups**, never “Change group”. Group membership writes preserve memberships
  in other groups.
- People without membership are collected in a separate **“Without a group”**
  section — same header, muted name, no dot and no `⋯`, rendered only when
  non-empty. It is **collapsed by default when real groups exist** (so it reads
  as a fallback bucket, not the page) and **open when there are no groups** (so a
  first-time Library is not a wall of collapsed headers). A person in multiple
  groups appears under each of them — the honest cost of a flat directory over a
  tree.
- `LibraryRow` and `EntityGlyph` live in `components/journiv`; the `⋯` menu is
  the stock `DropdownMenu` primitive (`src/components/ui/dropdown-menu.tsx`).
  Activities, Goals and Moods reuse all three, plus the now-generic
  `GroupsManagerDialog` (`LibraryGroup` shape + `itemNoun` / `itemCount` props —
  People keeps the defaults). The People collection's own section rendering
  stays People-local so a future `/library/people/$personId` route can replace
  the dialogs without rewriting it.
- **Import from Immich** is a secondary header action, rendered **only** when
  `GET /instance/config` has `immich_base_url` **and**
  `GET /integrations/immich/status` is `connected` — otherwise not rendered (no
  dead control). It opens `ImmichPeopleImportDialog`
  ([`src/features/library/immich/`](src/features/library/immich/ImmichPeopleImportDialog.tsx)):
  one `AppAdaptiveDialog` — bottom sheet at ≤ 860px, centred dialog above —
  with caller-owned state and three in-place views (browse → importing →
  results, they swap, never stack). Browse is a plain infinite-scroll **list** — deliberately not
  the virtualized `AssetGridPicker`, because every row carries its own mapping
  state; `GET /integrations/immich/people` takes a real `search` term (unlike
  the asset endpoint), so a debounced server search narrows it. Each row: round
  avatar (`thumbnail_url`, initials fallback), the Immich name **or a required
  name field for an unnamed face cluster**, and a `Create new` / `Link to
existing…` / `Skip` control (`Link` reveals a person `Combobox`). A row whose
  `mapped_person` is already set shows a muted "Linked to …" badge and is
  excluded. A batch checkbox — **"Suggest these people when their photos are
  added to an entry", default checked** — sets `sync_enabled` on every item.
  One primary, `Import N people`, disabled at zero or while any pointed-at row
  is unfinished. `POST /integrations/immich/people/import` is **partial
  success**: results list ✓ created/linked and ✗ per-item errors, with a
  `Retry failed` that resubmits only the failures. Any success invalidates
  `queryKeys.people`. Turning `sync_enabled` on or off **after** import is not
  built — see §21.G6.

### Activities

`/settings/journaling/activities` is functional and follows the People directory
rather than the older card/reorder UI. **Add activity** is the one primary
action and **Manage groups** is secondary. The page walks every page of
`GET /activities` (200 at a time) and combines the complete active collection
with ordered `GET /activity-groups/` results. Search is local over activity and
group names; named groups are open by default, and active activities with no
`group_id` use the same muted, collapsed-by-default **Without a group** fallback
as People.

- Activity rows reuse `LibraryRow`, `EntityGlyph` and the shared overflow menu.
  They render only `ActivityResponse.name`, `icon` and validated `color` (a hex
  string, passed to `EntityGlyph`'s `color` prop); the list response has no
  usage count. Create/edit uses `POST /activities` and
  `PUT /activities/{activity_id}` for name, one optional group, colour and icon.
  Delete is confirmed and calls `DELETE /activities/{activity_id}`; the backend
  soft-deletes the definition, so existing moment links remain.
- Group headers and the in-place `GroupsManagerDialog` reuse the People visual
  contract. Group appearance writes `ActivityGroupCreate/Update` through
  `POST /activity-groups/` and `PUT /activity-groups/{group_id}`. Deleting via
  `DELETE /activity-groups/{group_id}` moves its activities to **Without a
  group**; it never deletes them. Activity membership is one-to-zero-or-one via
  `ActivityCreate/Update.group_id`, so moving an activity is part of Edit rather
  than a many-to-many membership dialog.
- Every successful activity or group write invalidates both `activities` and
  `activity-groups`; a failed write stays in its dialog, retains all entered
  values, and shows a human failure sentence. The generated reorder endpoints
  remain supported by the API but are not exposed by this People-style
  directory iteration.

### Goals

`/settings/journaling/goals` is functional and follows the People / Activities
directory contract. **Add goal** is the one primary action and **Manage groups**
is secondary. The page combines active `GET /goals` results with ordered
`GET /goal-categories` groups and active `GET /activities` definitions used to
name and select a goal's optional linked activity. Search is local over goal and
group names; named groups are open by default, and goals without `category_id`
use the muted, collapsed-by-default **Without a group** fallback.

- Goal rows reuse `LibraryRow`, `EntityGlyph` and the shared overflow menu. They
  show the API's cadence, direction, current-period completed / target counts,
  linked activity name when resolvable, and paused state. Create/edit uses
  `POST /goals` and `PUT /goals/{goal_id}` for every supported definition field:
  title, optional category and activity, achieve/avoid direction, daily/weekly/
  monthly cadence, integer target ≥ 1, optional reminder time, paused state,
  colour and icon. The wider goal form uses a stock `sm:max-w-2xl` on
  `DialogContent`, not a bespoke width class. Delete is explicitly permanent,
  confirmed, and calls `DELETE /goals/{goal_id}`; its copy names the loss of
  completion history.
- **History** is exposed: a goal's ⋯ menu opens `GoalHistoryDialog`, a
  read-only view of `GET /goals/{id}/logs` — one evaluated period per row,
  newest first, a status mark, the cadence-shaped period label, and the
  count / target plus whether the period was logged automatically or by hand.
  No primary action; the surface's one primary stays "Add goal" on the page
  behind it, matching the Details-popover precedent in §14.
- Goal categories use the same in-place `GroupsManagerDialog` and appearance
  form as People / Activities. Writes use `POST /goal-categories`,
  `PUT /goal-categories/{category_id}` and
  `DELETE /goal-categories/{category_id}`. Because the backend relationship is
  `ON DELETE SET NULL`, deleting a group moves its goals to **Without a group**
  and never deletes them. Counts are derived from the complete active Goals
  response because category responses do not embed members.
- Every successful goal or category write invalidates both `goals` and
  `goal-categories`; a failed write remains in its dialog, retains all entered
  values, and shows a human failure sentence. The generated archive/unarchive,
  completion-toggle and reorder endpoints remain supported by the API but are
  not exposed by this People-style definition-management iteration.

### Moods

`/settings/journaling/moods` is a first-class Library workspace backed by
`GET /moods` and `GET /moods/groups`. New accounts arrive with the
backend-seeded **Daily Moods** group and five active moods; the page renders
that server data directly and does not invent a special built-in badge because
neither mood nor group responses expose their internal `stable_key`. Mood rows
use the shared `LibraryRow` and colour-only `EntityGlyph` (the API's icon is a
Material Symbols name and is not renderable by the Lucide frontend; §7), and
show the derived category plus score out of five. Search covers mood, category
and group names; moods absent from every many-to-many group appear under
**Without a group**.

- Create/edit uses `POST /moods` and `PUT /moods/{mood_id}` for name, score
  (required integer 1–5; the backend derives positive / neutral / negative) and
  optional ARGB colour. The unsupported icon picker is deliberately absent, while
  edits preserve existing Material Symbols icon values by omitting that field.
  `DELETE /moods/{mood_id}` is a confirmed soft delete: the mood leaves active
  lists while existing moment references remain.
- Mood-group appearance CRUD reuses `GroupsManagerDialog` and calls
  `POST /moods/groups`, `PUT /moods/groups/{group_id}` and
  `DELETE /moods/groups/{group_id}`. Group deletion removes only memberships;
  moods remain in the Library. Every successful mood or group write invalidates
  both `moods` and `mood-groups`; failed saves retain entered values and show a
  human sentence. Mood/group reorder, membership assignment, statistics and
  streak endpoints remain backend-supported but are not exposed in this
  People-style definition-management iteration.

### Tags

`/library/tags` is functional. It is the reference implementation of the
Library push pattern above: `TagsPage` is a `LibraryWorkspace`, and opening a
tag pushes to `TagDetailPage` (a `LibraryDetailView`) on `/library/tags/$tagId`.
Tags have no groups, colour or icon, so the mark is a plain `#` and the
People/Moods section machinery does not apply. The legacy
`/settings/journaling/tags` URL redirects here.

- **Workspace.** One primary: **New tag**; a secondary **Clean up N unused**
  `ghost` button appears while `usage_count === 0` tags exist
  (`DELETE /tags/unused`, confirmed). Local search over `GET /tags/`; a sort
  `<select>` (Most used — the default and the backend's own order — / A–Z /
  Recently added). A slim **insights strip** always shows four counts derived
  client-side from the tag list (total, in use, unused, avg per tag); it needs
  no licence. Then an airy `LibraryRow` grid (`.jv-lib-section__grid`, one
  column below the two-pane breakpoint) — `rowLink` makes the whole card open
  the detail; `#name`, `N moments · added …`, and a `⋯` menu (View moments →
  Timeline tag-scope · Merge into… · Delete…). Loading / empty / error via
  `Skeleton` / `StatusView`.
- **Merge** opens a `Dialog` with a filter field and a radio list of the other
  tags; the confirm sentence names the resulting tag and that the source is
  deleted. `POST /tags/{source}/merge/{target}`; a 400 (case-only collision) is
  shown as a human sentence.
- **Detail.** Breadcrumb `Tags / #name`; **Rename** (the surface's one primary)
  and the `⋯` menu sit at the bar's end. Body: the `N moments · added …` line,
  a **Usage** section, and a **Recent moments** preview (`GET /tags/{id}/moments`,
  first few, linking into the reader when the moment has an entry, else inert; a
  **View all** link always goes to the Timeline tag-scope). Merge and Delete
  both leave for `/library/tags` on success.
- **Tag analytics is Journiv Plus (Supporter tier or higher).** The gate is
  `GET /instance/config` → `plus` (`{ available, tier, upgrade_url }`), read via
  `usePlusCapability()` — never by probing the analytics endpoint and reading
  its 403/503. Three outcomes: `isSupporter` renders the analytics
  (`GET /tags/{id}/analytics?days=…` — trend chip, peak month, growth, a
  sparkline of `usage_over_time`); `available && !isSupporter` shows an upsell
  `StatusView` linking `upgrade_url`; `!available` shows a quieter "not included
  in this build" with no call to action. The analytics query still treats a
  late 403/503 defensively as the same locked state, so an expiring licence
  never reaches the screen as a raw error.
- The aggregate `GET /tags/analytics` visuals (distribution buckets +
  `usage_over_time` across all tags) render in the workspace strip for a
  Supporter licence; the four free counts stay for everyone.

Chart marks (`StatTiles`, `DistributionBars`, `Sparkline` in
[`tagCharts.tsx`](src/features/library/tagCharts.tsx)) are the first data
visualisations in the app — deliberately minimal, one series in `--chart-1`,
tracks in `--border`, every label a typographic role. Feature-local until a
second surface needs them (§18).

---

## 25. Personalization

A viewer can retint and re-font Journiv for their device. It works precisely
_because_ the app is on stock shadcn tokens — nothing is hard-coded, so a
retheme reaches every surface including the reader and editor.

### The layer

[`src/features/theme/`](src/features/theme/) owns it.

- **`UserTheme`** (`types.ts`) — `{ version, light, dark, systemFont?,
editorFont?, editorFontScale? }`. `light` / `dark` are `Partial<Record<ColorVar,
string>>`; `ColorVar` is the stock shadcn colour / shadow set —
  **font variables are deliberately not in it, and neither is `radius`.** Shape
  is not personalizable (§3); only colour, fonts and text size are. This shape
  is exactly what a
  future `PUT /users/me/settings { theme }` will carry; backend sync needs no
  redesign. Today it is **localStorage only** (`journiv.userTheme`).
- **`applyUserTheme`** renders the structured map to a single
  `<style id="journiv-user-theme">` in `<head>` — `:root { … } .dark { … }` plus
  `--font-sans` / `--font-reader` / `--prose-font-scale`. Called from `main.tsx`
  after `applyTheme` (no flash) and on every save / reset. We always serialise
  from the parsed map; a pasted string is never written to the DOM.
- **`parseThemeCss`** ingests a tweakcn / shadcn "Tailwind v4" export. A CSS
  declaration scanner — never a DOM or `<style>` probe. **Lenient about
  structure** (unknown selectors, `@theme`, `@layer`, `@custom-variant` are
  ignored, not rejected); **strict about names and values**: a declaration is
  kept only if the name is an allowlisted `ColorVar` and the value passes a
  function-name grammar (`oklch/oklab/rgb/hsl/color-mix/calc/var` …). `url(`,
  `image-set(`, `element(`, `expression(`, `@import`, `javascript:`, unbalanced
  parens → dropped with a note. `--font-*` → dropped with a note. Succeeds
  whenever ≥ 1 colour var survives. Covered by real tweakcn fixtures in
  `__fixtures__/`.
- **`exportThemeCss`** is the inverse, for copy / share. Fonts are a comment,
  not `--font-*`.

### A/B experiment layer (dormant)

[`uiExperiment.ts`](src/features/theme/uiExperiment.ts) +
[`UiExperimentSection`](src/features/settings/appearance/UiExperimentSection.tsx)
are a reusable harness: a **second** `<style id="journiv-ui-experiment">`
appended after the user-theme layer, toggling named axes so a proposed change
of feel can be judged against the current system on real screens, in both
themes, before it is committed. localStorage-only (`journiv.uiExperiment`),
never synced, raw values in JS on purpose (the static guard only polices
`.css`), and it reaches into `src/components/ui/*` rendered output by
`[data-slot]` selector rather than editing those files (§18) — which is why it
is a throwaway layer.

**The Settings control is unmounted** (`AppearancePage` renders no
`<UiExperimentSection />`). The harness stays wired at boot with
`uiExperimentCss(UI_DEFAULT) === ""`, so it adds nothing to the page — but a
future round only needs new axis fragments in `uiExperiment.ts` and the
component re-mounted, not new plumbing. When no further round is foreseeable,
delete the module, its test, the component and this subsection.

### Controls (Settings → Appearance → "Personalize")

Accent colour (curated preset swatches, or a typed colour); **system font** and **editor font** as _independent_ pickers over the bundled
set (`fonts.ts` — DM Sans always, others lazy); **text size** as a prose-only
scale (`--prose-font-scale`, consumed by `prose.css` — **the root font-size is
never scaled**, that would resize Tailwind's whole rem system); import / export
/ reset. Every setter previews live and persists immediately. There is
deliberately no corner-radius control (§3).

### The accent is a pair, never a colour

[`accent.ts`](src/features/theme/accent.ts) and
[`contrast.ts`](src/features/theme/contrast.ts) own this, and the rule is
short: **an accent is a light `{ brand, brand-foreground }` and a dark one, and
both are stored explicitly.**

Writing one brand value into both themes and leaving `--brand-foreground` at
its default is what this replaced, and it was not a near-miss — it put every
one of the eight curated presets under AA in at least one theme
(white-on-Amber at 2.66:1 in light, near-black-on-Slate at 2.65:1 in dark).
The reason is structural: `--brand` is a link colour _and_ a fill, so in light
mode every constraint wants it darker and in dark mode every constraint wants
it lighter. One value cannot serve both.

- A safe accent is a **band of lightness** per hue, not a point. `accentPair()`
  keeps the hue and chroma a user asked for and moves lightness into that
  band — for each theme separately. Presets go through the same function, so
  there is one rule and no special cases.
- The margin is 5.3:1, not 4.5:1. A token is rounded for display and a viewer
  may sit at a different gamma; an accent that lands exactly on the line has no
  room for either. `Journiv blue` is the single hand-written pair, because it
  _is_ the default in `tokens.css` and has to reproduce it exactly.
- A typed colour that cannot be parsed is **refused with an inline error**, not
  applied. `parseAccentColor` reads `oklch()`, `rgb()` and hex, and nothing
  else. Silently applying a colour the app cannot measure to a link colour and
  a focus ring is an accessibility failure, not a matter of taste.
- Amber and Teal are visibly deeper than their names suggest. That is the model
  working, not a bug: a light gold cannot both carry white text and be a
  readable link on a white page.
- An **imported theme is different** and is left alone. It carries its own
  `--brand` / `--brand-foreground` for each mode, authored together, so
  `importTheme` writes them through unchanged. The clamp applies to the accent
  _picker_, which is handed one colour and has to invent the rest.
- Every curated preset is asserted against `--background`, `--card` and its own
  foreground, in both themes, in
  [`accent.test.ts`](src/features/theme/accent.test.ts). Add a preset and the
  test covers it automatically; there is no list to remember to update.

### Rules

- Fonts come only from the pickers.
- No remote fonts — a self-hosted Journiv makes no external requests (§13).
- The accent picker writes `--brand` / `--brand-foreground`, not `--primary`
  (§3): `--primary` is neutral in both references, and the blue a user chooses
  is the identity accent.
- The remaining derived roles (`--line-strong`, `--danger-*`) are `color-mix`
  of stock tokens, so a user theme flows through them without being listed.
- `radius` is deliberately not themeable: the whole named scale derives from
  that one value, so letting a pasted theme move it would reshape every
  registry component at once.
- Backend cross-device sync is a **follow-up**; the `UserTheme` JSON is the
  contract it will reuse.

---

## 26. Authentication

Reference: none yet — add `docs/design/reference/26-login-*` when the capture
script covers it (§19).

Enforced: [`e2e/smoke/auth.spec.ts`](e2e/smoke/auth.spec.ts) (route guard,
sign-in, session) and [`e2e/auth/signup.spec.ts`](e2e/auth/signup.spec.ts).

- Three routes, `/login`, `/signup`, and `/oidc-finish`, outside the shell
  entirely — no nav, no `PageBar`, no Settings. They are the only screens in
  the product that are not one of the three panes.
- `.jv-auth` centres a single stock `Card` on `--muted` (the application
  canvas) — the only place the canvas itself is the whole page. Journiv sets
  nothing on the card but `max-width: 22rem`; its surface, radius and
  `shadow-sm` are the registry's own. This is the screen that should look most
  unmistakably like stock Base Vega.
- Brand mark, `.jv-display` heading ("Welcome back"), a one-line lede, then the
  form: email, password, a single `role="alert"` error line, one primary
  submit. Exactly one primary action, per §6.
- **Errors are deliberately generic.** "Sign in failed. Check your email and
  password." never distinguishes a wrong email from a wrong password — do not
  make this more specific even if the backend response would allow it.
- `returnTo` is carried in the `/login` route's search params and is where a
  successful sign-in navigates — so a session expiring mid-read returns the
  reader to the same Moment, not to the Timeline.
- `/signup` carries the same safe, same-origin `returnTo`. Its card reuses the
  authentication surface and adds name, email, password and password
  confirmation. Client validation covers required values, email shape and
  confirmation only. Because Journiv is self-hosted, signup intentionally
  accepts any non-empty password and does not impose a strength policy.
  Registration uses
  `POST /auth/register`, then signs in through `POST /auth/login`, writes the
  existing session abstraction and navigates to `returnTo`. If registration
  succeeds but sign-in fails, the card says the account exists and links to
  `/login`; it never encourages a duplicate registration attempt.
- Signup errors are status-aware but never echo the raw response: duplicate or
  invalid data (400), disabled signup (403), validation (422), rate limiting
  (429), and unavailable/network failures each get a calm human sentence.
- Both authentication routes read `GET /instance/config`. The login page only
  renders "Create an account" after configuration confirms that
  `disable_signup` is false. `/signup` fails closed while availability is
  unknown; a true flag replaces the form with a "Sign up is disabled" state
  explaining that an administrator can enable signup in the server
  configuration and restart Journiv. A configuration read failure gets a retry
  state and never exposes the form. The backend's first-user exception is not
  exposed in the frontend: bootstrap requires starting the backend with signup
  enabled.
- OIDC is part of the same authentication surface. When `oidc_enabled` is true,
  mixed-mode login and signup show the password form first, then a quiet `or`
  separator and one outline “Continue with single sign-on” action. When
  `oidc_only` is true, the form is absent and that action is the single primary
  action. If password signup alone is disabled, signup remains available through
  OIDC and explains that account provisioning is administrator-controlled.
- The OIDC action is a normal browser link to `GET /auth/oidc/login`, because
  the identity-provider redirect must navigate the top-level page. Before
  leaving, it stores the validated same-origin `returnTo` in session storage.
  `/oidc-finish` accepts the callback's one-time `ticket`, sends it exactly once
  to `POST /auth/oidc/exchange`, writes the existing session abstraction, clears
  the stored destination, and replaces the route with `returnTo`. Missing,
  expired, reused, and malformed tickets show one generic recovery state and
  never expose backend detail.
- Instance configuration does not expose an OIDC provider display name or
  whether automatic provisioning is enabled. The UI therefore uses the generic
  “single sign-on” label and does not promise that continuing will create an
  account; signup copy assigns that policy to the administrator.
- At widths up to 860px, the authentication card is top-aligned with the mobile
  page inset and reduced padding so forms remain usable with the on-screen
  keyboard. Its width, tokens, states, and action hierarchy otherwise remain the
  same in light and dark themes.

---

## 27. Divergences from Base Vega / Minimal Neutral

A short, closed list of places Journiv diverges on a **component, a token or a
class string the registry actually defines**. **Anything of that kind not here
is drift and should be removed, not documented.** Each entry names the concrete
product reason.

Journiv's own page composition is **not** in scope and never needs an entry
here (§5, §18): the shell, the settings modal, the Library workspace, the
editor and the adaptive overlays are product layout, not divergences from a
registry that has no opinion about them.

| Divergence                                                              | Reason                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| ----------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **DM Sans, not Inter**                                                  | The `bIkeymG` preset names Inter; Minimal Neutral — authoritative for theme values — ships DM Sans, which is already bundled and self-hosted (§3).                                                                                                                                                                                                                                                                                     |
| **`--muted-foreground: oklch(0.52 0 0)` in light**                      | Minimal Neutral ships `0.556`, which measures under AA against its own `--muted`/`--accent` (`0.95`). Journiv puts that exact pair on screen (tags, hovered rows, secondary badges), so the failure is real. Dark keeps MN's `0.708` verbatim.                                                                                                                                                                                         |
| **`--ring: var(--brand)`**                                              | The product's single global focus affordance. MN's neutral ring at Vega's `ring-ring/50` × 3px reads too faint to serve as one. Identity _and_ accessibility.                                                                                                                                                                                                                                                                          |
| **`Button variant="brand"`**                                            | One filled blue control in the whole product — the sidebar's "New entry". Writing is what Journiv exists for.                                                                                                                                                                                                                                                                                                                          |
| **`body { @apply bg-muted }`**                                          | The one deviation from base-vega's own reset, and it is the canvas decision itself (§3, "Surfaces").                                                                                                                                                                                                                                                                                                                                   |
| **`NativeSelect`**                                                      | A native `<select>` wearing `SelectTrigger`'s own class string. Native is genuinely better on touch and for long lists; the shared class string is what stops the two drifting apart. One class is overridden — `py-0`: `SelectTrigger` is a button whose label may overflow its box, but a native `<select>` clips to its content box, and `h-9` minus `py-2` is smaller than the line box, which cut the descenders off every value. |
| **`IconButton`**                                                        | Requires an accessible name and projects a ≥44px hit area regardless of the visual box. Behaviour the registry does not provide.                                                                                                                                                                                                                                                                                                       |
| **`.jv-view-switch` grows on coarse pointers**                          | The three segments sit flush, so `IconButton`'s projected hit area would overlap its neighbours and mis-fire. The control itself grows to `--tap-target` instead, and only where the pointer is coarse (§7).                                                                                                                                                                                                                           |
| **`sr-only` radios in the colour and icon pickers**                     | The swatch _is_ the value — a colour cannot be represented by a radio dot, and the icon grid is the same. A visually hidden native radio inside a `<label>` is the correct accessible primitive here, and `RadioGroup` would add a control that must then be hidden. Every other exclusive choice in the product uses `RadioGroup` or `ToggleGroup` (§18).                                                                             |
| **Selection = surface + rail + `aria-current`**                         | Selection is never colour alone. Stronger than upstream; keep it.                                                                                                                                                                                                                                                                                                                                                                      |
| **`--line-strong`, `--danger-surface`, `--danger-border`, `--success`** | Roles the stock set does not name, each a `color-mix` of a stock token so a user theme flows through (§3).                                                                                                                                                                                                                                                                                                                             |
| **On-media values** (`--overlay-scrim`, `--text-on-overlay`)            | They sit on a photograph, not a Journiv surface, so they must not follow light/dark.                                                                                                                                                                                                                                                                                                                                                   |
| **`radius` is not user-themeable**                                      | The whole named scale derives from one value; letting a pasted theme move it would reshape every registry component at once.                                                                                                                                                                                                                                                                                                           |
