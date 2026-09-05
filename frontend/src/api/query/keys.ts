export type MomentFilters = {
  journal_id?: string;
  /** Entity scope — at most one is set at a time (docs/features/library.md "View
   *  moments"). Each resolves to the matching `GET /moments` filter: a single
   *  id passed as the backend's repeatable list param, or `goal_id` directly. */
  person_id?: string;
  tag_id?: string;
  activity_id?: string;
  mood_id?: string;
  goal_id?: string;
  search?: string;
  /** ISO `YYYY-MM-DD`. Used by the calendar's selected-day panel. */
  start_date?: string;
  end_date?: string;
};

export function normalizeMomentFilters(filters: MomentFilters) {
  return {
    ...(filters.journal_id ? { journal_id: filters.journal_id } : {}),
    ...(filters.person_id ? { person_ids: [filters.person_id] } : {}),
    ...(filters.tag_id ? { tag_ids: [filters.tag_id] } : {}),
    ...(filters.activity_id ? { activity_ids: [filters.activity_id] } : {}),
    ...(filters.mood_id ? { mood_ids: [filters.mood_id] } : {}),
    ...(filters.goal_id ? { goal_id: filters.goal_id } : {}),
    ...(filters.search?.trim() ? { search: filters.search.trim() } : {}),
    ...(filters.start_date ? { start_date: filters.start_date } : {}),
    ...(filters.end_date ? { end_date: filters.end_date } : {}),
  };
}

export type CalendarFilters = {
  journal_id?: string;
  start: string;
  end: string;
};
export type MediaFilters = { journal_id?: string; media_type?: string };

export function normalizeCalendarFilters(filters: CalendarFilters) {
  return {
    ...(filters.journal_id ? { journal_id: filters.journal_id } : {}),
    start_date: filters.start,
    end_date: filters.end,
  };
}

export function normalizeMediaFilters(filters: MediaFilters) {
  return {
    ...(filters.journal_id ? { journal_id: filters.journal_id } : {}),
    ...(filters.media_type ? { media_type: filters.media_type } : {}),
  };
}

export const queryKeys = {
  me: ["current-user"] as const,
  /** Preferences behind `/users/me/settings` — timezone, and the future
   *  Appearance / Journaling controls. Settings → Profile owns the timezone
   *  slice today; later pages read the same key. */
  userSettings: ["user-settings"] as const,
  /** Instance capability flags (`oidc_enabled`, `oidc_only`, …). Server
   *  configuration, cached hard. */
  instanceConfig: ["instance-config"] as const,
  adminUsers: ["admin", "users"] as const,
  journals: ["journals"] as const,
  moods: ["moods"] as const,
  moodGroups: ["mood-groups"] as const,
  people: ["people"] as const,
  personGroups: ["people-groups"] as const,
  tags: ["tags"] as const,
  activities: ["activities"] as const,
  activityGroups: ["activity-groups"] as const,
  goals: ["goals"] as const,
  goalCategories: ["goal-categories"] as const,
  /** Per-goal completion history. Nested under `["goals", id]` so invalidating
   *  goals by prefix also drops a goal's logs — a completion toggle changes
   *  both. Do not flatten to a sibling key. */
  goalLogs: (id: string) => ["goals", id, "logs"] as const,
  versionInfo: ["instance", "version"] as const,
  versionCheckEnabled: ["instance", "version", "enabled"] as const,
  licenseInfo: ["instance", "license"] as const,
  integrationStatus: (provider: string) =>
    ["integrations", provider, "status"] as const,
  /** The connected Immich library, browsed page by page in the editor picker.
   *  Not nested under `integrationStatus` — disconnect/reconnect invalidates
   *  both explicitly. */
  immichAssets: ["integrations", "immich", "assets"] as const,
  /** One Immich → Moment import job, polled until it settles. */
  immichImportJob: (id: string) =>
    ["integrations", "immich", "import-job", id] as const,
  /** A page-search of the connected Immich instance's detected people, keyed by
   *  the (trimmed) search term so each term is its own infinite query. */
  immichPeople: (search: string) =>
    ["integrations", "immich", "people", search] as const,
  /** People Immich's face index suggests for one moment. Nested under
   *  `["moment", id]` so a moment invalidation drops it too — same rule as
   *  `momentMedia`. Do not flatten to a sibling key. */
  immichPeopleSuggestions: (momentId: string) =>
    ["moment", momentId, "immich-people-suggestions"] as const,
  exportJob: (id: string) => ["export", id] as const,
  exportDownload: (id: string) => ["export", id, "signed"] as const,
  importJob: (id: string) => ["import", id] as const,
  tagSearch: (q: string) => ["tags", "search", q] as const,
  /** Aggregate tag analytics (Journiv Plus). */
  tagAnalytics: ["tags", "analytics"] as const,
  /** One tag's analytics over `days` (Journiv Plus). Nested under the tag so a
   *  rename/merge that invalidates `["tags"]` also drops it. */
  tagDetailAnalytics: (id: string, days: number) =>
    ["tags", id, "analytics", days] as const,
  /** Moments carrying one tag — the tag detail pane's preview list. */
  tagMoments: (id: string) => ["tags", id, "moments"] as const,
  /** Insights analytics. One prefix so an entry/mood mutation can drop the
   *  whole surface in a single `invalidateQueries`. */
  insights: ["insights"] as const,
  writingStreak: ["insights", "writing-streak"] as const,
  writingPatterns: (days: number) =>
    ["insights", "writing-patterns", days] as const,
  productivity: ["insights", "productivity"] as const,
  journalAnalytics: ["insights", "journals"] as const,
  moodStatistics: (start: string, end: string) =>
    ["insights", "mood", "statistics", start, end] as const,
  moodStreak: ["insights", "mood", "streak"] as const,
  mediaFormats: ["media-formats"] as const,
  /** Journaling prompts. One prefix so a future create/edit mutation (or the
   *  editor attaching a `prompt_id`) can drop the whole surface at once. */
  prompts: ["prompts"] as const,
  /** Offset pages for the system-prompt browser, scoped by all API filters. */
  promptLibrary: (filters: {
    category?: string;
    difficulty_level?: number;
    q?: string;
    min_minutes?: number;
    max_minutes?: number;
  }) => ["prompts", "library", filters] as const,
  /** Per-writer prompt completion analytics, mounted only on the Insights tab. */
  promptAnalytics: ["prompts", "analytics"] as const,
  /** Today's rotating prompt for the signed-in user (204 → none left today). */
  dailyPrompt: ["prompts", "daily"] as const,
  /** One prompt by id — the editor reads it to show the "written from" banner. */
  prompt: (id: string) => ["prompts", "item", id] as const,
  moments: (filters: MomentFilters) =>
    ["moments", normalizeMomentFilters(filters)] as const,
  momentCalendar: (filters: CalendarFilters) =>
    ["moment-calendar", normalizeCalendarFilters(filters)] as const,
  mediaLibrary: (filters: MediaFilters) =>
    ["media-library", normalizeMediaFilters(filters)] as const,
  moment: (id: string) => ["moment", id] as const,
  /**
   * Deliberately nested under `moment(id)`. Invalidating the Moment — which the
   * editor already does after a save — also invalidates its media by prefix
   * match, so media cannot go stale behind a fresh Moment. Do not flatten this
   * to a sibling key such as ["moment-media", id].
   */
  momentMedia: (id: string) => ["moment", id, "media"] as const,
  entry: (id: string) => ["entry", id] as const,
  allMoments: ["moments"] as const,
  allMomentCalendars: ["moment-calendar"] as const,
  allMediaLibraries: ["media-library"] as const,
};
