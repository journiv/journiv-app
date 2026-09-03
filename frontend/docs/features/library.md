# Library feature contract

Library contains People, Tags, Moods, Activities, and Goals: journal content,
not application preferences. It is a chrome management workspace spanning the
shell's content columns, with one scroll owner and one dominant action. Existing
/settings/journaling paths stay stable; route behaviour, not their legacy prefix,
determines the presentation.

Library uses a background canvas, panels of LibraryRows, and Cards for titled
detail blocks. A list-to-detail transition is a push in the same workspace, not
a third shell pane. Use LibraryWorkspace and LibraryDetailView rather than
recreating their scroll/header/breadcrumb behaviour. Entity “View moments”
opens the ordinary scoped Timeline, not a Library detail.

Forms are AppAdaptiveDialogs with footer actions and Field primitives. Menus are
AppAdaptiveMenu action data; destructive actions use AppConfirmDialog. The
shared Library patterns belong in components/journiv only because multiple
entities consume them.

## People and groups

People combine complete people and group responses into directory sections.
Named groups are expanded by default; ungrouped people are a muted fallback
that is collapsed when real groups exist. A person can appear in multiple
groups, and all membership language is “Manage groups,” never a singular group.
Deleting a group never deletes its people.

Rows include avatar/initials, display name, available nickname/count metadata,
and the actual supported actions. Group management swaps in-place views rather
than stacking dialogs. Import from Immich is visible only for configured,
connected instances; its partial-success import can create, link, or skip rows,
then invalidates people. Suggested-sync is default-on at import and has no later
toggle.

## Activities, goals, moods, and tags

Activities follow the People directory, but have zero-or-one group membership.
Group deletion moves activities to the ungrouped section; definition deletion
preserves existing moment links. Use actual create/update/delete operations;
generated reorder endpoints are not an instruction to add UI reorder controls.

Goals use the existing Goal contract and history dialog. Moods are identity
colours/names rather than a presumed emotional scale. Tags use their existing
detail workspace and scoped Timeline action. Data marks stay minimal and
feature-local until another surface needs them.

## Known gaps

- Mood colours are identity, not valence; use category/score for meaning.
- Immich people cannot change sync_enabled after import, face suggestions are
  synchronous, empty suggestions are unexplained, and imported people lack an
  appearance count.

