import { API_V1, API_URL } from "./env";

/** How to produce a backend this suite can use. Quoted verbatim in every
 *  preflight failure so the fix is in the error, not in a document.
 *
 *  Deliberately NOT the `docker-compose.override.ci.yml` overlay: that file is
 *  written for the image-based `docker-compose.sqlite.yml`, and against the dev
 *  compose it swaps the `./data` bind mount for a named volume — so a developer
 *  running it would find their local data apparently missing. CI uses the
 *  overlay; local dev sets the flag in `.env`, which is the only place the dev
 *  compose reads it from.
 */
const START_BACKEND = `  cd journiv-backend
  echo "RATE_LIMITING_ENABLED=false" >> .env     # once
  docker compose -f docker-compose.dev.sqlite.yml up -d`;

function fail(problem: string, fix: string): never {
  throw new Error(
    `\n\nJourniv E2E preflight failed.\n\n  ${problem}\n\n${fix}\n\n` +
      `  Backend expected at: ${API_URL}\n` +
      `  Override with:      JOURNIV_E2E_API_URL=<origin>\n` +
      `  See:                frontend/e2e/README.md\n`,
  );
}

async function getJson(url: string, what: string): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(url, { signal: AbortSignal.timeout(10_000) });
  } catch (cause) {
    return fail(
      `Could not reach the backend (${what}): ${(cause as Error).message}`,
      `  Start it with:\n\n${START_BACKEND}\n\n` +
        `  RATE_LIMITING_ENABLED=false is required, not optional: the backend\n` +
        `  allows 3 registrations and 5 logins per minute by default, and every\n` +
        `  Playwright worker registers its own account. The dev compose reads\n` +
        `  that flag from journiv-backend/.env only.`,
    );
  }
  if (!response.ok)
    return fail(
      `${what} returned HTTP ${response.status}.`,
      `  The backend is reachable but unhealthy. Check its logs:\n\n` +
        `    docker compose -f docker-compose.dev.sqlite.yml logs app`,
    );
  return response.json();
}

export default async function globalSetup(): Promise<void> {
  await getJson(`${API_V1}/health`, "GET /api/v1/health");

  const config = (await getJson(
    `${API_V1}/instance/config`,
    "GET /api/v1/instance/config",
  )) as { disable_signup?: boolean; oidc_only?: boolean };

  // Every worker registers its own throwaway account over the API. Both of
  // these flags close that door, and the resulting 403 is far less legible
  // than saying so here.
  if (config.disable_signup)
    fail(
      "This instance has sign up disabled (instance/config.disable_signup = true).",
      "  Restart the backend with DISABLE_SIGNUP=false.",
    );
  if (config.oidc_only)
    fail(
      "This instance is OIDC-only (instance/config.oidc_only = true).",
      "  Restart the backend with OIDC_ONLY=false — E2E uses password accounts.",
    );

  // Rate limiting cannot be detected from here: SlowAPI is configured without
  // `headers_enabled`, so a healthy instance and a throttling one look
  // identical until a request is actually refused. The auth fixture turns the
  // resulting 429 into a message naming RATE_LIMITING_ENABLED instead.

  process.env.JOURNIV_E2E_RUN_ID ??= `${Date.now().toString(36)}${Math.random()
    .toString(36)
    .slice(2, 6)}`;
}
