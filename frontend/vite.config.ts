import { fileURLToPath } from "node:url";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { VitePWA } from "vite-plugin-pwa";
import { manifestShortcuts } from "./src/app/pwa/manifestShortcuts";

const srcDir = fileURLToPath(new URL("./src", import.meta.url));
const shortcutIcons = [
  { src: "/pwa-192x192.png", sizes: "192x192", type: "image/png" },
];

// Manifest colours are not scanned by npm run lint:design (raw colours are a
// source-tree rule). Keep them mirroring the real tokens by hand:
// src/styles/tokens.css `--background` -- oklch(1 0 0) light, oklch(0.205 0 0)
// dark, resolved to sRGB via getComputedStyle in a real browser (do not trust
// an eyeballed conversion — oklch does not map to hex by inspection).
const LIGHT_BACKGROUND_HEX = "#ffffff";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "JOURNIV_");
  const backendProxy = env.JOURNIV_BACKEND_PROXY_URL ?? "http://127.0.0.1:8000";

  return {
    base: "/",
    plugins: [
      react(),
      tailwindcss(),
      VitePWA({
        // registerType/workbox/service-worker filename land in Phase 3
        // (docs/features/pwa.md); this call only establishes the manifest.
        injectRegister: null,
        manifestFilename: "manifest.json",
        includeAssets: ["favicon.svg", "favicon.ico", "apple-touch-icon.png"],
        manifest: {
          id: "/",
          name: "Journiv",
          short_name: "Journiv",
          description: "Your private journal.",
          start_url: "/",
          scope: "/",
          display: "standalone",
          display_override: ["standalone", "minimal-ui", "browser"],
          theme_color: LIGHT_BACKGROUND_HEX,
          background_color: LIGHT_BACKGROUND_HEX,
          lang: "en",
          dir: "ltr",
          categories: ["lifestyle", "productivity"],
          launch_handler: { client_mode: "navigate-existing" },
          handle_links: "preferred",
          prefer_related_applications: false,
          icons: [
            {
              src: "/pwa-192x192.png",
              sizes: "192x192",
              type: "image/png",
              purpose: "any",
            },
            {
              src: "/pwa-512x512.png",
              sizes: "512x512",
              type: "image/png",
              purpose: "any",
            },
            {
              src: "/pwa/maskable-icon-192x192.png",
              sizes: "192x192",
              type: "image/png",
              purpose: "maskable",
            },
            {
              src: "/pwa/maskable-icon-512x512.png",
              sizes: "512x512",
              type: "image/png",
              purpose: "maskable",
            },
          ],
          // Android long-press shortcuts only; iOS ignores this. Reuses the
          // `any` 192 icon rather than drawing three new glyphs. Never add
          // Quick Log here -- it ships behind QUICK_LOG_ENABLED = false
          // (src/features/shell/shellContext.ts). The list itself lives in
          // manifestShortcuts.ts so manifestShortcuts.test.ts can assert
          // every url resolves in the router.
          shortcuts: manifestShortcuts.map((shortcut) => ({
            ...shortcut,
            icons: shortcutIcons,
          })),
        },
        devOptions: { enabled: false },
      }),
    ],
    resolve: {
      alias: { "@": srcDir },
    },
    server: {
      port: process.env.PORT ? Number(process.env.PORT) : undefined,
      proxy: {
        "/api": backendProxy,
        "/media": backendProxy,
      },
    },
  };
});
