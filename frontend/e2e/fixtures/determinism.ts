import type { Page } from "@playwright/test";

/** The instant every time-sensitive test pretends it is.
 *
 *  A journal renders dates on nearly every surface — "Today", relative
 *  timestamps, calendar month grids, streaks. Pinning the clock is what stops a
 *  spec from passing all day and failing at midnight, or in a CI region.
 *  Midday deliberately: far from either day boundary in the suite's timezone.
 */
export const FROZEN_NOW = new Date("2026-03-17T12:00:00.000-07:00");

/** Pin `Date.now()` without faking the timer queue.
 *
 *  Prefer this over `page.clock.install()`. `install()` replaces
 *  setTimeout/setInterval as well, which stalls anything that waits on a timer —
 *  React transitions, TanStack Query retries and refetches, the editor's
 *  autosave. `setFixedTime` changes what the app *reads* as now and leaves the
 *  event loop alone, which is what almost every date assertion actually needs.
 *
 *  Reach for `page.clock.install()` only when a test must advance time on
 *  purpose, and say so in a comment when you do.
 */
export async function freezeClock(page: Page, at: Date = FROZEN_NOW) {
  await page.clock.setFixedTime(at);
}

/** Wait for webfonts before measuring or screenshotting anything.
 *
 *  DM Sans and Lora are bundled and self-hosted, so they load fast — but "fast"
 *  is not "already". A screenshot taken mid-swap captures fallback metrics.
 */
export async function fontsReady(page: Page) {
  await page.evaluate(() => document.fonts.ready.then(() => undefined));
}

export type ThemeMode = "light" | "dark";

/** The init script every context runs before the app boots.
 *
 *  Three jobs, all of them about starting from a known appearance:
 *   - pin the theme, so a test never inherits the CI machine's
 *     `prefers-color-scheme`;
 *   - clear personalization, so a stray accent colour or font scale from a
 *     previous run cannot bleed into a comparison (e2e/README.md names this as a
 *     precondition for deterministic capture);
 *   - seed the auth session when there is one.
 *
 *  It runs on every navigation, so the session write is guarded: a token the app
 *  refreshed mid-test must survive the next page load.
 */
export function buildInitScript(options: {
  theme: ThemeMode;
  sessionKey: string;
  session: { version: 1; accessToken: string; refreshToken: string } | null;
}) {
  return `(() => {
    try {
      localStorage.setItem("journiv.theme", ${JSON.stringify(options.theme)});
      localStorage.removeItem("journiv.userTheme");
    } catch {}
    const session = ${JSON.stringify(options.session)};
    if (session) {
      try {
        if (!sessionStorage.getItem(${JSON.stringify(options.sessionKey)})) {
          sessionStorage.setItem(
            ${JSON.stringify(options.sessionKey)},
            JSON.stringify(session),
          );
        }
      } catch {}
    }
  })();`;
}
