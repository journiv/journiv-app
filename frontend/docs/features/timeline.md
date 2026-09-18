# Timeline feature contract

Read this with [the Moments domain contract](../domain/moments.md).

The header names the real scope: a journal title and colour mark, or All
journals, never a generic Timeline title. Below 1100px PageBar carries the
scope so it is not repeated.

Rows show time, optional kind chip and pin, title or body-weight moment text, a
two-line excerpt, then the domain metadata budget. Do not use a single-line
ellipsis for a two-line row. Media thumbnails are 68px, 80px on mobile, with a
count badge; they are navigational and can crop.

This is a content list: no dividers or surrounding panel. Selection is the
global accent surface plus brand rail. Calendar and media-list rules belong to
the Moments domain contract.

`momentsQuery` keeps the previous page visible (marked `aria-busy`, with "Load
more" disabled) while a search narrows within the same scope, but never across
a scope-subject change — All moments to a person, or journal A to journal B —
where a retained row would carry the old scope's title and link target
(DESIGN.md "Navigation loading"). `sameMomentScope`
(`src/api/query/keys.ts`) is what tells the two apart; it defines scope
identity by removing `search` rather than by listing fields, so a filter added
to `momentsQuery` later is covered without touching it — put any new rule
there, not in a feature-local check.

Selecting a moment keeps the list's scroll natively: `/timeline` and
`/timeline/$momentId` both render `Workspace`, which React reconciles rather
than remounts. Arriving back from a *sibling* route — Journals, a Library
section — does remount the pane, and `usePaneScrollRestoration` is what
returns it to where the reader left it. The same hook covers the Calendar and
Media panes, which the `?view=` switch mounts in the same column.

