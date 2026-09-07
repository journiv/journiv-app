# Reader feature contract

Read this with [the Moments domain contract](../domain/moments.md) for Reader
work, including signed media and deleting an Entry.

## Reading surface

Reader has one scroll owner and a compact PageBar with Back, journal badge, and
Edit or Write. Its centred column is bounded by the reader measure. EntryHeader
renders the display-only date, title, and reader metadata; QuillReader renders
prose without raw HTML. People and tags sit above the final rule.

When a Moment has `prompt_id`, the Reader resolves that prompt and shows its
text as a read-only "Written from a prompt" banner below the header. A missing
or deleted prompt is quiet supplementary context; it never blocks the Moment.

Malformed stored content falls back visibly to plain text. An untitled Moment
uses its date as h1. Reader does not edit metadata.

## Entry actions

Reader PageBar actions are `Edit` (or `Write`) and, whenever the Moment has an
Entry, an `Entry actions` overflow menu built from the shared `AppAdaptiveMenu`
(anchored menu on regular widths, bottom action sheet when compact). The menu
holds:

- **Download PDF** — downloads the Entry as a PDF (`GET /entries/{entry_id}/pdf`)
  and starts a browser download. Present only when the Moment has an actual
  Entry. While the request is in flight the item is disabled; the menu closes on
  select, so pending state is carried by a transient toast. The browser starting
  the download is the only success signal. Failure surfaces as a transient error
  toast with a Retry action that re-runs the same download and keeps the
  in-flight guard.
- **Delete entry…** — separated below Download and styled destructive. Opens the
  existing `AppConfirmDialog` confirmation (open state owned by the reader); the
  dialog stays open with a human error on failure.

DELETE /entries/{entry_id} deletes writing, not Moment context. Refetch the
Moment after success; it becomes the matching quick-log kind. If the backend
pruned an otherwise empty Moment and refetch is 404, return to the same list
mode, search, and scope. Invalidate affected moment lists, Calendar, media
library, journal count, and tag previews. There is no Undo because the API has
no restore contract.

## Media

Inline media stays in prose. The gallery — `components/journiv/MomentMediaGallery`
(`variant="content"`, the default) with `useMomentMedia` — shows only attached
media not referenced by prose. The same component in `variant="tray"` is the
Editor's attachment tray (docs/features/editor.md); the Reader never uses that.
The moment response supplies thumbnails and media_count; the gallery fetches the
detailed moment-media endpoint only when media_count is positive. The list wins
if its result disagrees with the denormalized count. Reader passes no
`renderItemAction`, so the gallery is display-only there.

The backend hydrates stored media ids to signed relative URLs for inline Delta
content. Render that URL, but never write it back in place of the durable id.
Only same-origin relative sources are rendered; unsafe or unsupported embeds
fall back visibly to plain text.

Where media is content, show it uncropped: one column, intrinsic ratio (3:2
fallback), object-fit contain, bounded height, and reserved layout space.
Thumbnails may use object-fit cover because they navigate to the full Moment.

### Full-screen viewer

Activating a gallery image, or an inline prose image, opens the moment's media
in a full-screen viewer (`components/journiv/media/MediaViewer`, backed by
`yet-another-react-lightbox` and lazy-loaded). Gallery images are real buttons;
inline prose images (rendered by Quill) are given `role="button"` + a tab stop
and activate on click, Enter or Space. A gallery `<video>` keeps its native
controls and gets a small corner "expand" control instead; an inline prose
`<video>` has no expand affordance. Feature code speaks `MediaViewerItem`
(`momentMediaToViewerItems`), never the library's slide types or a raw API
response.

The collection is **ready media only**: `image` and `video`, upload complete,
signed URL present, inline and attached, in document order. Audio, `unknown`,
and anything still processing or failed stay in the Reader gallery and never
become a slide position. A slide that was ready but whose URL breaks at runtime
keeps its position and shows an in-place error with a retry (`brokenIds` on the
viewer), so the slide count never shifts mid-session.

The open item is `?media=<mediaId>` on the reader route. Opening pushes one
history entry; prev/next replace it; the close control steps back over the
pushed entry (or just drops the param when the viewer was deep-linked). A
`?media=` id is stripped from the URL only once the moment media query has
*definitively* resolved without it — never while it is still loading, so a
valid deep link survives a temporarily empty list. Load failures route through
`useMomentMedia.reportLoadFailure` (the capture-phase handler also covers the
Video plugin's `<source>`/`<video>`, which carry no `onError`); the viewer is
keyed by media id, so a re-signed URL reloads the slide in place.

The library owns its own modal semantics — `role="dialog"`, `aria-modal`,
accessible name from `labels.Lightbox`, sibling `inert`, focus-in on open and
focus-restore on close. `controller.aria` is a deprecated no-op in 3.32 and is
not set. `carousel.finite` is deliberately `true` (no wrap past the last item).

- alt_text is only image alt text, never a visible caption.
- pending or processing media has a Processing frame; failed media has an
  unavailable frame.
- image, video and audio render inline; a `media_type` of `unknown` renders as a
  plain "Attachment" frame rather than vanishing.
- A failed gallery request is an inline retry notice, not a pane-filling error.
- A successful empty list with nonzero media_count is quiet stale data.
- One failed item never hides successful items.

Signed URLs are refreshed once proactively near expiry and once reactively on
image load failure. A second failure is genuinely broken; never loop. Inline
media needs one entry refetch because its URLs live in the document.

## Known gaps

- PDF export (backend follow-up): `GET /entries/{entry_id}/pdf`
  does not declare its binary `application/pdf` response, so the generated client
  types the body as `unknown`; the client wrapper parses the Blob defensively as
  a workaround. The endpoint should declare the response properly.
- PDF export (backend follow-up): the owned endpoint renders
  WeasyPrint synchronously inside an `async` handler, blocking the event loop for
  the whole render. Offload the render (thread pool or worker).
- Reader PageBar can be visually bare for journal-less quick logs.
- The full-screen viewer is wired on the Reader only. The Media Library grid
  still navigates to the moment; wiring it to open the viewer in place needs a
  by-id media lookup for items outside the loaded page (`/api/v1/media/{id}/info`
  returns an untyped body, so there is no contract for it yet).
- Legacy absolute third-party media URLs intentionally fall back to plain text.
- Existing media alt text cannot be edited without a backend update endpoint.
