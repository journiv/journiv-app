# Editor feature contract

Read this with [the Moments domain contract](../domain/moments.md) for Editor
work. It owns editing behaviour, drafts, attachments, metadata writes, and the
Quill boundary.

## Editing surface

Reading and writing use the same EntryHeader and prose styles. PageBar has a
journal selector when needed, the save status, one Cancel, and one Done primary.
The title is a growing textarea with an optional-title invitation. When the
PageBar shows the journal selector the header passes `showJournal={false}` so the
journal is not named twice; the reader has no such bar and keeps it in the
header. Toolbar controls keep a 30px visual size and 44px targets; pointer-down
prevention on toolbar buttons preserves the editor selection and must remain —
including on the More trigger, which opens over live writing.

The save status is one control (`SaveStatus`) in the PageBar at every width — an
icon plus one word (`Saved` / `Unsaved` / `Saving…` / `No changes`), with the
full sentence in a popover and as the button's accessible name. It folds in what
was the separate "saved on this device as you write" line; only a local-copy
*failure* still gets a loud in-flow alert below the header (`LocalDraftStatus`).
Tone is carried by icon and word, never colour alone.

The word count is document metadata, not a toolbar control. It shares one
bracketed footer unit (`.jv-editor__foot`) with the people and tag chips below
the prose — the count as a quiet line, then the same chips the reader shows
(`~N min read` is appended only once there is a minute's worth of words). The
whole footer is absent until there is writing to count or a chip to show, so a
blank entry is pure writing canvas. It is not a live region — it must never be
announced on every change.

The toolbar is a non-scrolling flex sibling of the scroll owner, like PageBar —
never a sticky layer over the prose. At the regular width it is a full-width band
directly under PageBar; at the compact width it re-orders (CSS `order`) below the
scroll owner and docks at the bottom, above the on-screen keyboard, and is shown
only while the prose surface holds focus or a keyboard is up. `useKeyboardInset`
tracks `window.visualViewport` and writes the live keyboard height to
`--jv-keyboard-inset` (and `data-kbd="open"`) on the editor root — imperatively,
never as React state, so viewport churn cannot re-render the page. This is a
bounded exception to DESIGN.md's "no JS layout state": it offsets one
fixed-height bar and drives no reflow.

Because the band sits outside the scrollport at the regular width, its
`scroll-padding-top` is now only a small breathing gutter. At the compact width
the docked bar floats over the bottom of the scrollport on iOS (the layout
viewport does not shrink there), so `scroll-padding-bottom` includes the live
keyboard inset plus the bar height. Both the browser's own caret tracking and
Quill's `scrollRectIntoView` honour scroll-padding, so a line scrolled into view
lands clear of the bar rather than behind it.

### Toolbar fit

The toolbar holds more controls than a narrow pane can show at 30px, and
shrinking them is not an option. This resolves two ways by width:

- **Regular width:** `toolbarFit.ts` measures the bar's own container and gives
  up groups to a "More actions" popover worst-earned first: list nesting is kept
  longest, then headings, undo/redo, ordered list, blockquote, underline/strike,
  and last the Markdown-help control. Bold, Italic, Bullet, Checklist, Link and
  the insert group never move. The insert group leads the bar — Add media, then
  Moment details, then (only while the entry is still empty) Write from a prompt
  (docs/features/prompts.md); `toolbarPlan` reserves that button's width via
  `hasPromptCta` only while it is shown. With the word count gone from this
  group, the whole formatting set fits inline in the three-pane editor pane at
  1440 with no More control at all.
- **Compact width:** no collapse and no More popover — every control stays on the
  bar and the row scrolls horizontally, the standard mobile toolbar pattern.
  `EditorToolbar` reads `useCompactViewport()` and passes `scrollable` to
  `toolbarPlan`, which then returns every group. The scrollbar is hidden and
  overscroll is contained so a swipe past the end does not fire the browser back
  gesture.

Nesting is ranked first because it is the only *contextual* group: at the moment
it exists at all, it is what the writer is doing, and on touch it is the only
route to nesting there is. The cost is that the caret entering a list line can
push the lowest-ranked group into the popover. That displacement is
unavoidable — 64px has to come from somewhere — and the alternatives are worse:
reserving the space permanently costs a real group at every width, and ranking
nesting last buries Outdent/Indent in the popover even on a 1920px screen.

Each group is rendered in exactly ONE place per width — on the bar or in the
popover, never both with one copy hidden, which would put two controls with the
same accessible name in the tree. That is why this is measured rather than a
container query: the choice is not presentational. It measures its own
container — the centred inner row of the band (`.jv-toolbar__inner`), not the
full-width band chrome and not the window — which DESIGN.md allows as "a
component reflowing at its own width" (`features/media/useVirtualGrid.ts`
follows the same reasoning). An unmeasured width, and the compact scrolling bar,
show every group.

