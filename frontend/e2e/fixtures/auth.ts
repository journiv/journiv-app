/** The sessionStorage key the app reads its tokens from.
 *
 *  Mirrors the private `key` in `src/api/auth/session.ts`. It cannot be imported
 *  (the module does not export it) and it cannot be verified at runtime, so
 *  `e2e/smoke/auth.spec.ts` carries a test whose only job is to prove an
 *  injected session actually signs the app in. If that test fails after a
 *  refactor, this constant is the first thing to check.
 */
export const SESSION_STORAGE_KEY = "journiv.session.v1";

export interface JournivWorkerUser {
  name: string;
  email: string;
  password: string;
  accessToken: string;
  refreshToken: string;
}
