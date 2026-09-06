# Settings feature contract

Settings is a secondary contextual activity over the running journal, not a
third persistent pane. Read the engineering contract for route metadata and
the design contract for overlay rules.

## Routes and navigation

Settings routes are real. They declare the existing settings route metadata;
AppShell mounts SettingsModal over the ordinary background workspace. Direct
links open the requested section. Add a section by registering its route,
adding settings-nav data, and implementing the page; do not add modal-local
state or pathname parsing.

Above 1100px Settings is a centred two-column routed modal. At or below 1100px
it is a full-screen routed flow: the index lists sections and a section has a
back control. The one matchMedia read at index navigation is deliberate,
one-shot route selection; all other presentation is CSS.

Opening from the app records the origin href. Close, escape, and backdrop return
there, or /timeline after a deep link. Section changes and dismissal share the
existing unsaved-changes guard. Successful saves do not close Settings. Never
store password or API-key fields in drafts or persistent client storage.

## Presentation

The modal is a real overlay. It has one close control, restrained navigation,
and a muted canvas with stock Cards for coherent sections. Use Card header,
content, and footer; a section action belongs in its Card footer, not on the
canvas. Forms have a readable max width, while data tables may take the content
pane and choose their own container-query layout.

Settings rows use Item and Field. Selection is accent plus brand rail and
aria-current. Do not stack large modals: edit in place, reserving small
confirmation only for actual confirmation.

## Implemented sections

- Profile uses current-user and user-settings queries for display name and
  timezone; email and avatar remain read-only until API support exists.
- Security is capability-aware: local accounts can change password, OIDC users
  see provider guidance. Every account type can permanently delete itself via
  `DELETE /users/me`; deletion requires the exact typed `DELETE` confirmation,
  clears the local session only after a success response, then returns to login.
  An uncertain request stays open with an honest retry/sign-in message because
  a failed response is not proof that deletion did not complete.
- Appearance writes account theme defaults, time format, and first day together.
  It does not silently replace the existing per-device sidebar theme override.
- Integrations is catalogue then detail, both routed. The frontend registry
  names providers because the backend has no provider-list endpoint. Immich
  reads config and status, connects with import mode, supports sync/disconnect,
  keeps secrets ephemeral, and invalidates status after mutation.
- Import/export starts explicit background jobs, polls only while active, shows
  progress and human failure states, and never auto-downloads. Each section
  lists its recent jobs newest-first with keyset pagination (`items` plus
  `next_cursor_created_at` / `next_cursor_id`, mirroring moments); a **Load
  older jobs** control fetches the next page. The legacy Flutter client still
  receives its offset-paginated bare array unless it opts into `format=page`.
  History lives in the content pane's own Table, so a job resumes after a reload
  or a section switch and a finished export re-downloads through a fresh signed
  URL. Every export row opens a details overlay with its scope, timing, archive
  size, progress, media setting, warnings, and all recorded content totals; the
  shared adaptive overlay presents as a dialog on regular screens and a bottom
  sheet on compact screens. A settled job can be deleted (`DELETE`, confirmed). A `pending` or
  `running` job can be cancelled (`POST /export/{id}/cancel`, `POST
  /import/{id}/cancel`, confirmed); cancellation is cooperative — the worker
  stops at its next progress checkpoint and the job moves to `cancelled`, which
  reads as a neutral end state, not a failure. Export scope is full or a chosen
  set of journals (archived included, marked). The completed panel reads the
  job's `result_data` — export item/size/missing-media counts, import
  created-vs-skipped totals with the warning list behind a disclosure. The
  archive picker is the shared `Dropzone` primitive; the source row carries a
  one-line "how to produce this export" hint per supported source (`journiv`,
  `dayone`, `daylio`).
- Support reads available public version/config/license information. Administration
  owns version checking and Plus license registration: it shows cached update
  state, controls automatic checks, permits a rate-limit-aware manual check,
  and lets an administrator register a license. License reset/unbinding is a
  separate destructive lifecycle flow and is intentionally not exposed here.
- Admin Users is role-gated before its list query. It fetches the documented
  offset pages, searches/pages locally, sends only changed fields, respects
  last-admin protections, and refreshes user/session queries when needed.

## Known gaps

- Integration pause/resume, test-connection, provider metadata, and provider
  icons have no backend contract.
- Admin user pagination exposes neither a total nor continuation token, so the
  complete collection is fetched before local search/paging.
