# Cross-cutting known gaps

Read this only when the task intersects one of these cross-frontend issues.
Feature-specific gaps live in their own feature or domain contracts.

## Release blocker: Flutter inline video compatibility

Flutter Quill treats an inline video as a block embed and adds a newline on each
load/save cycle. Reopening and saving a document containing video permanently
adds blank lines. Image and audio embeds are stable.

The web frontend can ship inline video only with the targeted Flutter
normalization that collapses a video followed by multiple newlines to one on
load. The Flutter compatibility test intentionally fails loudly when upstream
behaviour changes. Do not hide this by changing web rendering or accepting
document corruption as a known issue.

## E2E infrastructure mismatch

Several existing Playwright failures are fixture/spec contradictions rather than
product design failures: settings persistence assertions conflict with the
determinism fixture resetting theme and personalization on every navigation;
the focus-dialog and two media-upload failures were also observed before the
Minimal Neutral pass. Fix the relevant test or fixture, not product behaviour,
when working on that area.

## PWA offline follow-ups

- **Inline signed media URLs persisted with a cached Moment.** The offline
  read cache (`src/app/offline/`) persists `["moment", id]` queries whose
  Delta content carries signed, short-lived media URLs baked in by the
  backend. There is no allowlist rule that strips them; the reader instead
  falls back to a placeholder when a persisted URL has expired. The clean fix
  is canonicalising stored Deltas back to durable media ids the way
  `src/features/editor/draftCanonical.ts` already does for drafts — not
  attempted here because it would couple the offline cache to the editor's
  canonicalisation module and change the shape the reader expects to hydrate.
- **Offline readers still expose some mutation controls.**
  `docs/features/pwa.md`'s offline-restricted route guard now redirects every
  mutation-oriented route (new/edit, Settings, Import, Library management, and
  so on) to a cached reading destination, and the sidebar disables its primary
  "New entry" action. Controls embedded in an otherwise read-only route still
  need the same treatment — notably the reader's Edit/Delete menu. Edit is
  safely redirected by the route guard, while Delete still attempts a real
  request that fails honestly offline. Threading a shared disabled state and
  reason into those remaining controls is a follow-up.
- **The reader's inline media-placeholder path was not directly modified.**
  The offline read cache relies on the reader's *existing* by-media-id
  fallback (the one a live re-signed URL already reloads in place,
  `docs/features/reader.md`) to also cover an *expired* signed URL served
  from the offline cache. This was not independently re-verified against a
  persisted, offline-served entry — only against the live re-sign path it
  already had. Confirm this on a real device per the manual test matrix
  before relying on it.
