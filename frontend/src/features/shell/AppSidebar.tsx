import {
  Link,
  useMatchRoute,
  useNavigate,
  useRouterState,
  useSearch,
} from "@tanstack/react-router";
import {
  CalendarDays,
  ChartNoAxesCombined,
  Clock3,
  Images,
  Library,
  LogOut,
  Monitor,
  Moon,
  Plus,
  RefreshCw,
  Settings,
  Sun,
} from "lucide-react";
import type { ReactNode } from "react";
import type {
  JournalResponse,
  UserResponse,
} from "../../api/generated/types.gen";
import { sessionStore } from "../../api/auth/session";
import { useTheme, type ThemeMode } from "../../app/theme";
import { Button } from "../../components/ui/button";
import { IconButton } from "../../components/ui/icon-button";
import { Skeleton } from "../../components/ui/skeleton";
import { BrandMark } from "../../components/journiv/BrandMark";
import { JournalDot } from "../../components/journiv/JournalBadge";
import { groupJournals } from "../../lib/journalOrder";
import { useJournalLookup } from "../../lib/useJournalLookup";
import { cx } from "../../lib/cx";
import { startOidcLogout } from "../auth/oidc";
import "./shell.css";
import { ToggleGroup, ToggleGroupItem } from "../../components/ui/toggle-group";

/** Most journals the rail shows before it defers the rest to "All journals". */
const SIDEBAR_MAX = 8;

export function AppSidebar({
  user,
  loadingUser,
  onNavigate,
}: {
  user?: UserResponse;
  loadingUser: boolean;
  onNavigate?: () => void;
}) {
  const { journals, isLoading, isError, refetch } = useJournalLookup();
  const navigate = useNavigate();
  // Where Settings was opened from, so closing it returns here (docs/features/settings.md).
  const fromHref = useRouterState({ select: (state) => state.location.href });
  // The rail lists active journals in the canonical order — favourites sort to
  // the top, so favouriting re-orders rather than hiding anything. Only a long
  // list is truncated, and "All journals" always covers the rest (and is the
  // one route to archived journals). See docs/features/journals.md.
  const { active } = groupJournals(journals);
  const railJournals = active.slice(0, SIDEBAR_MAX);

  return (
    <div className="jv-nav">
      <div className="jv-nav__brand">
        <BrandMark wordmark size={24} />
      </div>

      {/* Styled as a button, never as a nav item: it must not pick up the
          selected-route treatment. That regression made it unreadable before.
          This is the product's one filled brand control (DESIGN.md, brand
          use #1) — writing is the thing Journiv exists for. */}
      <Button
        variant="brand"
        className="jv-nav__new"
        nativeButton={false}
        render={
          <Link to="/timeline/new" search={{ q: "" }} onClick={onNavigate} />
        }
      >
        <Plus aria-hidden="true" size={16} />
        New entry
      </Button>

      <nav className="jv-nav__group" aria-label="Views">
        <NavItem
          to="/timeline"
          onNavigate={onNavigate}
          icon={<Clock3 aria-hidden="true" size={16} />}
        >
          Timeline
        </NavItem>
        <NavItem
          to="/timeline"
          view="calendar"
          onNavigate={onNavigate}
          icon={<CalendarDays aria-hidden="true" size={16} />}
        >
          Calendar
        </NavItem>
        <NavItem
          to="/timeline"
          view="media"
          onNavigate={onNavigate}
          icon={<Images aria-hidden="true" size={16} />}
        >
          Media
        </NavItem>
        <InsightsNavItem onNavigate={onNavigate} />
      </nav>

      <p className="jv-nav__section">Journals</p>
      <nav className="jv-nav__group" aria-label="Journals">
        {isLoading && (
          <div
            className="jv-nav__loading"
            role="status"
            aria-label="Loading journals"
          >
            <Skeleton height="1rem" width="70%" />
            <Skeleton height="1rem" width="55%" />
            <Skeleton height="1rem" width="62%" />
          </div>
        )}
        {isError && (
          <Button
            variant="ghost"
            className="jv-nav__item"
            onClick={() => refetch()}
          >
            <RefreshCw aria-hidden="true" size={15} />
            Retry journals
          </Button>
        )}
        {!isLoading &&
          !isError &&
          railJournals.map((journal) => (
            <JournalNavItem
              key={journal.id}
              journal={journal}
              onNavigate={onNavigate}
            />
          ))}
        {!isLoading && !isError && <AllJournalsItem onNavigate={onNavigate} />}
      </nav>

      <p className="jv-nav__section">Library</p>
      <nav className="jv-nav__group" aria-label="Library">
        <NavItem
          to="/settings/journaling/people"
          onNavigate={onNavigate}
          nested
        >
          People
        </NavItem>
        <NavItem to="/library/prompts" onNavigate={onNavigate} nested>
          Prompts
        </NavItem>
        <NavItem to="/library/tags" onNavigate={onNavigate} nested>
          Tags
        </NavItem>
        <NavItem to="/settings/journaling/moods" onNavigate={onNavigate} nested>
          Moods
        </NavItem>
        <NavItem
          to="/settings/journaling/activities"
          onNavigate={onNavigate}
          nested
        >
          Activities
        </NavItem>
        <NavItem to="/settings/journaling/goals" onNavigate={onNavigate} nested>
          Goals
        </NavItem>
      </nav>

      <div className="jv-nav__footer">
        <ThemeControl />
        <div className="jv-nav__account">
          {loadingUser ? (
            <div className="jv-nav__account-text">
              <Skeleton height="0.85rem" width="60%" />
              <Skeleton height="0.75rem" width="80%" />
            </div>
          ) : (
            <div className="jv-nav__account-text">
              <span className="jv-label jv-truncate">
                {user?.name || "Journiv"}
              </span>
              <span className="jv-caption jv-truncate">{user?.email}</span>
            </div>
          )}
          <IconButton
            label="Settings"
            onClick={() => {
              navigate({
                to: "/settings",
                search: { q: "" },
                state: { settingsFrom: fromHref },
              });
              onNavigate?.();
            }}
          >
            <Settings aria-hidden="true" size={16} />
          </IconButton>
          <IconButton
            label="Log out"
            onClick={() => {
              const useSingleSignOut = user?.is_oidc_user === true;
              sessionStore.clear();
              onNavigate?.();
              if (useSingleSignOut) startOidcLogout();
            }}
          >
            <LogOut aria-hidden="true" size={16} />
          </IconButton>
        </div>
      </div>
    </div>
  );
}

