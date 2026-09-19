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
import {
  hydrateOfflineCache,
  purgeOfflineCache,
  revalidatePersistedQueries,
  subscribeOfflineCache,
  teardownOfflineCache,
} from "./app/offline/offlineCache";
import {
  getBootMode,
  initBootMode,
  subscribeBootMode,
} from "./app/offline/offlineMode";
import { registerServiceWorker } from "./app/pwa/registerServiceWorker";
import {
  registerOfflineCachePurge,
  registerOfflineCacheSubscribe,
  sessionStore,
} from "./api/auth/session";
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

// The offline cache module has no dependency on session.ts (avoids a
// cycle); session.ts calls back through these registrations instead: purge
// on logout / a definite 401, and (re)subscribe from adopt() -- a fresh
// sign-in has no hint yet at boot, so without this the subscription boot
// started never learns the userId and nothing gets persisted for it.
registerOfflineCachePurge((userId) => {
  teardownOfflineCache();
  void purgeOfflineCache(userId).catch(() => {
    // Session teardown must complete even if browser storage cannot be erased.
  });
});
registerOfflineCacheSubscribe((userId) => {
  subscribeOfflineCache(queryClient, userId);
});

async function boot() {
  // Must finish before the service worker registers and before the session
  // restore request goes out, so a stale root-scoped Flutter worker can
  // never intercept either.
  await retireRootFlutterWorker();

  const hint = sessionStore.readHint();
  // Concurrent, not sequential: an offline cold launch must paint cached
  // content in well under a second, not stare at the splash for the full
  // restore timeout before hydration even starts (docs/features/pwa.md).
  const [restoreResult] = await Promise.all([
    sessionStore.restore(),
    hydrateOfflineCache(queryClient, hint?.userId),
  ]);
  initBootMode(restoreResult);
  // An authenticated boot must use IndexedDB as stale-while-revalidate, not
  // as a second source of truth. Mark only the allowlisted persisted queries
  // stale before render; a later offline -> normal upgrade does the same and
  // immediately refreshes any active cached screen.
  if (getBootMode() === "normal") {
    void revalidatePersistedQueries(queryClient);
  }
  const unsubscribeBootMode = subscribeBootMode((mode) => {
    if (mode === "normal") void revalidatePersistedQueries(queryClient);
  });
  const unsubscribeOfflineCache = subscribeOfflineCache(
    queryClient,
    sessionStore.readHint()?.userId,
  );
  void unsubscribeBootMode; // kept alive for the app's lifetime
  void unsubscribeOfflineCache; // kept alive for the app's lifetime

  root.render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <Toaster>
          <RouterProvider router={router} />
        </Toaster>
      </QueryClientProvider>
    </StrictMode>,
  );

  // After first render, not before: a registration competing with the boot
  // restore request above would slow down the launch the user sees.
  registerServiceWorker();
}

void boot();
