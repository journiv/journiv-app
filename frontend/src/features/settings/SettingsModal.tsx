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
  useMemo,
  useRef,
  useState,
  type MutableRefObject,
} from "react";
import { Button } from "../../components/ui/button";
import { IconButton } from "../../components/ui/icon-button";
import { SettingsNavigation } from "./SettingsNavigation";
import { settingsItem, type SettingsNavItem } from "./settingsNav";
import { ProfilePage } from "./profile/ProfilePage";
import { SecurityPage } from "./security/SecurityPage";
import { AppearancePage } from "./appearance/AppearancePage";
import { AppSettingsPage } from "./app/AppSettingsPage";
import { IntegrationsPage } from "./integrations/IntegrationsPage";
import { ImportPage } from "./backup/ImportPage";
import { ExportPage } from "./backup/ExportPage";
import { HelpPage } from "./support/HelpPage";
import { AboutPage } from "./support/AboutPage";
import { currentUserQuery } from "../../api/query/options";
import { UsersPage } from "./admin/UsersPage";
import { UpdatesLicensePage } from "./admin/UpdatesLicensePage";
import "./settings.css";

/** The route the modal knows how to show. `AppShell` reads it from route
 *  `staticData` and only mounts this component when one is present. */
export type SettingsSection = "index" | SettingsNavItem["id"];

/** Above this width Settings is a centred modal; at or below it is a
 *  full-screen routed flow (docs/features/settings.md). Matches the app's own
 *  persistent-pane breakpoint (DESIGN.md). */
export const SETTINGS_DESKTOP_QUERY = "(min-width: 1101px)";

const DISCARD_PROMPT = "Discard your unsaved changes?";

function isDesktop() {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia(SETTINGS_DESKTOP_QUERY).matches
  );
}

/** What the modal's fixed action bar needs to render a page's primary Save. */
type SettingsSaveState = {
  pending: boolean;
  canSave: boolean;
  /** Resting label, default "Save changes". */
  label?: string;
  /** Label while pending, default "Saving…". */
  pendingLabel?: string;
};

type SettingsFormContextValue = {
  /** A page with an editable form calls this as its dirty state changes. The
   *  modal then guards every dismissal — X, Escape, backdrop, section switch,
   *  browser Back. */
  setDirty: (dirty: boolean) => void;
  /** Latest primary-save handler for the modal action bar. Held in a ref so a
   *  page can pass a fresh closure every render without re-arming effects. */
  saveRef: MutableRefObject<(() => void) | null>;
  /** Publishes (or clears, with null) the action bar's button state. */
  setSaveState: (state: SettingsSaveState | null) => void;
};

const SettingsFormContext = createContext<SettingsFormContextValue>({
  setDirty: () => {},
  saveRef: { current: null },
  setSaveState: () => {},
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

/**
 * A settings page with one primary Save calls this instead of `useSettingsDirty`.
 * It arms the dismissal guard AND surfaces the Save control in the modal's fixed
 * action bar (docs/features/settings.md) — the page keeps its own `<form>` and
 * submit logic; the bar just calls `onSave`. Every field is a primitive or a
 * ref-held closure, so passing a fresh object each render is fine.
 */
export function useSettingsForm(options: {
  dirty: boolean;
  pending: boolean;
  canSave: boolean;
  onSave: () => void;
  label?: string;
  pendingLabel?: string;
}) {
  const { setDirty, saveRef, setSaveState } = useContext(SettingsFormContext);
  const { dirty, pending, canSave, onSave, label, pendingLabel } = options;

  // Keep the newest handler without making effects depend on its identity.
  saveRef.current = onSave;

  useEffect(() => {
    setDirty(dirty);
    return () => setDirty(false);
  }, [dirty, setDirty]);

  useEffect(() => {
    setSaveState({ pending, canSave, label, pendingLabel });
    return () => setSaveState(null);
  }, [pending, canSave, label, pendingLabel, setSaveState]);
}

export function SettingsModal({ section }: { section: SettingsSection }) {
  const router = useRouter();
  const navigate = useNavigate();
  const matchRoute = useMatchRoute();
  const onIntegrationsDetail = Boolean(
    matchRoute({ to: "/settings/integrations/$provider" }),
  );
  const dirtyRef = useRef(false);
  const saveRef = useRef<(() => void) | null>(null);
  const [saveState, setSaveState] = useState<SettingsSaveState | null>(null);
  const currentUser = useQuery(currentUserQuery());
  const isAdmin = currentUser.data?.role === "admin";

  const setDirty = useCallback((next: boolean) => {
    dirtyRef.current = next;
  }, []);

  const formContext = useMemo<SettingsFormContextValue>(
    () => ({ setDirty, saveRef, setSaveState }),
    [setDirty],
  );

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
    if (
      (section === "users" || section === "updatesLicense") &&
      currentUser.data &&
      !isAdmin
    ) {
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

  // The action bar only makes sense against a real section form, never the
  // bare compact index.
  const showActionBar = saveState != null && section !== "index";

  return (
    <SettingsFormContext.Provider value={formContext}>
      <Dialog.Root
        open
        onOpenChange={(open) => {
          if (!open) close();
        }}
      >
        <Dialog.Portal>
          <Dialog.Backdrop className="z-[42] fixed inset-0 bg-black/10 duration-100 supports-backdrop-filter:backdrop-blur-xs data-open:animate-in data-open:fade-in-0 data-closed:animate-out data-closed:fade-out-0" />
          <Dialog.Popup className="jv-settings-popup">
            <Dialog.Title className="sr-only">Settings</Dialog.Title>
            <div className="jv-settings">
              {/* The modal's own header — a flex sibling above the one scroll
                  owner, never sticky (DESIGN.md). One close control. */}
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
                  {section === "app" && <AppSettingsPage />}
                  {section === "integrations" && <IntegrationsPage />}
                  {section === "users" && isAdmin && <UsersPage />}
                  {section === "updatesLicense" && isAdmin && (
                    <UpdatesLicensePage />
                  )}
                  {section === "import" && <ImportPage />}
                  {section === "export" && <ExportPage />}
                  {section === "help" && <HelpPage />}
                  {section === "about" && <AboutPage />}
                </div>

                {/* The page's one primary Save. A fixed flex sibling of the
                    scroll owner, never a layer over it (DESIGN.md). Pages
                    register it with useSettingsForm; on compact widths its
                    button goes full-width. */}
                {showActionBar && (
                  <div className="jv-settings__actionbar">
                    <Button
                      type="button"
                      variant="default"
                      disabled={!saveState.canSave || saveState.pending}
                      onClick={() => saveRef.current?.()}
                    >
                      {saveState.pending
                        ? (saveState.pendingLabel ?? "Saving…")
                        : (saveState.label ?? "Save changes")}
                    </Button>
                  </div>
                )}
              </div>
            </div>
          </Dialog.Popup>
        </Dialog.Portal>
      </Dialog.Root>
    </SettingsFormContext.Provider>
  );
}
