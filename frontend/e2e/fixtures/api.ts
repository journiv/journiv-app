import { createClient } from "@/api/generated/client/client.gen";
import type { Client } from "@/api/generated/client";
import {
  deleteCurrentUserApiV1UsersMeDelete,
  loginApiV1AuthLoginPost,
  registerApiV1AuthRegisterPost,
} from "@/api/generated";
import { API_URL } from "../env";

/** A backend client for test setup.
 *
 *  This deliberately builds on `src/api/generated` — the same committed client
 *  the app uses — rather than hand-rolled `fetch` calls. Setup code is then
 *  type-checked against `openapi/openapi.json`, so a backend contract change
 *  breaks the fixtures at `npm run typecheck` instead of at 3am in a flaky
 *  assertion.
 *
 *  It does NOT use `src/api/client/api.ts`: that façade reads `import.meta.env`
 *  and `sessionStorage`, neither of which exists in Playwright's Node process.
 */
export function createJournivClient(accessToken?: string): Client {
  return createClient({
    // The generated operations carry `/api/v1/...` in their own `url`, so the
    // base is the bare origin.
    baseUrl: API_URL,
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
  });
}

export interface JournivCredentials {
  name: string;
  email: string;
  password: string;
}

export interface JournivTokens {
  accessToken: string;
  refreshToken: string;
}

/** Turns the two backend policies that break account creation into errors that
 *  say what to do, instead of a bare 4xx from deep inside a fixture. */
function explainAuthFailure(
  status: number | undefined,
  action: string,
): string {
  if (status === 429)
    return (
      `${action} was rate limited (HTTP 429).\n\n` +
      `  The backend limits register to 3/minute and login to 5/minute, which a\n` +
      `  parallel Playwright run exceeds immediately. Start the backend with\n` +
      `  RATE_LIMITING_ENABLED=false — the docker-compose.override.ci.yml overlay\n` +
      `  already does this.`
    );
  if (status === 403)
    return (
      `${action} was forbidden (HTTP 403).\n\n` +
      `  The instance is refusing new password accounts. Check DISABLE_SIGNUP=false\n` +
      `  and OIDC_ONLY=false on the backend.`
    );
  return `${action} failed with HTTP ${status ?? "unknown"}.`;
}

/** Registers an account and returns tokens for it. Used once per worker. */
export async function registerAndLogin(
  credentials: JournivCredentials,
): Promise<JournivTokens> {
  const client = createJournivClient();

  const registered = await registerApiV1AuthRegisterPost({
    client,
    body: credentials,
  });
  if (registered.error !== undefined)
    throw new Error(
      explainAuthFailure(
        registered.response?.status,
        "Registering the E2E account",
      ),
    );

  const loggedIn = await loginApiV1AuthLoginPost({
    client,
    body: { email: credentials.email, password: credentials.password },
  });
  if (loggedIn.error !== undefined || !loggedIn.data)
    throw new Error(
      explainAuthFailure(
        loggedIn.response?.status,
        "Signing in the E2E account",
      ),
    );

  return {
    accessToken: loggedIn.data.access_token,
    refreshToken: loggedIn.data.refresh_token,
  };
}

/** Deletes the account and, by database cascade, everything it owns — journals,
 *  entries, media, tags, mood logs, prompts, settings, streaks. This is the
 *  whole cleanup story; there is no per-resource teardown to keep in sync. */
export async function deleteAccount(accessToken: string): Promise<void> {
  const result = await deleteCurrentUserApiV1UsersMeDelete({
    client: createJournivClient(accessToken),
  });
  if (result.error !== undefined)
    // Teardown must never mask a real test failure, so this warns rather than
    // throws. The `e2e-` email prefix makes the leftover account findable.
    console.warn(
      `[e2e] Could not delete the worker account (HTTP ${result.response?.status}). ` +
        `Clean it up by hand if it accumulates.`,
    );
}
