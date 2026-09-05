# Journiv design contract

This file defines Journiv's global visual and interaction design system. It is
the contract for every UI task, not an encyclopedia of feature behaviour. Read
[docs/README.md](docs/README.md) to discover relevant domain, feature, and
engineering contracts.

When this file and implementation disagree, investigate code and tests:
working behaviour is the fact, and stale documentation must be corrected in
the same change. Do not silently follow a stale rule or change product
behaviour only to make old prose true.

## Product character

Journiv is a private personal journal for writing today and enjoying rereading
months later. It should feel calm, personal, refined, quiet, trustworthy, and
content-first. It is not an enterprise dashboard, task manager, or generic
three-pane application.

Base Vega provides generic component construction and Minimal Neutral provides
the visual token language. Use existing primitives and tokens rather than
inventing colours, sizes, spacing, or radii.

## Principles

1. Keep generic controls close to the Base Vega registry. Change tokens before
   editing a Tailwind class in components/ui.
2. Product CSS expresses Journiv layout and behaviour, not a second control
   design system.
3. Interactive controls are identifiable at rest: a border, filled surface, or
   shadow-xs exists before hover.
4. Elevation describes a surface's role; it is not decoration.
5. Reading content is quiet; chrome is structured. Do not wrap journal prose in
   cards or dividers. Group related controls on management and overlay surfaces.
6. Never invent data the API did not return. Design honest loading, empty, and
   error states rather than leaving raw text in a pane.

## Tokens and typography

The semantic token source is
[src/styles/tokens.css](src/styles/tokens.css), mapped into Tailwind by
[src/styles/index.css](src/styles/index.css). Use stock semantic roles, never
raw colours in product styles. Primary is neutral. Dark mode is the .dark class
on html.

Journiv's blue is brand, used only for the filled sidebar New entry action, the
focus ring, selected-item rail, and navigational text links. It is not a
general accent for badges, controls, charts, hover states, or selected
backgrounds. User personalization may change the brand pair but must retain
readable light and dark foregrounds.

### The identity mark

The logo is a distinct thing from that accent. `BrandMark`
([src/components/journiv/BrandMark.tsx](src/components/journiv/BrandMark.tsx)) —
a Georgia-Italic `j` in an asymmetric rounded tile — is the product's fixed
identity: the tile is the literal hex `#405DE6` and the glyph is white, baked
into the SVG, and it stays that colour in dark mode and under every user
accent. `--brand` / `--brand-foreground` are the *customisable* UI accent and
must never colour the mark; equally the mark's raw hex must not appear anywhere
else. It sits in the sidebar next to the "Journiv" wordmark (which carries the
name, so the SVG is `aria-hidden`), and centred and enlarged above the heading
on the auth card, where it stands alone and takes an `aria-label` instead. The
same geometry ships as `public/favicon.svg`,
`public/favicon.ico` and `public/apple-touch-icon.png`; regenerate all three
together if it ever changes. This is not a PWA install contract — there is no
web app manifest or maskable icon yet.

The only extra roles are line-strong, danger-surface, danger-border, success,
and theme-independent on-media values. They derive from semantic roles where
possible so imported themes flow through. Journal, mood, and entity colours are
API data and may be set at runtime; they are not stylesheet palette values.

Canonical token facts, checked by npm run lint:design:

- `--radius` 1rem. Use Base Vega's named derived radius scale rather than
  literal steps.
Spacing: 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64 as `--space-1` through
`--space-16`.
- `--bar-height` 52px.
- `--reader-measure` 68ch.
- `--tap-target` 44px.
- `--duration-fast` 110ms.

DM Sans is the bundled system font. The reader font owns reading and editor
prose; no remote fonts. Use existing role classes in
[src/styles/base.css](src/styles/base.css) and semantic prose styles in
[src/styles/prose.css](src/styles/prose.css), not one-off px font sizes.

## Surfaces, shape, and elevation

Minimal Neutral's surfaces are intentionally distinct. In light mode, chrome
and content use subtle separation; in dark mode their order inverts. Preserve
that relationship rather than forcing light-mode hierarchy into dark mode.

| Role | Treatment |
| --- | --- |
| resting control | border, fill, or shadow-xs |
| grouped or detached surface | shadow-sm when separation is needed |
| popover or menu | shadow-md |
| dialog or drawer | shadow-lg |

The reader is content: prose has a measured column, no card, and no paragraph
dividers. Timeline rows are content-side list rows. Management screens,
settings, dialogs, and libraries are chrome: use a clear canvas, panels, Cards,
fields, and grouping where controls belong together.

Do not put a card around a single ungrouped value, or add a card simply because
there is empty space. A row's hover shape matches its container: flush inside a
clipping panel, rounded within a gapped list.

## States and actions

| State | Global treatment |
| --- | --- |
| resting | identifiable control at rest |
| hover | muted surface; content may lift |
| selected | accent plus a 3px brand rail and aria-current |
| focus-visible | existing native/product outline or upstream registry ring |
| disabled | opacity 0.55 and cursor not-allowed |
| loading | shape-matching Skeleton or pane-level StatusView |
| error | human message, pane-level StatusView, and retry where possible |

Selection is never colour-only. Secondary row overflow actions may be hidden
only on fine hover pointers, must remain in the accessibility tree and tab
order, reveal on focus, stay visible while open, and have another route to the
same capability. A sole action is never hidden.

