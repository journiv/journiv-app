# Frontend documentation router

Read this after `AGENTS.md`. **Do not recursively read this documentation tree.**
Load only the documents relevant to the task, then inspect the implementation
and nearby tests.

| If the task touches… | Read… |
| --- | --- |
| any UI | [`../DESIGN.md`](../DESIGN.md) |
| Moment classification, metadata, time, locations/map, Calendar, or media list modes | [`domain/moments.md`](domain/moments.md) |
| routing, placement, API/client, query/cache, generated OpenAPI, or unit testing | [`architecture/frontend.md`](architecture/frontend.md) |
| visual references or browser tests | [`../e2e/README.md`](../e2e/README.md) |
| Reader or signed media URLs | [`features/reader.md`](features/reader.md) |
| Editor, drafts, attachments, metadata editing, or Quill | [`features/editor.md`](features/editor.md) |
| Timeline | [`features/timeline.md`](features/timeline.md) and `domain/moments.md` |
| Journals | [`features/journals.md`](features/journals.md) |
| Settings or integrations | [`features/settings.md`](features/settings.md) |
| Library: People, Tags, Goals, Moods, Activities, or Immich people | [`features/library.md`](features/library.md) |
| Insights: writing/mood analytics, streaks, the `/insights` workspace | [`features/insights.md`](features/insights.md) |
| Prompts: the `/library/prompts` library, the editor prompt picker, `prompt_id` | [`features/prompts.md`](features/prompts.md) |
| personalization/theme import | [`features/personalization.md`](features/personalization.md) |
| login, signup, or OIDC | [`features/authentication.md`](features/authentication.md) |
| an unresolved issue | the relevant document's **Known gaps**, then [`known-gaps.md`](known-gaps.md) only if cross-cutting |

## Ownership

| Information | Canonical location |
| --- | --- |
| Global visual/interaction design | `DESIGN.md` |
| Engineering architecture | `architecture/` |
| Shared domain semantics | `domain/` |
| Feature behaviour | `features/` |
| E2E harness rules | [`../e2e/README.md`](../e2e/README.md) |
| Feature-specific gaps | that feature document |
| Cross-cutting blockers | `known-gaps.md` |

Do not add a feature-specific rule to `DESIGN.md`; link to the feature contract
instead. Do not add a document for code that is self-evident and has no durable
contract.
