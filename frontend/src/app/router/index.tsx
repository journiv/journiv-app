import {
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  type RouterHistory,
  redirect,
} from "@tanstack/react-router";
import { BookOpenText, Compass, Library, Loader2 } from "lucide-react";
import { lazy, Suspense } from "react";
import { sessionStore } from "../../api/auth/session";
import { StatusView } from "../../components/journiv/StatusView";
import { LoginPage } from "../../features/auth/LoginPage";
import { OidcFinishPage } from "../../features/auth/OidcFinishPage";
import { SignUpPage } from "../../features/auth/SignUpPage";
import { safeReturnTo } from "../../features/auth/returnTo";
import { AppShell } from "../../features/shell/AppShell";
import { Workspace } from "../../features/shell/Workspace";

const ReaderPage = lazy(async () => ({
  default: (await import("../../features/reader/ReaderPage")).ReaderPage,
}));
const EntryEditorPage = lazy(async () => ({
  default: (await import("../../features/editor/EntryEditorPage"))
    .EntryEditorPage,
}));
const JournalsPage = lazy(async () => ({
  default: (await import("../../features/journals/JournalsPage")).JournalsPage,
}));
const PeoplePage = lazy(async () => ({
  default: (await import("../../features/library/PeoplePage")).PeoplePage,
}));
const ActivitiesPage = lazy(async () => ({
  default: (await import("../../features/library/ActivitiesPage"))
    .ActivitiesPage,
}));
const GoalsPage = lazy(async () => ({
  default: (await import("../../features/library/GoalsPage")).GoalsPage,
}));
const MoodsPage = lazy(async () => ({
  default: (await import("../../features/library/MoodsPage")).MoodsPage,
}));
const TagsPage = lazy(async () => ({
  default: (await import("../../features/library/TagsPage")).TagsPage,
}));
const TagDetailPage = lazy(async () => ({
  default: (await import("../../features/library/TagDetailPage")).TagDetailPage,
}));
const InsightsPage = lazy(async () => ({
  default: (await import("../../features/insights/InsightsPage")).InsightsPage,
}));
const PromptLibraryPage = lazy(async () => ({
  default: (await import("../../features/prompts/PromptLibraryPage"))
    .PromptLibraryPage,
}));

function DetailLoading({ label }: { label: string }) {
  return (
    <div className="jv-pane-status" role="status">
      <StatusView
        icon={<Loader2 className="jv-spin" size={20} />}
        title={label}
      />
    </div>
  );
}

function NothingSelected() {
  return (
    <div className="jv-pane-status">
      <StatusView
        icon={<BookOpenText size={22} />}
        title="Nothing selected"
        description="Choose a moment from the timeline to read it."
      />
    </div>
  );
}

function JournalsIndex() {
  return (
    <>
      <Suspense fallback={<DetailLoading label="Loading journals…" />}>
        <JournalsPage />
      </Suspense>
      <section className="jv-shell__page" aria-label="Journal detail">
        <div className="jv-pane-status">
          <StatusView
            icon={<Library size={22} />}
            title="Your journals"
            description="Open a journal to browse its moments, or create a new one."
          />
        </div>
      </section>
    </>
  );
}

/** The inert Journiv view painted behind the Settings modal. Settings is an
 *  overlay with real routes (docs/features/settings.md): the route renders the ordinary
 *  Timeline workspace and `AppShell` mounts the modal on top when a
 *  `staticData.settings` route matches. */
function SettingsBackground() {
  return (
    <Workspace>
      <NothingSelected />
    </Workspace>
  );
}

function ReaderDetail() {
  return (
    <Workspace>
      <Suspense fallback={<DetailLoading label="Loading entry…" />}>
        <ReaderPage />
      </Suspense>
    </Workspace>
  );
}

function EditorDetail() {
  return (
    <Workspace>
      <Suspense fallback={<DetailLoading label="Loading editor…" />}>
        <EntryEditorPage />
      </Suspense>
    </Workspace>
  );
}

const isMonth = (v: unknown): v is string =>
  typeof v === "string" && /^\d{4}-\d{2}$/.test(v);
const isDay = (v: unknown): v is string =>
  typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v);

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
/** An entity-scope id from the URL. Kept loose — it is only ever matched against
 *  a cached entity id and forwarded to `GET /moments`, never used as a storage
 *  key (unlike `draft`) — but length-capped so a junk link cannot bloat state. */
const asId = (v: unknown): string | undefined =>
  typeof v === "string" && v.length > 0 && v.length <= 64 ? v : undefined;

