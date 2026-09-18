import { expect, test } from "../fixtures/test";

test.describe("web app manifest", () => {
  test.use({ session: "none" });

  test("serves valid, no-cache JSON declaring both any and maskable icons", async ({
    page,
  }) => {
    const response = await page.request.get("/manifest.json");
    expect(response.status()).toBe(200);
    expect(response.headers()["cache-control"]).toContain("no-cache");

    const manifest = await response.json();
    expect(manifest.name).toBe("Journiv");
    expect(manifest.display).toBe("standalone");
    expect(manifest.id).toBe("/");

    const purposes = manifest.icons.map(
      (icon: { purpose?: string }) => icon.purpose,
    );
    expect(purposes).toContain("any");
    expect(purposes).toContain("maskable");
    expect(
      manifest.icons.some(
        (icon: { sizes?: string }) => icon.sizes === "192x192",
      ),
    ).toBe(true);
    expect(
      manifest.icons.some(
        (icon: { sizes?: string }) => icon.sizes === "512x512",
      ),
    ).toBe(true);

    for (const icon of manifest.icons as { src: string }[]) {
      const iconResponse = await page.request.get(icon.src);
      expect(iconResponse.status(), icon.src).toBe(200);
    }
  });

  // Route resolution for each shortcut's url is a router-shape question,
  // already covered by src/app/pwa/manifestShortcuts.test.ts (Vitest, against
  // the real router) -- it also catches a static path shadowed by a dynamic
  // segment, which an E2E navigation-not-/login check cannot.
  test("never ships a Quick Log shortcut", async ({ page }) => {
    const manifest = await (await page.request.get("/manifest.json")).json();
    const shortcuts = (manifest.shortcuts ?? []) as { name: string }[];
    expect(
      shortcuts.some((shortcut) =>
        shortcut.name.toLowerCase().includes("quick log"),
      ),
    ).toBe(false);
  });
});
