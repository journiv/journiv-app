# Reader feature contract

Read this with [the Moments domain contract](../domain/moments.md) for Reader
work, including signed media and deleting an Entry.

## Reading surface

Reader has one scroll owner and a compact PageBar with Back, journal badge, and
Edit or Write. Its centred column is bounded by the reader measure. EntryHeader
renders the display-only date, title, and reader metadata; QuillReader renders
prose without raw HTML. People and tags sit above the final rule.

Malformed stored content falls back visibly to plain text. An untitled Moment
uses its date as h1. Reader does not edit metadata.

## Delete Entry

The reader shows one direct ghost delete icon immediately before Edit whenever
the Moment has an Entry. Confirm with AppConfirmDialog and leave the surface
open with a human error on failure.

DELETE /entries/{entry_id} deletes writing, not Moment context. Refetch the
Moment after success; it becomes the matching quick-log kind. If the backend
pruned an otherwise empty Moment and refetch is 404, return to the same list
mode, search, and scope. Invalidate affected moment lists, Calendar, media
library, journal count, and tag previews. There is no Undo because the API has
no restore contract.

## Media

Inline media stays in prose. EntryMedia is a gallery only for attached media not
referenced by prose. The moment response supplies thumbnails and media_count;
the gallery fetches the detailed moment-media endpoint only when media_count is
positive. The list wins if its result disagrees with the denormalized count.

The backend hydrates stored media ids to signed relative URLs for inline Delta
content. Render that URL, but never write it back in place of the durable id.
Only same-origin relative sources are rendered; unsafe or unsupported embeds
fall back visibly to plain text.

Where media is content, show it uncropped: one column, intrinsic ratio (3:2
fallback), object-fit contain, bounded height, and reserved layout space.
Thumbnails may use object-fit cover because they navigate to the full Moment.
There is no full-screen viewer yet.

- alt_text is only image alt text, never a visible caption.
- pending or processing media has a Processing frame; failed media has an
  unavailable frame.
- A failed gallery request is an inline retry notice, not a pane-filling error.
- A successful empty list with nonzero media_count is quiet stale data.
- One failed item never hides successful items.

Signed URLs are refreshed once proactively near expiry and once reactively on
image load failure. A second failure is genuinely broken; never loop. Inline
media needs one entry refetch because its URLs live in the document.

## Known gaps

- Reader PageBar can be visually bare for journal-less quick logs.
- No full-size media viewer; gallery images must stay uncropped until one exists.
- Legacy absolute third-party media URLs intentionally fall back to plain text.
- Existing media alt text cannot be edited without a backend update endpoint.