/**
 * Shared search for the list-pane routes. `view` selects the middle pane's mode
 * (list / calendar / media); `month` and `date` are the calendar's viewport and
 * selected day. They ride on the reader routes too so opening a moment from the
 * calendar or grid keeps that view mounted beside it.
 *
 * `person` / `tag` / `activity` / `mood` / `goal` scope the list to moments
 * associated with one Library entity (docs/features/library.md). At most one is meaningful
 * at a time; `useMomentScope` reads the first one set. They ride the reader
 * routes too, so opening a moment keeps the scope mounted beside it.
 */
const timelineSearch = (
  search: Record<string, unknown>,
): {
  q: string;
  view?: "calendar" | "media";
  month?: string;
  date?: string;
  person?: string;
  tag?: string;
  activity?: string;
  mood?: string;
  goal?: string;
} => ({
  q: typeof search.q === "string" ? search.q : "",
  view:
    search.view === "calendar" || search.view === "media"
      ? search.view
      : undefined,
  month: isMonth(search.month) ? search.month : undefined,
  date: isDay(search.date) ? search.date : undefined,
  person: asId(search.person),
  tag: asId(search.tag),
  activity: asId(search.activity),
  mood: asId(search.mood),
  goal: asId(search.goal),
});

/**
 * A new entry's local draft id, so a reload finds the writing it left behind.
 *
 * Only the two "new" routes carry it — an existing entry keys its draft on its
 * own id and needs nothing in the URL. The shape is validated because this
 * value becomes an IndexedDB key, and an unchecked one would let a crafted link
 * point the editor at an arbitrary record.
 */
const editorSearch = (
  search: Record<string, unknown>,
): { q: string; draft?: string; prompt?: string } => ({
  ...timelineSearch(search),
  draft:
    typeof search.draft === "string" && UUID.test(search.draft)
      ? search.draft
      : undefined,
  // A prompt to start the entry from (docs/features/prompts.md). The id becomes
  // a query key and, on save, the Moment's `prompt_id`, so it is shape-checked
  // for the same reason `draft` is.
  prompt:
    typeof search.prompt === "string" && UUID.test(search.prompt)
      ? search.prompt
      : undefined,
});

/** Marks routes that own the detail pane. The shell reads this instead of
 *  parsing the pathname, so adding a detail route needs no shell change. */
const detailPane = { pane: "detail" } as const;

const rootRoute = createRootRoute({
  component: () => <Outlet />,
  notFoundComponent: () => (
    <main className="jv-route-not-found">
      <StatusView
        icon={<Compass size={22} />}
        title="Page not found"
        description="The Journiv page you requested does not exist."
      />
    </main>
  ),
});
const protectedRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: "protected",
  beforeLoad: ({ location }) => {
    if (!sessionStore.read())
      throw redirect({ to: "/login", search: { returnTo: location.href } });
  },
  component: AppShell,
});
const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  validateSearch: (s: Record<string, unknown>) => ({
    returnTo: safeReturnTo(s.returnTo),
  }),
  component: LoginPage,
});
const signupRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/signup",
  validateSearch: (s: Record<string, unknown>) => ({
    returnTo: safeReturnTo(s.returnTo),
  }),
  component: SignUpPage,
});
const oidcFinishRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/oidc-finish",
  validateSearch: (s: Record<string, unknown>) => ({
    ticket:
      typeof s.ticket === "string" &&
      s.ticket.length > 0 &&
      s.ticket.length <= 512
        ? s.ticket
        : undefined,
  }),
  component: OidcFinishPage,
});
const indexRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: "/",
  beforeLoad: () => {
    throw redirect({ to: "/timeline", search: { q: "" } });
  },
});
const timelineRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: "/timeline",
  validateSearch: timelineSearch,
  component: () => (
    <Workspace>
      <NothingSelected />
    </Workspace>
  ),
});
const timelineNewRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: "/timeline/new",
  validateSearch: editorSearch,
  staticData: detailPane,
  component: EditorDetail,
});
const timelineEditRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: "/timeline/$momentId/edit",
  validateSearch: timelineSearch,
  staticData: detailPane,
  component: EditorDetail,
});
const timelineMomentRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: "/timeline/$momentId",
  validateSearch: timelineSearch,
  staticData: detailPane,
  component: ReaderDetail,
});
/** Settings routes. Real URLs, rendered as a centred modal on desktop and a
 *  full-screen flow on compact widths (docs/features/settings.md). `/settings` redirects to
 *  Profile on desktop and shows the section list on compact — the one place a
 *  single `matchMedia` read at navigation time is allowed (it is not reactive
 *  breakpoint state). The incoming `state.settingsFrom` is carried through the
 *  redirect so closing returns to the originating route. */
const settingsIndexRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: "/settings",
  validateSearch: timelineSearch,
  staticData: { settings: "index" },
  beforeLoad: ({ location, search }) => {
    const desktop =
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(min-width: 1101px)").matches;
    // When Settings was opened from within the app, `state.settingsFrom` carries
    // the return target. `redirect()` does not forward history state, so let
    // those land on `/settings` and have `SettingsModal` do the desktop hop
    // (which preserves the state). A stateless direct hit redirects here.
    if (desktop && !location.state.settingsFrom)
      throw redirect({ to: "/settings/profile", search });
  },
  component: SettingsBackground,
});
const settingsProfileRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: "/settings/profile",
  validateSearch: timelineSearch,
  staticData: { settings: "profile" },
  component: SettingsBackground,
});
const settingsSecurityRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: "/settings/security",
  validateSearch: timelineSearch,
  staticData: { settings: "security" },
  component: SettingsBackground,
});
const settingsAppearanceRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: "/settings/appearance",
  validateSearch: timelineSearch,
  staticData: { settings: "appearance" },
  component: SettingsBackground,
});
const settingsUsersRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: "/settings/admin/users",
  validateSearch: timelineSearch,
  staticData: { settings: "users" },
  component: SettingsBackground,
});
const settingsUpdatesLicenseRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: "/settings/admin/updates-license",
  validateSearch: timelineSearch,
  staticData: { settings: "updatesLicense" },
  component: SettingsBackground,
});
/** Tags graduated from the legacy `/settings/journaling/*` prefix to its own
 *  Library workspace. Keep the old URL working. */
const settingsTagsRedirectRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: "/settings/journaling/tags",
  beforeLoad: () => {
    throw redirect({ to: "/library/tags", search: { q: "" } });
  },
});
/** The list and the detail are both wide workspaces spanning the two content
 *  columns; opening a tag *pushes* to the detail (marketplace-style), it does
 *  not open a third pane (docs/features/library.md). So neither route carries `detailPane`
 *  and each renders one component. */
const libraryTagsRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: "/library/tags",
  validateSearch: timelineSearch,
  component: () => (
    <Suspense fallback={<DetailLoading label="Loading Tags…" />}>
      <TagsPage />
    </Suspense>
  ),
});
const libraryTagRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: "/library/tags/$tagId",
  validateSearch: timelineSearch,
  component: () => (
    <Suspense fallback={<DetailLoading label="Loading tag…" />}>
      <TagDetailPage />
    </Suspense>
  ),
});
/** Insights is a wide analysis workspace like Library, but read-only: one
 *  component, no detail pane, no `Workspace`. `tab` selects the Overview / Mood /
 *  Journals panel; `period` is the shared "Trend period" for the range-based
 *  charts. Both ride in the URL so a tab switch keeps the period and a link is
 *  shareable (docs/features/insights.md). */
const INSIGHTS_PERIODS = [7, 30, 90, 365] as const;
type InsightsPeriod = (typeof INSIGHTS_PERIODS)[number];
const insightsSearch = (
  search: Record<string, unknown>,
): { tab: "overview" | "mood" | "journals"; period: InsightsPeriod } => ({
  tab:
    search.tab === "mood" || search.tab === "journals"
      ? search.tab
      : "overview",
  period: INSIGHTS_PERIODS.includes(search.period as InsightsPeriod)
    ? (search.period as InsightsPeriod)
    : 30,
});
const promptLibrarySearch = (
  search: Record<string, unknown>,
): { tab: "discover" | "insights" } => ({
  tab: search.tab === "insights" ? "insights" : "discover",
});
const insightsRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: "/insights",
  validateSearch: insightsSearch,
  component: () => (
    <Suspense fallback={<DetailLoading label="Loading Insights…" />}>
      <InsightsPage />
    </Suspense>
  ),
});
/** The prompt library is a wide Library-style workspace: one component, no
 *  detail pane. Choosing a prompt opens `/timeline/new?prompt=` rather than a
 *  third pane (docs/features/prompts.md). */
const libraryPromptsRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: "/library/prompts",
  validateSearch: promptLibrarySearch,
  component: () => (
    <Suspense fallback={<DetailLoading label="Loading Prompts…" />}>
      <PromptLibraryPage />
    </Suspense>
  ),
});
const settingsPeopleRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: "/settings/journaling/people",
  validateSearch: timelineSearch,
  component: () => (
    <Suspense fallback={<DetailLoading label="Loading People…" />}>
      <PeoplePage />
    </Suspense>
  ),
});
const settingsMoodsRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: "/settings/journaling/moods",
  validateSearch: timelineSearch,
  component: () => (
    <Suspense fallback={<DetailLoading label="Loading Moods…" />}>
      <MoodsPage />
    </Suspense>
  ),
});
const settingsActivitiesRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: "/settings/journaling/activities",
  validateSearch: timelineSearch,
  component: () => (
    <Suspense fallback={<DetailLoading label="Loading Activities…" />}>
      <ActivitiesPage />
    </Suspense>
  ),
});
const settingsGoalsRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: "/settings/journaling/goals",
  validateSearch: timelineSearch,
  component: () => (
    <Suspense fallback={<DetailLoading label="Loading Goals…" />}>
      <GoalsPage />
    </Suspense>
  ),
});
const settingsIntegrationsRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: "/settings/integrations",
  validateSearch: timelineSearch,
  staticData: { settings: "integrations" },
  component: SettingsBackground,
});
/** The provider detail drill-down. Same `settings` section as the catalogue, so
 *  the modal chrome and the "Providers" nav item are unchanged across the
 *  drill-down — only the content pane swaps (docs/features/settings.md). A single-segment
 *  param, not a splat, so route matching stays unaffected elsewhere. Only
 *  `immich` is a real provider; an unknown or removed one (a stale bookmark) is
 *  redirected to the catalogue rather than 404ing. */
const settingsIntegrationProviderRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: "/settings/integrations/$provider",
  validateSearch: timelineSearch,
  staticData: { settings: "integrations" },
  beforeLoad: ({ params }) => {
    if (params.provider !== "immich")
      throw redirect({ to: "/settings/integrations", search: { q: "" } });
  },
  component: SettingsBackground,
});
const settingsImportRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: "/settings/data/import",
  validateSearch: timelineSearch,
  staticData: { settings: "import" },
  component: SettingsBackground,
});
const settingsExportRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: "/settings/data/export",
  validateSearch: timelineSearch,
  staticData: { settings: "export" },
  component: SettingsBackground,
});
const settingsHelpRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: "/settings/support/help",
  validateSearch: timelineSearch,
  staticData: { settings: "help" },
  component: SettingsBackground,
});
const settingsAboutRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: "/settings/support/about",
  validateSearch: timelineSearch,
  staticData: { settings: "about" },
  component: SettingsBackground,
});
const journalsIndexRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: "/journals",
  validateSearch: timelineSearch,
  component: JournalsIndex,
});
const journalRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: "/journals/$journalId",
  validateSearch: timelineSearch,
  component: () => (
    <Workspace>
      <NothingSelected />
    </Workspace>
  ),
});
const journalNewRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: "/journals/$journalId/new",
  validateSearch: editorSearch,
  staticData: detailPane,
  component: EditorDetail,
});
const journalEditRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: "/journals/$journalId/$momentId/edit",
  validateSearch: timelineSearch,
  staticData: detailPane,
  component: EditorDetail,
});
const journalMomentRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: "/journals/$journalId/$momentId",
  validateSearch: timelineSearch,
  staticData: detailPane,
  component: ReaderDetail,
});
const routeTree = rootRoute.addChildren([
  loginRoute,
  signupRoute,
  oidcFinishRoute,
  protectedRoute.addChildren([
    indexRoute,
    timelineRoute,
    timelineNewRoute,
    timelineEditRoute,
    timelineMomentRoute,
    settingsIndexRoute,
    settingsProfileRoute,
    settingsSecurityRoute,
    settingsAppearanceRoute,
    settingsUsersRoute,
    settingsUpdatesLicenseRoute,
    settingsTagsRedirectRoute,
    libraryTagsRoute,
    libraryTagRoute,
    libraryPromptsRoute,
    insightsRoute,
    settingsPeopleRoute,
    settingsMoodsRoute,
    settingsActivitiesRoute,
    settingsGoalsRoute,
    settingsIntegrationsRoute,
    settingsIntegrationProviderRoute,
    settingsImportRoute,
    settingsExportRoute,
    settingsHelpRoute,
    settingsAboutRoute,
    journalsIndexRoute,
    journalRoute,
    journalNewRoute,
    journalEditRoute,
    journalMomentRoute,
  ]),
]);
export function createAppRouter(history?: RouterHistory) {
  return createRouter({
    routeTree,
    defaultPreload: "intent",
    ...(history ? { history } : {}),
  });
}

export const router = createAppRouter();
declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
  interface StaticDataRouteOption {
    pane?: "detail";
    /** Which Settings surface this route shows. `AppShell` reads it to mount
     *  the Settings modal without parsing the pathname (docs/features/settings.md). */
    settings?:
      | "index"
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
  }
  interface HistoryState {
    /** Full href of the route Settings was opened from, so closing can return
     *  there. Absent on a direct deep link — close then falls back to
     *  `/timeline`. */
    settingsFrom?: string;
  }
}
