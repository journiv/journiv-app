import { fileURLToPath } from "node:url";
import { configDefaults, defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

const srcDir = fileURLToPath(new URL("./src", import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": srcDir,
      // vite-plugin-pwa's virtual module only exists at build/dev time;
      // point it at a stub so registerServiceWorker.test.ts can vi.mock it.
      "virtual:pwa-register": fileURLToPath(
        new URL("./src/test/stubs/virtualPwaRegister.ts", import.meta.url),
      ),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    // Playwright specs are also named `*.spec.ts`, which Vitest's default
    // include would happily match and then fail to run. `e2e/` belongs to
    // Playwright; `src/**/*.test.ts(x)` belongs here.
    exclude: [...configDefaults.exclude, "e2e/**"],
  },
});
