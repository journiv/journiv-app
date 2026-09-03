# Moments domain contract

Read this for Timeline, Reader, Editor, Calendar, Media, scoped moment lists,
or any work that renders moment metadata and time.

## Moment and Entry

A Moment is a container. Its optional Entry is writing; a Moment is meaningful
when it has any entry, note, mood, prompt, pin, media, location, weather, tags,
or people. Classification belongs in [src/lib/moment.ts](../../src/lib/moment.ts);
do not recreate it in a component.

| Kind | Condition | Rendering rule |
| --- | --- | --- |
| titled entry | Entry has a title | title and excerpt are primary |
| untitled entry | Entry has no title | moment text is body weight; date is the h1 |
| note-only | no Entry, has note | note is body text, never a title |
| media-only | no Entry/note, media exists | media is primary; invite writing |
| marker-only | only contextual fields | show context and invite writing |

Never invent an “Untitled moment” title. Every kind reaches the editor through
the same write-about-this-moment path.

## Metadata

MomentMeta has a surface-specific budget:

| Surface | Budget | Order |
| --- | --- | --- |
| row | 3, or 2 below 860px | journal, location, mood, weather |
| compact | 2 | same order |
| reader | one unlimited row | same order |

List overflow is dropped rather than shown as a count badge. People and tags
are not MomentMeta: shared MomentChips renders them at the foot of Reader and
Editor. Reader only displays metadata; editing belongs to the Editor contract.

Use only API-documented location data. locationLabel reads name, locality,
admin area, then country; never infer a missing label.

## Time and list modes

Render each Moment in the timezone where it happened. Timeline grouping uses
logged_date_tz, not the viewer's date. Use Today or Yesterday only when the
moment timezone matches the viewer timezone; otherwise use the explicit date.
Times use tabular numerals. The helpers in
[src/lib/datetime.ts](../../src/lib/datetime.ts) own these rules.

The Timeline workspace has URL-selected list modes:

- Timeline is the default chronological list.
- Calendar uses the shared validated view/month/date search shape; changing a
  day updates URL state without leaving the calendar.
- Media uses the media-library query, only moments with media, and keeps the
  current reader detail mounted.

ListViewSwitch is three router links in ButtonGroup, not ToggleGroup: one
destination is current, not pressed. Media tiles are navigational thumbnails and
may crop; Reader media is content and follows the Reader contract.

## Known gap

Sticky day headers need a real iOS Safari check. If nested scrolling misbehaves,
make them static rather than adding JavaScript.

