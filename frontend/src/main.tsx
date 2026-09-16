import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import "./styles/index.css";
import { router } from "./app/router";
import { createAppQueryClient } from "./app/queryClient";
import { applyTheme, readTheme } from "./app/theme";
import { applyUserTheme } from "./features/theme/applyUserTheme";
import { readUserTheme } from "./features/theme/themeStorage";
import {
  applyUiExperiment,
  readUiExperiment,
} from "./features/theme/uiExperiment";
import { retireRootFlutterWorker } from "./app/retireRootFlutterWorker";
import { sessionStore } from "./api/auth/session";
import { Toaster } from "./components/ui/toast";

const rootElement = document.getElementById("root");
if (!rootElement) throw new Error("Missing application root");
const root = createRoot(rootElement);
const queryClient = createAppQueryClient();
applyTheme(readTheme());
// Personalization layer (colour / font / text size) — a <style> we render from
// the stored structured theme. Applied after applyTheme so there is no flash.
applyUserTheme(readUserTheme());
// TEMPORARY: UI-feel A/B experiment layer (docs/features/personalization.md). Softened primitives
// and pane separation, toggled from Settings → Appearance. Appended after the
// user theme so it wins while active. Remove with uiExperiment.ts.
applyUiExperiment(readUiExperiment());

async function boot() {
  // Must finish before the service worker registers (Phase 3) and before the
  // session restore request goes out, so a stale root-scoped Flutter worker
  // can never intercept either.
  await retireRootFlutterWorker();
  // The route guard (src/app/router/index.tsx) reads the resolved session
  // synchronously, so it must not render until this settles. The boot splash
  // in index.html is what the user sees meanwhile.
  await sessionStore.restore();

  root.render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <Toaster>
          <RouterProvider router={router} />
        </Toaster>
      </QueryClientProvider>
    </StrictMode>,
  );
}

void boot();
