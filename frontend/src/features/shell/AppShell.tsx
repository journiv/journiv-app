import { Dialog } from "@base-ui/react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Outlet,
  useLocation,
  useMatches,
  useRouter,
} from "@tanstack/react-router";
import { X } from "lucide-react";
import { lazy, Suspense, useEffect, useState } from "react";
import { sessionStore } from "../../api/auth/session";
import { currentUserQuery } from "../../api/query/options";
import { IconButton } from "../../components/ui/icon-button";
import type { SettingsSection } from "../settings/SettingsModal";
import { AppSidebar } from "./AppSidebar";
import { ShellContext } from "./shellContext";
import { cx } from "../../lib/cx";
import "./shell.css";

// Re-exported for existing importers; the context itself lives in shellContext
// to keep the AppShell ↔ AppSidebar module pair free of a cycle.
export { useShell } from "./shellContext";

const SettingsModal = lazy(async () => ({
  default: (await import("../settings/SettingsModal")).SettingsModal,
}));
const QuickLogSheet = lazy(async () => ({
  default: (await import("../quicklog/QuickLogSheet")).QuickLogSheet,
}));

export function AppShell() {
  const location = useLocation();
  const matches = useMatches();
  // Declarative, from the route tree — not a pathname regex. Adding a detail
  // route only requires `staticData: { pane: "detail" }` on that route.
  const detailActive = matches.some(
    (match) => match.staticData?.pane === "detail",
  );
  // Same declarative read for the Settings overlay: a `staticData.settings`
  // route means "open the Settings modal on this section" (docs/features/settings.md).
  const settingsSection = matches
    .map((match) => match.staticData?.settings)
    .find((value): value is SettingsSection => Boolean(value));

  const [drawerOpen, setDrawerOpen] = useState(false);
  // Quick Log is a single-session capture. Bumping `quickLogKey` on every open
  // remounts the sheet so its form state and moment identity start clean, while
  // leaving it mounted on close lets the overlay animate out.
  const [quickLogOpen, setQuickLogOpen] = useState(false);
  const [quickLogKey, setQuickLogKey] = useState(0);
  const router = useRouter();
  const queryClient = useQueryClient();
  const currentUser = useQuery(currentUserQuery());

  useEffect(() => {
    const signOut = () => {
      queryClient.clear();
      void router.navigate({
        to: "/login",
        search: { returnTo: location.href },
      });
    };
    const unsubscribe = sessionStore.subscribe((session) => {
      if (!session) signOut();
    });
    if (currentUser.isError) sessionStore.clear();
    return unsubscribe;
  }, [currentUser.isError, location.href, queryClient, router]);

  return (
    <ShellContext.Provider
      value={{
        openNavigation: () => setDrawerOpen(true),
        openQuickLog: () => {
          setQuickLogKey((key) => key + 1);
          setQuickLogOpen(true);
        },
      }}
    >
      <div className={cx("jv-shell", detailActive && "is-detail")}>
        <Dialog.Root open={drawerOpen} onOpenChange={setDrawerOpen}>
          <Dialog.Portal>
            <Dialog.Backdrop className="z-30 fixed inset-0 bg-black/10 duration-100 supports-backdrop-filter:backdrop-blur-xs data-open:animate-in data-open:fade-in-0 data-closed:animate-out data-closed:fade-out-0" />
            <Dialog.Popup className="jv-drawer">
              <Dialog.Title className="sr-only">
                Journiv navigation
              </Dialog.Title>
              <IconButton
                label="Close navigation"
                variant="secondary"
                className="jv-drawer__close"
                onClick={() => setDrawerOpen(false)}
              >
                <X aria-hidden="true" size={17} />
              </IconButton>
              <AppSidebar
                user={currentUser.data}
                loadingUser={currentUser.isLoading}
                onNavigate={() => setDrawerOpen(false)}
              />
            </Dialog.Popup>
          </Dialog.Portal>
        </Dialog.Root>

        <aside className="jv-shell__nav" aria-label="Primary navigation">
          <AppSidebar
            user={currentUser.data}
            loadingUser={currentUser.isLoading}
          />
        </aside>
        <Outlet />

        {settingsSection && (
          <Suspense fallback={null}>
            <SettingsModal section={settingsSection} />
          </Suspense>
        )}

        {quickLogKey > 0 && (
          <Suspense fallback={null}>
            <QuickLogSheet
              key={quickLogKey}
              open={quickLogOpen}
              onOpenChange={setQuickLogOpen}
            />
          </Suspense>
        )}
      </div>
    </ShellContext.Provider>
  );
}
