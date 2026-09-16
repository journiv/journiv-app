import { defineConfig, type Preset } from "@vite-pwa/assets-generator/config";

/**
 * Generates the manifest's `any` icons from the identity mark
 * (public/favicon.svg) — the asymmetric rounded tile, unchanged. See
 * DESIGN.md, "The identity mark", and pwa-assets.maskable.config.ts for the
 * separate `maskable` source. Regenerate with `npm run pwa:assets`.
 */
const anyPreset: Preset = {
  // No padding: favicon.svg's tile already fills its own viewBox exactly as
  // BrandMark.tsx renders it. The tool's 0.3 default padding would inset it.
  transparent: { sizes: [192, 512], padding: 0 },
  maskable: { sizes: [] },
  apple: { sizes: [] },
};

export default defineConfig({
  preset: anyPreset,
  images: ["public/favicon.svg"],
});