function NavItem({
  to,
  icon,
  children,
  onNavigate,
  nested = false,
  view,
}: {
  to:
    | "/timeline"
    | "/settings/journaling/people"
    | "/library/prompts"
    | "/library/tags"
    | "/settings/journaling/moods"
    | "/settings/journaling/activities"
    | "/settings/journaling/goals";
  icon?: ReactNode;
  children: ReactNode;
  onNavigate?: () => void;
  nested?: boolean;
  /** Timeline / Calendar / Media share the `/timeline` route and differ only by
   *  the `view` search param, so the active one is chosen by that param too. */
  view?: "calendar" | "media";
}) {
  const matchRoute = useMatchRoute();
  const currentView = useSearch({
    strict: false,
    select: (s) => (s as { view?: "calendar" | "media" }).view,
  });
  // Route matching, not pathname parsing: this stays correct when search
  // params change and when child routes are added.
  const routeMatches = Boolean(matchRoute({ to, fuzzy: true }));
  const selected =
    to === "/timeline" ? routeMatches && currentView === view : routeMatches;
  return (
    <Link
      to={to}
      search={view ? { q: "", view } : { q: "" }}
      onClick={onNavigate}
      className={cx(
        "jv-nav__item",
        nested && "jv-nav__item--nested",
        selected && "is-selected",
      )}
      aria-current={selected ? "page" : undefined}
    >
      {icon}
      <span className="jv-truncate">{children}</span>
    </Link>
  );
}

function JournalNavItem({
  journal,
  onNavigate,
}: {
  journal: JournalResponse;
  onNavigate?: () => void;
}) {
  const matchRoute = useMatchRoute();
  const selected = Boolean(
    matchRoute({
      to: "/journals/$journalId",
      params: { journalId: journal.id },
      fuzzy: true,
    }),
  );
  return (
    <Link
      to="/journals/$journalId"
      params={{ journalId: journal.id }}
      search={{ q: "" }}
      onClick={onNavigate}
      className={cx("jv-nav__item", selected && "is-selected")}
      aria-current={selected ? "page" : undefined}
    >
      <JournalDot journal={journal} size={15} className="jv-nav__item-dot" />
      <span className="jv-truncate">{journal.title}</span>
    </Link>
  );
}

/** Insights lives in "Views": it is a way of looking at your own writing, not a
 *  Library entity to manage (docs/features/insights.md). Its own `{ tab, period }`
 *  search differs from the timeline `NavItem` contract, so it is a small
 *  standalone link like `AllJournalsItem`. */
function InsightsNavItem({ onNavigate }: { onNavigate?: () => void }) {
  const matchRoute = useMatchRoute();
  const selected = Boolean(matchRoute({ to: "/insights" }));
  return (
    <Link
      to="/insights"
      search={{ tab: "overview", period: 30 }}
      onClick={onNavigate}
      className={cx("jv-nav__item", selected && "is-selected")}
      aria-current={selected ? "page" : undefined}
    >
      <ChartNoAxesCombined aria-hidden="true" size={16} />
      <span className="jv-truncate">Insights</span>
    </Link>
  );
}

/** Opens the Journals screen — the only route to archived journals and to
 *  creating or managing any journal. */
function AllJournalsItem({ onNavigate }: { onNavigate?: () => void }) {
  const matchRoute = useMatchRoute();
  const selected = Boolean(matchRoute({ to: "/journals" }));
  return (
    <Link
      to="/journals"
      search={{ q: "" }}
      onClick={onNavigate}
      className={cx("jv-nav__item", selected && "is-selected")}
      aria-current={selected ? "page" : undefined}
    >
      <Library aria-hidden="true" size={16} />
      <span className="jv-truncate">All journals</span>
    </Link>
  );
}

const THEMES: Array<{ mode: ThemeMode; label: string; icon: ReactNode }> = [
  {
    mode: "light",
    label: "Light theme",
    icon: <Sun aria-hidden="true" />,
  },
  {
    mode: "dark",
    label: "Dark theme",
    icon: <Moon aria-hidden="true" />,
  },
  {
    mode: "system",
    label: "Match system theme",
    icon: <Monitor aria-hidden="true" />,
  },
];

function ThemeControl() {
  const theme = useTheme();
  return (
    <ToggleGroup
      spacing={0}
      variant="outline"
      size="sm"
      className="jv-theme-control"
      aria-label="Theme"
      value={[theme.mode]}
      onValueChange={([next]) => {
        // A group with one selectable option never emits an empty value here,
        // but guard anyway: deselecting the current theme means nothing.
        if (next) theme.set(next as ThemeMode);
      }}
    >
      {THEMES.map((option) => (
        <ToggleGroupItem
          key={option.mode}
          value={option.mode}
          aria-label={option.label}
          title={option.label}
        >
          {option.icon}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}
