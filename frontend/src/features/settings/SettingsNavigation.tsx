import { Link, useMatchRoute } from "@tanstack/react-router";
import { cx } from "../../lib/cx";
import { SETTINGS_NAV } from "./settingsNav";

/**
 * The Settings section list. One component for both surfaces: the fixed left
 * column of the desktop modal and the full-screen list on compact widths
 * (docs/features/settings.md). Selection is by route match, never pathname parsing
 * (DESIGN.md), and is shown with a tint plus a rail and `aria-current`.
 */
export function SettingsNavigation({
  onNavigate,
  isAdmin = false,
}: {
  onNavigate?: () => void;
  isAdmin?: boolean;
}) {
  const matchRoute = useMatchRoute();
  const groups = SETTINGS_NAV.filter((group) => !group.adminOnly || isAdmin);
  return (
    <nav className="jv-settings-nav" aria-label="Settings sections">
      {groups.map((group) => (
        <div className="jv-settings-nav__group" key={group.label}>
          <p className="jv-settings-nav__label">{group.label}</p>
          {/* The items are wrapped separately from the label so the compact
              settings index can card the destinations and leave the group
              label on the canvas above them (docs/features/settings.md). */}
          <div className="jv-settings-nav__items">
            {group.items.map((item) => {
              const selected = Boolean(matchRoute({ to: item.to }));
              return (
                <Link
                  key={item.id}
                  to={item.to}
                  search={{ q: "" }}
                  state={(prev) => prev}
                  onClick={onNavigate}
                  className={cx(
                    "jv-settings-nav__item",
                    selected && "is-selected",
                  )}
                  aria-current={selected ? "page" : undefined}
                >
                  {item.label}
                </Link>
              );
            })}
          </div>
        </div>
      ))}
    </nav>
  );
}
