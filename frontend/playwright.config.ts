import { defineConfig } from "@playwright/test";
import { APP_PORT, BASE_URL, IS_CI, SKIP_WEB_SERVER } from "./e2e/env";
import { VIEWPORTS } from "./e2e/viewports";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  // A stray `test.only` locally is a debugging aid; in CI it silently drops
  // coverage, so it fails the run instead.
  forbidOnly: IS_CI,
  // No retries locally: a flaky test should be visibly flaky while you are
  // looking at it. In CI, two retries absorb infrastructure noise.
  retries: IS_CI ? 2 : 0,
  // Every worker shares one backend, so CI stays deliberately narrow.
  workers: IS_CI ? 2 : undefined,
  reporter: IS_CI
    ? [["github"], ["html", { open: "never" }], ["list"]]
    : [["html", { open: "never" }], ["list"]],
  outputDir: "test-results",
  globalSetup: "./e2e/global-setup.ts",
  // Baselines live beside the specs rather than in `test-results/`, which is
  // gitignored. No baselines are committed yet — see e2e/README.md.
  snapshotPathTemplate:
    "{testDir}/__screenshots__/{testFilePath}/{arg}-{projectName}{ext}",

  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    // A journalling app renders dates on nearly every surface, and CI runs in
    // UTC while developers do not. Pinning both is what stops a date assertion
    // from depending on who ran it.
    timezoneId: "America/Los_Angeles",
    locale: "en-US",
  },

  projects: [
    {
      name: "chromium",
      use: {
        browserName: "chromium",
        // Specs needing another width call `test.use({ viewport: VIEWPORTS.mobile })`.
        viewport: VIEWPORTS.desktop,
      },
    },
  ],

  webServer: SKIP_WEB_SERVER
    ? undefined
    : {
        // The port is passed explicitly because vite.config.ts leaves
        // `server.port` undefined; 5199 is the project's existing convention.
        // `--host 127.0.0.1` is not redundant: Vite's default binding resolves
        // to ::1 on macOS, which leaves the IPv4 address in `baseURL`
        // unreachable and the webServer wait timing out with no explanation.
        command: `npx vite --port ${APP_PORT} --strictPort --host 127.0.0.1`,
        url: BASE_URL,
        // Locally, reuse whatever `npm run dev` you already have open. In CI
        // there is nothing to reuse and a stale server would be a lie.
        reuseExistingServer: !IS_CI,
        timeout: 120_000,
        stdout: "ignore",
        stderr: "pipe",
      },
});
