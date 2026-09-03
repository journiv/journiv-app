import { fileURLToPath } from "node:url";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const srcDir = fileURLToPath(new URL("./src", import.meta.url));

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "JOURNIV_");
  const backendProxy = env.JOURNIV_BACKEND_PROXY_URL ?? "http://127.0.0.1:8000";

  return {
    base: "/",
    plugins: [react(), tailwindcss()],
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
