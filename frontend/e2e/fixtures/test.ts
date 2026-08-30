import { test as base, expect } from "@playwright/test";
import type { Client } from "@/api/generated/client";
import { workerEmail, workerPassword } from "../env";
import { createJournivClient, deleteAccount, registerAndLogin } from "./api";
import { SESSION_STORAGE_KEY, type JournivWorkerUser } from "./auth";
import { DataFactory } from "./data";
import { buildInitScript, type ThemeMode } from "./determinism";

interface Options {
  /** `"user"` (the default) starts the test already signed in as the worker's
   *  account. `"none"` gives an anonymous browser — use it for the login,
   *  signup and route-guard specs, and nowhere else. */
  session: "user" | "none";
  /** Which theme the app boots in. Pinned so no test inherits the machine's
   *  `prefers-color-scheme`. */
  theme: ThemeMode;
}

interface Fixtures {
  /** A backend client authenticated as the worker's account. */
  api: Client;
  /** Creates prerequisite journals, moments and tags over the API. */
  data: DataFactory;
}

interface WorkerFixtures {
  /** One throwaway account per worker, registered before the worker's first
   *  test and deleted after its last. */
  journivUser: JournivWorkerUser;
}

/** The single entry point for every Playwright spec in this repo.
 *
 *      import { expect, test } from "../fixtures/test";
 *
 *  Do not import `@playwright/test` directly in a spec, and do not build a
 *  second way to sign in. If a spec needs something this file does not provide,
 *  extend this file.
 */
export const test = base.extend<Options & Fixtures, WorkerFixtures>({
  session: ["user", { option: true }],
  theme: ["light", { option: true }],

  journivUser: [
    // Playwright derives a fixture's dependencies by parsing this
    // destructuring pattern and rejects any first argument that is not one, so
    // `{}` is how a fixture declares that it depends on nothing.
    // biome-ignore lint/correctness/noEmptyPattern: required by Playwright's fixture API
    async ({}, use, workerInfo) => {
      const credentials = {
        name: `E2E Worker ${workerInfo.workerIndex}`,
        email: workerEmail(workerInfo.workerIndex),
        password: workerPassword(workerInfo.workerIndex),
      };
      const tokens = await registerAndLogin(credentials);

      await use({ ...credentials, ...tokens });

      // Deleting the account cascades to every journal, entry, media file, tag,
      // mood log and goal it owns — so this one call is the entire cleanup.
      // An interrupted run skips it; find the leftovers by their `e2e-` email prefix.
      await deleteAccount(tokens.accessToken);
    },
    { scope: "worker" },
  ],

  // Overriding `context` (rather than using `storageState`) is not a style
  // choice: Journiv keeps its tokens in sessionStorage, and Playwright's
  // storageState only persists cookies and localStorage. An init script is the
  // only way to have the app already signed in when it boots.
  //
  // Note the worker account is created even for `session: "none"` — the fixture
  // is requested unconditionally here. One extra registration per worker is a
  // fair price for there being exactly one way to get an account.
  context: async ({ context, session, theme, journivUser }, use) => {
    await context.addInitScript(
      buildInitScript({
        theme,
        sessionKey: SESSION_STORAGE_KEY,
        session:
          session === "none"
            ? null
            : {
                version: 1,
                accessToken: journivUser.accessToken,
                refreshToken: journivUser.refreshToken,
              },
      }),
    );
    await use(context);
  },

  api: async ({ journivUser }, use) => {
    await use(createJournivClient(journivUser.accessToken));
  },

  data: async ({ api }, use, testInfo) => {
    // Titles are prefixed with the test's own id so a failure screenshot says
    // which test produced the row, and two tests in one worker cannot collide.
    await use(new DataFactory(api, `e2e-${testInfo.testId}`));
  },
});

export { expect };
