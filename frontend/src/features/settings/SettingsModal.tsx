import { Dialog } from "@base-ui/react";
import { useQuery } from "@tanstack/react-query";
import {
  Link,
  useBlocker,
  useMatchRoute,
  useNavigate,
  useRouter,
} from "@tanstack/react-router";
import { ChevronLeft, X } from "lucide-react";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
} from "react";
import { IconButton } from "../../components/ui/icon-button";
import { SettingsNavigation } from "./SettingsNavigation";
import { settingsItem, type SettingsNavItem } from "./settingsNav";
import { ProfilePage } from "./profile/ProfilePage";
import { SecurityPage } from "./security/SecurityPage";
import { AppearancePage } from "./appearance/AppearancePage";
import { IntegrationsPage } from "./integrations/IntegrationsPage";
import { ImportPage } from "./backup/ImportPage";
import { ExportPage } from "./backup/ExportPage";
import { HelpPage } from "./support/HelpPage";
import { AboutPage } from "./support/AboutPage";
import { currentUserQuery } from "../../api/query/options";
import { UsersPage } from "./admin/UsersPage";
import "./settings.css";

/** The route the modal knows how to show. `AppShell` reads it from route
 *  `staticData` and only mounts this component when one is present. */
export type SettingsSection = "index" | SettingsNavItem["id"];

/** Above this width Settings is a centred modal; at or below it is a
 *  full-screen routed flow (DESIGN.md §23). Matches the app's own
 *  persistent-pane breakpoint (DESIGN.md §9). */
export const SETTINGS_DESKTOP_QUERY = "(min-width: 1101px)";

const DISCARD_PROMPT = "Discard your unsaved changes?";

function isDesktop() {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia(SETTINGS_DESKTOP_QUERY).matches
  );
}

type SettingsFormContextValue = {
  /** A page with an editable form calls this as its dirty state changes. The
   *  modal then guards every dismissal — X, Escape, backdrop, section switch,
   *  browser Back. */
  setDirty: (dirty: boolean) => void;
};

const SettingsFormContext = createContext<SettingsFormContextValue>({
  setDirty: () => {},
});

/** Registers a page's unsaved-changes state with the modal's dismissal guard.
 *  Clears itself on unmount so a discarded page cannot keep the guard armed. */
export function useSettingsDirty(dirty: boolean) {
  const { setDirty } = useContext(SettingsFormContext);
  useEffect(() => {
    setDirty(dirty);
    return () => setDirty(false);
  }, [dirty, setDirty]);
}

export function SettingsModal({ section }: { section: SettingsSection }) {
  const router = useRouter();
  const navigate = useNavigate();
  const matchRoute = useMatchRoute();
  const onIntegrationsDetail = Boolean(
    matchRoute({ to: "/settings/integrations/$provider" }),
  );
  const dirtyRef = useRef(false);
  const currentUser = useQuery(currentUserQuery());
  const isAdmin = currentUser.data?.role === "admin";

  const setDirty = useCallback((next: boolean) => {
    dirtyRef.current = next;
  }, []);

  // One guard for every path out of a dirty form: the section links, the
  // programmatic close below, and browser Back all pass through it. The native
  // reload prompt is left off — the guard is for in-app dismissal.
  useBlocker({
    enableBeforeUnload: false,
    shouldBlockFn: () =>
      dirtyRef.current ? !window.confirm(DISCARD_PROMPT) : false,
  });

  const settingsFrom = router.state.location.state.settingsFrom;

  const close = useCallback(() => {
    if (settingsFrom) router.history.replace(settingsFrom);
    else navigate({ to: "/timeline", search: { q: "" } });
  }, [settingsFrom, router, navigate]);

  // Desktop never sits on the bare index (the route redirects); a viewport that
  // grows past the breakpoint while `/settings` is open is the one exception.
  useEffect(() => {
    if (section === "index" && isDesktop()) {
      navigate({
        to: "/settings/profile",
        search: { q: "" },
        state: (prev) => prev,
        replace: true,
      });
    }
  }, [section, navigate]);

  // Administration is absent from navigation for ordinary users. A direct
  // deep link is also returned to Profile before the admin query can mount.
  useEffect(() => {
    if (section === "users" && currentUser.data && !isAdmin) {
      navigate({
        to: "/settings/profile",
        search: { q: "" },
        state: (prev) => prev,
        replace: true,
      });
    }
  }, [currentUser.data, isAdmin, navigate, section]);

  const sectionLabel =
    section === "index"
      ? "Settings"
      : onIntegrationsDetail
        ? "Immich"
        : settingsItem(section).label;

  return (
    <SettingsFormContext.Provider value={{ setDirty }}>
      <Dialog.Root
        open
        onOpenChange={(open) => {
          if (!open) close();
        }}
      >
        <Dialog.Portal>
          <Dialog.Backdrop className="jv-settings-backdrop" />
          <Dialog.Popup className="jv-settings-popup">
            <Dialog.Title className="sr-only">Settings</Dialog.Title>
            <div className="jv-settings">
              {/* The modal's own header — a flex sibling above the one scroll
                  owner, never sticky (DESIGN.md §9). One close control. */}
              <div className="jv-settings__topbar">
                {section !== "index" && (
                  <IconButton
                    label={
                      onIntegrationsDetail
                        ? "Back to integrations"
                        : "Back to settings"
                    }
                    className="jv-settings__back"
                    nativeButton={false}
                    render={
                      <Link
                        to={
                          onIntegrationsDetail
                            ? "/settings/integrations"
                            : "/settings"
                        }
                        search={{ q: "" }}
                        state={(prev) => prev}
                      />
                    }
                  >
                    <ChevronLeft aria-hidden="true" size={18} />
                  </IconButton>
                )}
                <span className="jv-settings__title jv-desktop-only">
                  Settings
                </span>
                <span className="jv-settings__title jv-compact-only">
                  {sectionLabel}
                </span>
                <IconButton
                  label="Close settings"
                  className="jv-settings__close"
                  onClick={close}
                >
                  <X aria-hidden="true" size={18} />
                </IconButton>
              </div>

              <div className="jv-settings__nav">
                <SettingsNavigation isAdmin={isAdmin} />
              </div>

              <div className="jv-settings__content">
                <div className="jv-settings__scroll">
                  {section === "index" && (
                    <SettingsNavigation isAdmin={isAdmin} />
                  )}
                  {section === "profile" && <ProfilePage />}
                  {section === "security" && <SecurityPage />}
                  {section === "appearance" && <AppearancePage />}
                  {section === "integrations" && <IntegrationsPage />}
                  {section === "users" && isAdmin && <UsersPage />}
                  {section === "import" && <ImportPage />}
                  {section === "export" && <ExportPage />}
                  {section === "help" && <HelpPage />}
                  {section === "about" && <AboutPage />}
                </div>
              </div>
            </div>
          </Dialog.Popup>
        </Dialog.Portal>
      </Dialog.Root>
    </SettingsFormContext.Provider>
  );
}
