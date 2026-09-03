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

