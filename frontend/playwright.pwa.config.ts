import { defineConfig } from "@playwright/test";
import { IS_CI, SKIP_WEB_SERVER } from "./e2e/env";
import { VIEWPORTS } from "./e2e/viewports";

const PWA_PORT = 5198;
const PWA_BASE_URL = `http://127.0.0.1:${PWA_PORT}`;

/**
 * Service-worker and offline behaviour need a real build: devOptions.enabled
 * is false in vite.config.ts, so the plain Vite dev server this project's
 * other Playwright config uses never registers a worker at all
 * (docs/features/pwa.md). This config runs the same specs' fixtures against
 * `vite preview` instead, which serves the production `dist/` output the
 * built worker actually controls.
 */
export default defineConfig({
  testDir: "./e2e/pwa",
  fullyParallel: true,
  forbidOnly: IS_CI,
  retries: IS_CI ? 2 : 0,
  // The service worker is shared browser-profile state; running several
  // workers against the same preview server risks one test's precache or
  // Cache Storage bleeding into another's assertions.
  workers: 1,
  reporter: IS_CI
    ? [["github"], ["html", { open: "never" }], ["list"]]
    : [["html", { open: "never" }], ["list"]],
  outputDir: "test-results-pwa",
  globalSetup: "./e2e/global-setup.ts",

  use: {
    baseURL: PWA_BASE_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    timezoneId: "America/Los_Angeles",
    locale: "en-US",
  },

  projects: [
    {
      name: "chromium",
      use: { browserName: "chromium", viewport: VIEWPORTS.desktop },
    },
  ],

  webServer: SKIP_WEB_SERVER
    ? undefined
    : {
        command: `npm run build && npx vite preview --port ${PWA_PORT} --strictPort --host 127.0.0.1`,
        url: PWA_BASE_URL,
        reuseExistingServer: !IS_CI,
        // A full production build first, then preview boot -- generously
        // over the 120s the dev-server config uses.
        timeout: 300_000,
        stdout: "ignore",
        stderr: "pipe",
      },
});
