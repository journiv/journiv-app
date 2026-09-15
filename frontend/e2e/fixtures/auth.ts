/** The `HttpOnly` cookie the app restores a session from.
 *
 *  Mirrors the private `REFRESH_COOKIE_NAME` in
 *  `journiv-backend/app/core/auth_cookies.py`. Page JS can never read or write
 *  an `HttpOnly` cookie — that is the whole point of the session model
 *  (`docs/features/authentication.md`) — so the fixtures inject it directly
 *  into the browser context via `context.addCookies()`, which is a Playwright
 *  API, not page script, and is therefore not subject to that restriction.
 *  `e2e/smoke/auth.spec.ts` carries a test whose only job is to prove an
 *  injected session actually signs the app in. If that test fails after a
 *  refactor, this constant is the first thing to check.
 */
export const REFRESH_COOKIE_NAME = "journiv_refresh";
export const REFRESH_COOKIE_PATH = "/api/v1/auth";

export interface JournivWorkerUser {
  name: string;
  email: string;
  password: string;
  accessToken: string;
  refreshToken: string;
  userId: string;
}
