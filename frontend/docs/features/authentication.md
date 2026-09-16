# Authentication feature contract

Authentication lives outside the shell on /login, /signup, and /oidc-finish.
It uses one stock Card on the muted canvas; no navigation, PageBar, or Settings
presentation leaks into these routes.

Login has a generic sign-in failure message and a validated same-origin returnTo
so an expired session returns the reader to its Moment. Signup uses the same
safe return destination, validates required values/email/confirmation only,
registers then signs in through the existing session abstraction, and never
encourages duplicate registration after partial success.

Both routes read instance config. Do not show signup until config permits it;
configuration failure is retryable and fails closed. Password signup accepts any
non-empty password because the self-hosted backend does. OIDC can be mixed mode
or OIDC-only. Its normal browser navigation stores returnTo, and oidc-finish
exchanges the one-time ticket exactly once before replacing the route.

Do not expose raw backend detail, provider identity assumptions, or automatic
provisioning promises. Use generic single-sign-on wording. At compact widths,
top-align and tighten the Card for keyboard usability without changing its
hierarchy.

## Session model

`src/api/auth/session.ts` owns two credentials with different lifetimes and
storage rules:

| Credential          | Lifetime | Lives in                                | JS-readable             |
| ------------------- | -------- | --------------------------------------- | ----------------------- |
| Access token (JWT)  | 15 min   | a module-level variable                 | no — dies with the page |
| Refresh token (JWT) | 7 days   | the `journiv_refresh` `HttpOnly` cookie | no                      |

Nothing durable is ever written to `localStorage` or `sessionStorage`. The one
thing persisted is a credential-free **hint** (`journiv.session-hint.v1`: user
id + timestamp) that lets the app boot into the shell, rather than flashing
`/login`, while the cookie-based restore is in flight.

**Boot restore.** `main.tsx` calls `sessionStore.restore()` and awaits it
before the first render — the router's route guard
(`src/app/router/index.tsx`) reads `sessionStore.getAccessToken()`
synchronously and needs no async work of its own. `restore()` posts to
`/api/v1/auth/refresh` with `credentials: "include"` and no body, bounded by a
5s timeout (`RESTORE_TIMEOUT_MS`); success stores the new access token, a 401/403
clears the hint, and a network error or timeout leaves the hint untouched and
reports `"offline"` without waiting — an unreachable server is not a "no". This
matters for a self-hosted app: the server is often LAN-reachable even when
`navigator.onLine` reports false. `attemptRefresh()` is single-flight, shared
by boot restore, the runtime 401 retry in `src/api/client/config.ts`, and any
future `online`-event retry, so they can never race each other.

**Credentialed API origins must be safe.** The shipped topology is same-origin:
FastAPI serves both the frontend and API. An explicit cross-origin
`VITE_API_BASE_URL` is allowed only over HTTPS or on a loopback address because
session restore sends the refresh cookie with `credentials: "include"`.
Same-origin LAN HTTP remains available only when the backend is started with
the explicit `ALLOW_INSECURE_COOKIE_AUTH_OVER_HTTP=true` opt-in.

**Logging out when the cookie cannot be deleted.** Only the server can clear
an `HttpOnly` cookie, via `Set-Cookie` on a response — a page cannot delete it
itself. `signOut()` therefore writes a local tombstone
(`journiv.logout-pending.v1`) _before_ attempting the network call: clear
in-memory state first, attempt `POST /api/v1/auth/logout`, and only remove the
tombstone on success. `restore()` checks the tombstone first and returns
`"unauthenticated"` immediately with no network request while it exists,
additionally firing one best-effort retry of the logout call. This is what
stops a logout that happened while offline from being silently undone by a
later `restore()` that still finds a valid cookie. `POST /auth/logout` is
deliberately callable without a valid access token (backend
`app/api/v1/endpoints/auth.py`) — its only effect is idempotently clearing the
cookie, never anything else — which is exactly what the offline retry needs.
