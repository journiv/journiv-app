import type { Page } from "@playwright/test";
import { expect } from "../fixtures/test";

/**
 * A registration existing is not enough to route an offline navigation
 * through the worker's fetch handler -- it must be `active`. Waiting only
 * for registration count (not `active`) let a reload race activation and
 * hit the real network, which is exactly what going offline then breaks.
 */
export async function waitForActiveServiceWorker(page: Page) {
  await expect(async () => {
    const active = await page.evaluate(async () => {
      const registrations = await navigator.serviceWorker.getRegistrations();
      return registrations.some((registration) => registration.active);
    });
    expect(active).toBe(true);
  }).toPass({ timeout: 10_000 });
}