### Typing cost

Nothing in the editor may do work proportional to the document on every
keystroke, and a keystroke must not re-render the editor page:

- `QuillSurface` hands `onStateChange` a new `EditorState` only when one of its
  fields actually changed. Typing a letter into a paragraph alters no format, no
  selection length and no selected embed, so it produces no host render.
- The word count is recomputed on an interval (`WORD_COUNT_INTERVAL_MS`), not
  per keystroke: counting words reads the whole document. It settles within one
  interval of the last keystroke.
- `onInlineMediaChange` fires only for a change that could alter the document's
  embeds — an embed insert or a deletion — and only when the resulting paths
  differ. Ordinary typing never reads the document for it.
- `initialContent` is cloned when a surface is built, never on render.
- The caret's media kind is read off the blot at that position, not by slicing a
  Delta out of the document.

`EditorToolbar` takes the surface as a **ref**, not as `ref.current` read during
render. The handle is published during commit, so a render-time read is `null`
on first render and only corrected by some later re-render — which the rules
above deliberately removed.

`/timeline/$momentId/edit` and its journal-scoped twin also take a `seedNote`
search flag from Quick Log's "Continue as full entry" — see
[quicklog.md](quicklog.md) for what it does.

The editor date is EntryDateControl: a popover Calendar with native month/year
selection and time field. A new Entry uses browser timezone and sends UTC plus
that zone. Editing a Moment preserves its recorded zone and interprets picked
wall time in that zone. Date changes on an existing Moment persist immediately,
refresh ordering, and do not mark prose dirty. There is no arbitrary timezone
selector. Date conversion helpers own DST behaviour; never persist the
browser-local Date serialization.

## Markdown input

Markdown is an *input method*, never a stored format. Typed shorthand is
rewritten into the same Delta the toolbar would produce; persisted content stays
a Quill Delta. Two pieces cooperate:

- **`markdownShortcuts.ts`** owns headings (`#`/`##`/`###`), the quote marker
  (`>`) and the inline runs (`**b**`/`__b__`, `*i*`/`_i_`, `~~s~~`,
  `[text](url)`). Its allowlist test pins it to the Gate-1 formats so a rule can
  never widen what the editor saves. It is installed by `QuillSurface` on the
  writing surface only; the read-only reader never rewrites. Rewrites apply
  synchronously inside the triggering text-change — nothing is deferred, because
  this module never performs a `<p>`→`<ol>` block-blot swap, which is the one
  thing Quill will not do mid-text-change.
- **Lists are Quill's own `list autofill` keyboard binding**, not this module.
  `QuillSurface` replaces that binding with a Journiv handler keyed on
  `^\s*?(1\.|-|\*|\[ ?\]|\[x\])$`: `- ` / `* ` → bullet, `1. ` → ordered (Quill
  renumbers the items itself), `[ ] ` → `unchecked`, `[x] ` → `checked`. `2. `
  and `10. ` stay literal — the ordered trigger is a bare `1.` only. Whitespace
  the marker was typed after sets the nesting level: one tab, or every two
  spaces, is one `indent` step, capped at 5.

