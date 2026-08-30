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
 *  overlay with real routes (DESIGN.md §23): the route renders the ordinary
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
 * associated with one Library entity (DESIGN.md §24). At most one is meaningful
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
): { q: string; draft?: string } => ({
  ...timelineSearch(search),
  draft:
    typeof search.draft === "string" && UUID.test(search.draft)
      ? search.draft
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
    returnTo:
      typeof s.returnTo === "string" &&
      s.returnTo.startsWith("/") &&
      !s.returnTo.startsWith("//")
        ? s.returnTo
        : "/timeline",
  }),
  component: LoginPage,
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
 *  full-screen flow on compact widths (DESIGN.md §23). `/settings` redirects to
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
 *  not open a third pane (DESIGN.md §24). So neither route carries `detailPane`
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
    settingsTagsRedirectRoute,
    libraryTagsRoute,
    libraryTagRoute,
    settingsPeopleRoute,
    settingsMoodsRoute,
    settingsActivitiesRoute,
    settingsGoalsRoute,
    settingsIntegrationsRoute,
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
     *  the Settings modal without parsing the pathname (DESIGN.md §23). */
    settings?:
      | "index"
      | "profile"
      | "security"
      | "appearance"
      | "users"
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
