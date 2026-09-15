/**
 * Test-only stand-in for the `virtual:pwa-register` module vite-plugin-pwa
 * generates at build/dev time. Vitest never runs the plugin, so the literal
 * specifier can't resolve without this alias (vitest.config.ts) -- tests
 * that need control over it still call `vi.mock("virtual:pwa-register", ...)`,
 * which requires the specifier to resolve to a real, mockable module first.
 */
export function registerSW(): (reloadPage?: boolean) => Promise<void> {
  throw new Error(
    'virtual:pwa-register was not mocked -- call vi.mock("virtual:pwa-register", ...) in this test.',
  );
}