Use explicit Base Vega button variants. There is exactly one surface-primary
default or brand action. Brand is reserved for the sidebar New entry action;
destructive is serious and tinted rather than another primary. Cancel and Done
must not look identical.

Use StatusView for pane-level empty or error state. A bare sentence, unfiltered
server error, or silent failed action is not acceptable. Loading skeletons
mirror the eventual layout.

Transient notifications (toast) report one-shot action outcomes that do not
invalidate the current screen — a download, a background command. An error that
prevents viewing or completing the current screen stays inline or pane-level
with StatusView, never a toast. Error toasts announce assertively (Base UI
Toast `priority: "high"`) and offer their retry as the toast action where the
action can be retried.

## Icons, motion, and accessibility

Use Lucide icons. Icon-only controls use IconButton with a label and a
44px target. Small visual controls can have a larger transparent target; flush
segmented controls grow their own target only on coarse pointers so hit areas
do not overlap.

Use the existing fast transition token for product hover and selected state.
Registry dialogs and drawers retain upstream entry motion. Honour reduced
motion globally; do not add decorative animation.

- Every control has visible focus.
- Body text and new foreground/background pairs meet AA in both themes.
- One h1 exists per screen. If a Moment has no title, its date is the heading.
- Icon-only controls have labels and form controls have labels.
- Formatting toggles expose aria-pressed.
- Errors use role alert; loading regions use role status.
- Keyboard and assistive-technology review remain necessary even when automated
  checks pass.

## Responsive layout and overlays

The app has exactly two page-layout breakpoints:

| Width | Layout |
| --- | --- |
| over 1100px | persistent navigation, list, and page panes |
| 861–1100px | list and page; navigation moves to its drawer |
| 860px or less | one pane per screen; history navigates |

Components may reflow at their own documented container-query width. Do not add
page-shaped breakpoints or JS layout state. Every pane has one scroll owner;
PageBar is its flex sibling, not a sticky layer over scrolling content.
Safe-area insets apply to drawers and scrolling-pane bottoms.

Use a named container query when a component must fit a pane, dialog, or card:
the viewport can become narrower while that component becomes wider, so it is
the wrong measurement. Put the container on the box that owns the available
inline size, measure the rendered budget, and document the reason next to the
rule. The documented 860/1100 page bands remain the only page-layout widths;
the design guard requires any new component-level media-query width to be
explicitly allowed rather than introduced silently.

The interaction selects an overlay family; the 860px boundary selects its
presentation:

| Interaction | compact | regular |
| --- | --- | --- |
| substantial form | Drawer | Dialog |
| simple confirmation | Drawer | AlertDialog |
| command menu | Drawer action sheet | DropdownMenu |
| anchored picker | Popover | Popover |
| routed application surface | route-specific | route-specific |

Use AppAdaptiveDialog, AppConfirmDialog, and AppAdaptiveMenu for the first
three rows. Feature code does not choose their branch. State lives above the
adaptive primitive, only one branch mounts, the body is the scroll owner, and
form actions live in the fixed footer. Do not autofocus a compact-sheet text
field; use the existing overlay autofocus helper.

Dismissible is presentation behaviour, not dirty-state policy. Callers own
unsaved-change prompts and cleanup. Typed or multi-step destructive flows are
forms and use AppAdaptiveDialog, not simple confirmation. Popovers remain
anchored popovers. Settings and shell navigation are documented routed-shell
exceptions in their feature contract.

## Global component rules

Use Base Vega compositions for generic arrangements: Card for a titled group,
Field for labelled input/help/error, Item for a structured row, RadioGroup or
ToggleGroup for exclusive choices, Empty through StatusView, ButtonGroup for
related actions, and Table for tabular data. This does not prohibit Journiv's
own page structures; it prevents rebuilding a generic primitive with a div and
bespoke CSS.

The durable allowed divergences are bundled DM Sans; the documented readable
muted foreground and brand focus ring; the one brand button variant;
NativeSelect; IconButton's accessible target; coarse-pointer view-switch
growth; visually hidden native radios where a swatch or icon is the value;
selection as surface plus rail plus aria-current; documented Journiv extra
roles; and non-themeable radius. Any new divergence needs a concrete product
reason and belongs here, not as a feature-local visual fork.

## Data visualization

Charts render through the Base Vega `Chart` primitive
([src/components/ui/chart.tsx](src/components/ui/chart.tsx)), which wraps
Recharts. Recharts is the drawing implementation only: a chart's colours come
from `--chart-1…5` (single series) or existing semantic roles (categorical
series) via the `ChartConfig` `color` field, never raw values; axes, grid and
tooltip inherit the primitive's token wiring; and every chart ships an
equivalent visually-hidden table or text summary. Keep chart code
feature-local until a second feature needs the same mark. The small tokened
SVG marks in the Library workspace
([src/features/library/tagCharts.tsx](src/features/library/tagCharts.tsx))
remain valid for a one- or two-mark aside where a full chart would be
overweight. Insights owns the feature contract for the analytics surface
([docs/features/insights.md](docs/features/insights.md)).

## Verification

Run npm run verify for frontend changes. The design guard is static: it checks
source-level design discipline, real token consumption, allowed breakpoints,
links from this document, and the token facts above. It does not prove rendered
contrast or layout. For visual work, inspect 1440, 1024, and 390 in both
themes; the E2E and reference-capture workflow is documented in
[e2e/README.md](e2e/README.md) and
[docs/architecture/frontend.md](docs/architecture/frontend.md).
