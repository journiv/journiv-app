# Journals feature contract

Journal browsing belongs in the shell; management belongs on /journals. Read
the global design contract for adaptive overlays and chrome composition.

The sidebar shows active journals in canonical order, capped by SIDEBAR_MAX,
then All journals. It never lists archived journals. A journal mark is its own
colour dot or curated icon in that colour.

The management route is a list-pane surface with one scroll owner and one
primary New journal action. Active journals use a divided management panel;
archived journals are a counted, collapsed details group. While the route's own
chunk is loading, its Suspense fallback is the shared `ListPaneFallback`
(`src/components/journiv/RouteFallback.tsx`), never a centred spinner; once the
chunk and the journals query resolve, loading uses row skeletons and
empty/error use StatusView. Back into the list restores its scroll position
via `usePaneScrollRestoration`.

Ordering is the backend order: favourite first, then position, then creation.
The shared journal-order helper is canonical. Move actions swap only within the
same favourite group and persist that group through the reorder endpoint.

Create and edit use AppAdaptiveDialog with caller-owned form state, validated
title, description, entry template, curated colour and icon choices, one Create
or Save primary, and a human alert on failure.

## Entry template

A journal may carry `entry_template`: optional plain text (at most 5,000
characters), typically a few fixed questions, one per line. Every NEW entry
written in that journal opens with it in the body (see the editor contract).
It is a starting point, not a link: once seeded it is ordinary prose, so
editing or removing a template never changes entries already written. Blank
text means no template; the backend normalises it to `null`, and `PUT` with
`null` or blank text removes it while omitting the field leaves it unchanged.
Templates travel with journal export and import.

Deletion is a typed-title AppAdaptiveDialog because it includes the reversible
Archive alternative. DELETE /journals/{id} deletes Entries' narrative while
parent Moments survive as quick logs; state that effect plainly. Do not replace
the flow with simple confirmation or an invented Undo.

