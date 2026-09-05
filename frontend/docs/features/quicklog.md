# Quick Log feature contract

Read this with [the Moments domain contract](../domain/moments.md) and, for the
hand-off, [the Editor contract](editor.md). Quick Log is a lightweight capture
for a moment you do not want to sit and write about.

## Surface

Quick Log is the "substantial form" adaptive overlay (`DESIGN.md`, "Responsive
layout and overlays"): `AppAdaptiveDialog` renders a bottom Drawer at ≤860px and
a centred Dialog above it. It is not a route — it mounts in `AppShell` and is
opened through `useShell().openQuickLog()`. `AppShell` remounts it with a fresh
`key` on every open so each capture starts from clean state.

Entry points (v1):

- the sidebar, as a quieter `outline` sibling under the brand "New entry" button;
- the compact Timeline `PageBar` actions slot.

Calendar, Media, Journals and Library surfaces do **not** get an entry point —
they are for browsing existing moments. The sidebar control is the global way in
from anywhere else.

## Composition

Top to bottom: mood, then a short note, then a prominent "Add media" action with
inline previews, then an "Add details" disclosure. Mood and the disclosed
fields (location, weather, people, tags) are the shared
[`MomentDetailsPanel`](../../src/components/journiv/MomentDetailsPanel.tsx) —
Quick Log is its second consumer, which is why it moved out of the editor
feature. `sections={["mood"]}` renders it standalone at the top;
`sections={["location","weather","people","tags"]}` renders the rest in the
disclosure. Nothing autofocuses — mood is the intended first interaction and a
compact sheet must not summon the keyboard on open.

Activities are deliberately out of v1. When an activity-selection component
exists it belongs in both Quick Log and the full editor; the panel's `sections`
list is the seam for adding it.

## Server identity and lifecycle

Quick Log follows the editor's "server identity first" rule: the first write of
any kind — a mood tap, a detail, a media upload — creates a real Moment through
`POST /moments` (`useQuickLogMoment`). Unlike the editor there is **no Entry and
no draft flag**, so the row is an ordinary note / mood / media-only Moment
(`docs/domain/moments.md`) and is visible in the Timeline immediately.

- **Log moment** persists the note (`PUT /moments/{id}`), stops owning the row,
  invalidates the moment lists, and closes. There is no toast — the new Moment
  appears at the top of the Timeline.
- **Continue as full entry** persists the note, then navigates to
  `/timeline/$momentId/edit?seedNote` (see below). The same Moment and every
  field and media association carry over untouched.
- **Dismiss** (swipe / Escape / outside press / desktop Cancel) with nothing
  entered just closes. With meaningful content it routes through
  `AppConfirmDialog` ("Discard quick log?"). Confirming deletes the row —
  **except** that media already uploaded is kept as a media-only Moment, the
  same rule the editor's Cancel uses (`editor.md`). The unsaved note is dropped.

"Meaningful content" is a note, mood, person, tag, location, or media —
auto-fetched weather on its own does not count. The primary actions are disabled
until then.

The note lives in `moment.note` and is capped at 500 characters server-side. It
is held in sheet state and only written on Log moment or Continue — a detail
write that creates the row early does not carry the note with it.

## The `seedNote` hand-off

`/timeline/$momentId/edit` and `/journals/$journalId/$momentId/edit` accept a
`seedNote` boolean search flag. When it is set and the moment has a `note` and no
Entry yet, the editor seeds that text as the opening paragraph of the body
(`prependPlainParagraph`, [`bodySeed.ts`](../../src/features/editor/bodySeed.ts))
and clears `moment.note` in the **same request** that first saves the Entry, so
the reader never shows the text twice. A failed save leaves the note intact.

## Known gaps

- v1 is create-only. `useQuickLogMoment` accepts a `momentId` so an
  "edit an existing lightweight moment in Quick Log" mode can be added later, but
  nothing passes it. Editing an existing note-only / marker moment stays with the
  editor's "Write about this moment" path.
- No date control: a quick log is always "now" in the browser timezone.
  Backdating is a full-editor affordance.
- No silent geolocation. Location and weather are only fetched through the
  explicit controls in the details disclosure.
- Immich media picking is editor-only; Quick Log uploads from the device.
- There is no per-moment media count limit in the backend, so the sheet imposes
  none.