These are typing shortcuts, not a CommonMark parser:

- **Boundaries / escaping are positional.** A heading or quote marker fires only
  when the text from line start to caret is *exactly* the marker plus one space,
  so `\# `, `  # ` and `a > b ` stay literal. An inline run fires only when its
  opening delimiter is at line start or right after whitespace, so `foo_bar_`,
  `2*3*4`, `word**x**` and a delimiter after `(` stay literal. A `\` before a
  delimiter blocks the match because it is non-whitespace; backslashes are never
  consumed or interpreted. Four or more hashes, `***x***`, `**_x_**`, `****`,
  `` `code` ``, `![img]()` and malformed or unsafe links (`[x]()`,
  `[x](javascript:…)`, `[x](ftp:…)`) are left completely literal — never
  partially transformed.
- A line that already carries a block format is left alone.
- Each `markdownShortcuts.ts` rewrite is one `"user"` change bracketed by
  `history.cutoff()`, so a single undo of a bare marker restores the literal
  characters; if content was already typed after the marker, the first undo
  removes that content and the second reverts the format. Quill's list binding
  brackets its transform the same way.
- The toolbar's "Markdown shortcuts" control opens `MarkdownHelpDialog`, a
  reference shown through the shared adaptive overlay. Formatting-toggle
  `aria-pressed` state stays in sync because the rewrite re-emits editor state.

Inline `code` and code blocks are deliberately out of scope: they need a Gate-1
contract expansion (this document, `deltaProfile.ts`, the backend guard, prose
styles, and the reader) before an input shortcut for them can exist.

## Lists

The `list` line attribute has four values: `bullet`, `ordered`, `unchecked`,
`checked`. A separate `indent` line attribute (integer 1–5) nests a list line;
it is a **list-only modifier** — `deltaProfile.ts` rejects `indent` on any line
that is not a list line, and `QuillSurface.getContents()` runs
`stripOrphanIndent` so a nested item turned into a heading cannot carry one into
a save. Blockquote stays single-level.

The toolbar carries Bullet, Ordered and Checklist toggles (the Checklist toggle
owns both task states) plus Indent / Outdent controls that appear only while the
caret is on a list line. `Tab` / `Shift+Tab` do the same nesting from the
keyboard, clamped to the 0–5 range. Ticking a task box is a `checked` ⇄
`unchecked` line-format change like any other toolbar toggle — there is no
document-history entry beyond the normal one.

The reader renders task boxes and nested lists for reference only: its Quill
instance is disabled, so the checkbox is inert and there is no prose-write path
to persist a tick. Server-side rendering (`app/utils/render_engine.py`, used by
PDF export) emits `<ul class="checklist">` with disabled `<input type="checkbox">`
and a real nested `<ul>` / `<ol>` tree.

## Attachments

Server identity comes first. On a new Entry, the first media attachment or
metadata write creates the draft Moment and draft Entry; simply opening the
editor creates nothing. Done finalizes the draft.

The attachment pipeline is:

    capture caret -> ensure draft -> placeholder -> upload/import ->
    durable reference -> save

Capture the caret before a picker opens. Placeholders carry only an upload id;
object URL, filename, and status stay in the side registry. A successful swap is
one Delta operation. If the live placeholder is gone when an upload completes,
delete the uploaded media rather than reinserting it. Release object URLs on
unmount, not placeholder removal, because undo can restore a blot.

Once a placeholder is swapped for a real embed there is nothing left to find by
upload id, so Retry and Remove act on the embed itself
(`QuillSurface.removeEmbedForMediaId`, matched by the durable media id in its
signed-URL source). Retry on a placed item is not one thing: a stalled poll
(the window elapsed with no terminal state) just resumes polling, since the
file may still finish; a definitive server-side failure has no "reprocess this
row" request, so it re-imports (Immich, upserting the existing row) or
re-uploads (device, a new row swapped in where the old embed was, with the
failed row deleted) instead. The two are tracked as attachment state
(`failureReason`), never inferred from a message string. Remove on a placed
item deletes its embed, marks the document dirty, and deletes its row: these
are this session's own attachments, and the save's orphan cleanup only
collects media the previously saved document referenced, so an unsaved one
would otherwise stay on the Moment as an "unavailable" attachment. Remove is
only offered for failed items, so this never deletes media that existed before
the edit. Leaving the editor without saving is the exception: that sweep
aborts anything still uploading or importing but passes `keepPlacedMedia` for
everything already placed, because marking the document dirty there would
re-arm and resurrect the local draft the same flow just explicitly discarded.

Only upload/import blocks Done; server processing does not. Use the isolated
XHR upload helper for progress, never another API client or Axios. Use formats
returned by the media-formats endpoint, with wildcards only while it loads.
Drop and paste call the same attach entry point. Keep Quill's uploader disabled
and reject foreign image embeds; stored documents use durable relative media
references, never base64 or third-party URLs.

Removing prose media is dirty and becomes deletion after save through the
backend's orphan handling. Clear Quill history after successful save so undo
cannot restore a deleted reference. Cancel aborts active uploads and discards
this-session draft identity, but keeps attached photos as a media-only Moment.
Never delete media that existed before the edit.

Media already attached to an existing Moment is shown above the prose by the
shared `components/journiv/MomentMediaGallery` in `variant="tray"`: a labelled
panel ("On this moment") of small cropped thumbnail tiles, deliberately *not*
the reader's full-bleed content treatment, so it never reads as if the photos
are already in the entry. The editor passes a per-item "Add to entry" control
(a `+` `IconButton`) through `renderItemAction`.

"Add to entry" calls `QuillSurface.insertMedia` with the item's signed URL — the
same durable-embed shape an upload produces, which the backend maps back to the
media id on save (`normalize_delta_media_ids`, which only ever remaps an id
already on the Moment), so no second media record is created. `insertMedia` also
scrolls the new embed into view and rings it briefly (`.jv-prose__media-flash`,
collapsed by the global reduced-motion reset), and re-adds the trailing newline
a block embed placed at the document end would otherwise leave off. The source
tile then flips to an "Added" state (dimmed, check badge, no action) rather than
disappearing, so the before/after is legible; once every addable attachment is
added the tray collapses to a one-line summary with a Show toggle. Tray dedup is
by `excludePaths` fed from `QuillSurface.onInlineMediaChange` — in tray mode it
*marks* rather than *hides* (content mode still hides).

It is not session media: opening or cancelling the editor never deletes it, and
it stays attached to the Moment (and in the reader gallery) until a save drops it
from the document. The first save of a note-only Moment is `entry_create` and
runs no orphan check; a later `entry_update` that no longer references the item
hits `delete_orphaned_media_for_delta` (old delta sources minus new), which
deletes the `MomentMedia` row, its file, and decrements `media_count` — the same
one-way path as any other prose media. Media never inserted is never in a delta,
so it is never collected. Nothing is inserted automatically — "Write about this
moment" carries the note, never the media.

"Add to entry" is offered only for `media_type` the editor can embed inline —
`image` (Quill's own blot), `video` and `audio` (Journiv's, in mediaBlots.ts),
which is exactly `INLINE_MEDIA_KINDS` and the document guard's allowlist. A
`media_type: "unknown"` attachment still renders as a tray tile (paperclip
glyph) and stays on the Moment; it is never offered and never inserted.

The optional Immich path is feature-gated by instance configuration. It uses
the same draft, placeholder, cancellation, processing-poll, and durable-media
rules as device upload. The asset endpoint is paged, newest-first, and has no
server filtering; do not invent one in the client.

## Local and server drafts

Server and local drafts solve different problems:

| Server draft | Local IndexedDB draft |
| --- | --- |
| owns a Moment and media | preserves unsaved writing Delta |
| created on first attachment/metadata intent | debounced after meaningful editing |
| visible across devices as draft identity | device-local |
| finalized by Done or session Cancel | retired on save or explicit discard |

Server drafts do not autosave prose. Local drafts store durable media ids only,
never signed URLs, object URLs, or base64. Draft canonicalization is the sole
translation layer that knows media signing.

Recovered drafts continue the same session. Never allow a recovered local draft
to claim or cancel an existing saved Moment. Verify its recorded Moment before
using it; only a definite 404 means it is gone. Leaving keeps the local draft;
Cancel discards it. A retired record stays retired.

## Conflicts, errors, and metadata

For existing Entries, send expected_updated_at. A 409 leaves writing intact and
offers Save anyway without that version. There is no merge or diff because the
backend has no history. Do not send the version for invisible draft Entries.

ApiError preserves status. Never read an unavailable request as a resource
absence. Use the shared UUID helper rather than direct crypto.randomUUID so
plain-HTTP self-hosting remains supported.

Moment details is one popover in the toolbar. The field group itself is the
shared `components/journiv/MomentDetailsPanel` (Quick Log is its second
consumer — [quicklog.md](quicklog.md)); the editor keeps only the popover shell
and injects its Immich people-suggestion strip through the panel's
`renderPeopleSuggestions` slot. It lazily ensures a Moment then writes mood,
location, weather, people, and tags through their actual operations. Header metadata and foot chips refresh after success. Existing
Moment metadata writes are immediate and not prose-dirty; new-entry writes are
dirty so Cancel protects the created draft. Every failed user action reaches the
screen with a human message.

Mood is identity colour plus name, not a guessed Lucide icon or valence scale.
Location search and current-location reverse lookup keep documented fields;
weather requires coordinates and shows an enabled-service failure without
saving. People writes replace the complete set; tags add by name and remove by
id. Immich people suggestions are add-only, never automatic, and a suggestion
fetch failure is a quiet retry state rather than a failed save.

## Quill boundary

Prose styles target semantic elements, never Quill. The Quill adapter stylesheet
and media blots are the only Quill-aware styling/code boundary. `QuillSurface`,
`QuillReader`, `deltaProfile.ts`, and `markdownShortcuts.ts` are the only
Quill-aware code. Reader and Editor share the same accepted-document guard.
Every media kind accepted by the guard must be in EDITOR_FORMATS; a test
protects this coupling.

## Known gaps

- At the compact width the docked bottom bar floats over the scrollport on iOS
  (the layout viewport does not shrink for the keyboard there). A caret the
  writer has themselves scrolled behind it stays there: nothing scrolls a caret
  that is already inside the scrollport. At the regular width the band is outside
  the scrollport, so this cannot happen.
- The standalone export viewer (`journiv-viewer`, separate repo) has its own
  client-side Delta renderer and does not yet draw task boxes or nested lists;
  exported ZIPs carry the `checked`/`unchecked`/`indent` deltas regardless.
- Reader task boxes are display-only; there is no way to tick one from the
  reader.
- Caret preservation through the file chooser, pending-upload save refusal, and
  placeholder-removal races have Chromium coverage at compact width. The
  `visualViewport` keyboard docking for the compact toolbar is implemented but
  still needs real-device verification on iOS Safari and Android Chrome, along
  with the physical-device media picker.
- Conflict resolution is refuse-or-overwrite; no merge exists.
- Recovering the same local draft in two tabs can race on draft-Moment finalization.
- Logged date has no arbitrary timezone selector.
- Immich has no asset search, type/date/album filters, duration/dimension data,
  or in-picker preview.
- Immich people sync_enabled is import-time only; suggestions are synchronous
  and unexplained when no eligible person appears; normalized people lack an
  appearance count.
