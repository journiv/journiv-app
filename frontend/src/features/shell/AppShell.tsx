import { Dialog } from "@base-ui/react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Outlet,
  useLocation,
  useMatches,
  useRouter,
} from "@tanstack/react-router";
import { X } from "lucide-react";
import {
  createContext,
  lazy,
  Suspense,
  useContext,
  useEffect,
  useState,
} from "react";
import { sessionStore } from "../../api/auth/session";
import { currentUserQuery } from "../../api/query/options";
import { IconButton } from "../../components/ui/icon-button";
import type { SettingsSection } from "../settings/SettingsModal";
import { AppSidebar } from "./AppSidebar";
import { cx } from "../../lib/cx";
import "./shell.css";

const SettingsModal = lazy(async () => ({
  default: (await import("../settings/SettingsModal")).SettingsModal,
}));

type ShellContextValue = { openNavigation: () => void };
const ShellContext = createContext<ShellContextValue>({
  openNavigation: () => {},
});

/** Panes use this to render the compact navigation affordance in their PageBar. */
export function useShell() {
  return useContext(ShellContext);
}

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
      value={{ openNavigation: () => setDrawerOpen(true) }}
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
      </div>
    </ShellContext.Provider>
  );
}
