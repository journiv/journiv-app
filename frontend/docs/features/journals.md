# Journals feature contract

Journal browsing belongs in the shell; management belongs on /journals. Read
the global design contract for adaptive overlays and chrome composition.

The sidebar shows active journals in canonical order, capped by SIDEBAR_MAX,
then All journals. It never lists archived journals. A journal mark is its own
colour dot or curated icon in that colour.

The management route is a list-pane surface with one scroll owner and one
primary New journal action. Active journals use a divided management panel;
archived journals are a counted, collapsed details group. Loading uses row
skeletons and empty/error use StatusView.

Ordering is the backend order: favourite first, then position, then creation.
The shared journal-order helper is canonical. Move actions swap only within the
same favourite group and persist that group through the reorder endpoint.

Create and edit use AppAdaptiveDialog with caller-owned form state, validated
title, description, curated colour and icon choices, one Create or Save primary,
and a human alert on failure.

Deletion is a typed-title AppAdaptiveDialog because it includes the reversible
Archive alternative. DELETE /journals/{id} deletes Entries' narrative while
parent Moments survive as quick logs; state that effect plainly. Do not replace
the flow with simple confirmation or an invented Undo.

