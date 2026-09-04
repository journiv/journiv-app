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
  progress and human failure states, and never auto-downloads.
- Support reads available public version/config/license information.
- Admin Users is role-gated before its list query. It fetches the documented
  offset pages, searches/pages locally, sends only changed fields, respects
  last-admin protections, and refreshes user/session queries when needed.

## Known gaps

- Integration pause/resume, test-connection, provider metadata, and provider
  icons have no backend contract.
- Admin user pagination exposes neither a total nor continuation token, so the
  complete collection is fetched before local search/paging.
- Version administration and license registration/reset remain intentionally
  undesigned; do not render dead links.
