# Editor feature contract

Read this with [the Moments domain contract](../domain/moments.md) for Editor
work. It owns editing behaviour, drafts, attachments, metadata writes, and the
Quill boundary.

## Editing surface

Reading and writing use the same EntryHeader and prose styles. PageBar has a
journal selector when needed, save status, one Cancel, and one Done primary.
The title is a growing textarea with an optional-title invitation. Toolbar
controls keep a 30px visual size and 44px targets; pointer-down prevention on
toolbar buttons preserves the editor selection and must remain.

The editor date is EntryDateControl: a popover Calendar with native month/year
selection and time field. A new Entry uses browser timezone and sends UTC plus
that zone. Editing a Moment preserves its recorded zone and interprets picked
wall time in that zone. Date changes on an existing Moment persist immediately,
refresh ordering, and do not mark prose dirty. There is no arbitrary timezone
selector. Date conversion helpers own DST behaviour; never persist the
browser-local Date serialization.

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

Moment details is one popover in the toolbar. It lazily ensures a Moment then
writes mood, location, weather, people, and tags through their actual
operations. Header metadata and foot chips refresh after success. Existing
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
and media blots are the only Quill-aware styling/code boundary. Reader and
Editor share the same accepted-document guard. Every media kind accepted by the
guard must be in EDITOR_FORMATS; a test protects this coupling.

## Known gaps

- Toolbar overflow below roughly 700px needs a More popover, not smaller targets.
- Media picker/caret/keyboard/slow-network behaviour lacks real-device coverage.
- Conflict resolution is refuse-or-overwrite; no merge exists.
- Recovering the same local draft in two tabs can race on draft-Moment finalization.
- Logged date has no arbitrary timezone selector.
- Immich has no asset search, type/date/album filters, duration/dimension data,
  or in-picker preview.
- Immich people sync_enabled is import-time only; suggestions are synchronous
  and unexplained when no eligible person appears; normalized people lack an
  appearance count.

