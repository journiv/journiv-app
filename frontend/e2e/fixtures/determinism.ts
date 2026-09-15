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
 *  Two jobs, both about starting from a known appearance:
 *   - pin the theme, so a test never inherits the CI machine's
 *     `prefers-color-scheme`;
 *   - clear personalization, so a stray accent colour or font scale from a
 *     previous run cannot bleed into a comparison (e2e/README.md names this as a
 *     precondition for deterministic capture).
 *
 *  It runs on every navigation, so the appearance writes are guarded: an
 *  appearance the test changes must survive the next page load.
 *
 *  The refresh token itself is a separate concern: it lives only in an
 *  `HttpOnly` cookie page script can never read or write, so `test.ts`'s
 *  `context` fixture injects it directly via `context.addCookies()` instead
 *  of through this script (docs/features/authentication.md). The session
 *  *hint* (`journiv.session-hint.v1`) is an ordinary localStorage breadcrumb
 *  though, and a real returning user's browser already carries one from
 *  signing in through the UI -- `sessionHint` here recreates that half of
 *  the state so offline-mode specs boot into offline-restricted instead of
 *  bouncing to /login (src/app/offline/offlineMode.ts). Like the appearance,
 *  it is seeded only once per tab: restoring it on every document load would
 *  recreate a hint that logout deliberately removed.
 */
export function buildInitScript(options: {
  theme: ThemeMode;
  sessionHint?: { userId: string };
}) {
  const hintScript = options.sessionHint
    ? `const sessionHintSeed = "journiv.e2e.session-hint-seeded";
      if (!sessionStorage.getItem(sessionHintSeed)) {
        localStorage.setItem("journiv.session-hint.v1", ${JSON.stringify(
          JSON.stringify({
            version: 1,
            userId: options.sessionHint.userId,
            signedInAt: new Date(0).toISOString(),
          }),
        )});
        sessionStorage.setItem(sessionHintSeed, "1");
      }`
    : "";
  return `(() => {
    try {
      const appearanceSeed = "journiv.e2e.appearance-seeded";
      if (!sessionStorage.getItem(appearanceSeed)) {
        localStorage.setItem("journiv.theme", ${JSON.stringify(options.theme)});
        localStorage.removeItem("journiv.userTheme");
        sessionStorage.setItem(appearanceSeed, "1");
      }
      ${hintScript}
    } catch {}
  })();`;
}
