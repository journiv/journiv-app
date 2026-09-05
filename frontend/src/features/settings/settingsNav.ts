/**
 * The Settings information architecture as data (docs/features/settings.md).
 *
 * A future page is: add a route in `src/app/router`, add an entry here, build
 * the page. Nothing in the modal, the responsive behaviour, the active state or
 * the close behaviour needs to change.
 *
 * Only sections with a real page ship. We do not render dead links — a group
 * with nothing functional is simply omitted until its first page lands. The
 * commented groups below are the planned shape, not a to-do list rendered on
 * screen.
 */

export type SettingsRouteTo =
  | "/settings/profile"
  | "/settings/security"
  | "/settings/appearance"
  | "/settings/admin/users"
  | "/settings/admin/updates-license"
  | "/settings/integrations"
  | "/settings/data/import"
  | "/settings/data/export"
  | "/settings/support/help"
  | "/settings/support/about";

export type SettingsNavItem = {
  /** Stable key, also used as the section identifier in `staticData`. */
  id:
    | "profile"
    | "security"
    | "appearance"
    | "users"
    | "updatesLicense"
    | "integrations"
    | "import"
    | "export"
    | "help"
    | "about";
  label: string;
  to: SettingsRouteTo;
};

export type SettingsNavGroup = {
  /** Quiet hierarchy label (sentence case — DESIGN.md). */
  label: string;
  items: SettingsNavItem[];
  /** Administration is visible only after the shared current-user query says
   *  the viewer is an administrator. */
  adminOnly?: boolean;
};

export const SETTINGS_NAV: SettingsNavGroup[] = [
  {
    label: "Account",
    items: [
      { id: "profile", label: "Profile", to: "/settings/profile" },
      { id: "security", label: "Security", to: "/settings/security" },
    ],
  },
  {
    label: "Appearance",
    items: [
      { id: "appearance", label: "Theme & time", to: "/settings/appearance" },
    ],
  },
  {
    label: "Integrations",
    items: [
      { id: "integrations", label: "Providers", to: "/settings/integrations" },
    ],
  },
  {
    label: "Administration",
    adminOnly: true,
    items: [
      { id: "users", label: "Users", to: "/settings/admin/users" },
      {
        id: "updatesLicense",
        label: "Updates & license",
        to: "/settings/admin/updates-license",
      },
    ],
  },
  {
    label: "Data & backup",
    items: [
      { id: "import", label: "Import", to: "/settings/data/import" },
      { id: "export", label: "Export", to: "/settings/data/export" },
    ],
  },
  {
    label: "Support",
    items: [
      { id: "help", label: "Help & feedback", to: "/settings/support/help" },
      { id: "about", label: "About", to: "/settings/support/about" },
    ],
  },
];

export const SETTINGS_NAV_ITEMS: SettingsNavItem[] = SETTINGS_NAV.flatMap(
  (group) => group.items,
);

export function settingsItem(id: SettingsNavItem["id"]): SettingsNavItem {
  const item = SETTINGS_NAV_ITEMS.find((entry) => entry.id === id);
  if (!item) throw new Error(`Unknown settings section: ${id}`);
  return item;
}
