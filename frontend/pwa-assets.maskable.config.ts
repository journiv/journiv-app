import { defineConfig, type Preset } from "@vite-pwa/assets-generator/config";

/**
 * Generates the manifest's `maskable` icons from the dedicated full-bleed
 * source (public/pwa/maskable.svg), separate from pwa-assets.config.ts's
 * `any` source — Android's mask would crop the identity mark's asymmetric
 * tile. See DESIGN.md, "The identity mark". Run together via
 * `npm run pwa:assets`.
 */
const maskablePreset: Preset = {
  transparent: { sizes: [] },
  // No padding: public/pwa/maskable.svg is already full-bleed with the glyph
  // pre-scaled into the 80% safe zone. The tool's 0.3 default padding would
  // inset the whole square again, shrinking the mark and adding a visible
  // border no platform mask expects.
  maskable: { sizes: [192, 512], padding: 0 },
  apple: { sizes: [] },
};

export default defineConfig({
  preset: maskablePreset,
  images: ["public/pwa/maskable.svg"],
});
