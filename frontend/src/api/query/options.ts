import {
  infiniteQueryOptions,
  keepPreviousData,
  queryOptions,
} from "@tanstack/react-query";
import { api } from "../client/api";
import { retryTransient } from "../client/errors";
import {
  normalizeMomentFilters,
  queryKeys,
  type CalendarFilters,
  type MediaFilters,
  type MomentFilters,
} from "./keys";

export const currentUserQuery = () =>
  queryOptions({
    queryKey: queryKeys.me,
    queryFn: () => api.me(),
    staleTime: 60_000,
    retry: false,
  });

export const userSettingsQuery = () =>
  queryOptions({
    queryKey: queryKeys.userSettings,
    queryFn: () => api.userSettings(),
    staleTime: 60_000,
    retry: false,
  });
export const instanceConfigQuery = () =>
  queryOptions({
    queryKey: queryKeys.instanceConfig,
    queryFn: () => api.instanceConfig(),
    staleTime: 3_600_000,
    retry: false,
  });
export const adminUsersQuery = () =>
  queryOptions({
    queryKey: queryKeys.adminUsers,
    queryFn: () => api.adminUsers(),
    staleTime: 30_000,
    retry: false,
  });

export const journalsQuery = () =>
  queryOptions({
    queryKey: queryKeys.journals,
    queryFn: () => api.journals(),
    staleTime: 60_000,
  });
export const moodsQuery = () =>
  queryOptions({
    queryKey: queryKeys.moods,
    queryFn: () => api.moods(),
    staleTime: 300_000,
  });
export const moodGroupsQuery = () =>
  queryOptions({
    queryKey: queryKeys.moodGroups,
    queryFn: () => api.moodGroups(),
    staleTime: 300_000,
  });
export const peopleQuery = () =>
  queryOptions({
    queryKey: queryKeys.people,
    queryFn: () => api.people(),
    staleTime: 300_000,
  });
export const personGroupsQuery = () =>
  queryOptions({
    queryKey: queryKeys.personGroups,
    queryFn: () => api.personGroups(),
    staleTime: 300_000,
  });
export const tagsQuery = () =>
  queryOptions({ queryKey: queryKeys.tags, queryFn: () => api.tags() });
export const activitiesQuery = () =>
  queryOptions({
    queryKey: queryKeys.activities,
    queryFn: () => api.activities(),
    staleTime: 300_000,
  });
export const activityGroupsQuery = () =>
  queryOptions({
    queryKey: queryKeys.activityGroups,
    queryFn: () => api.activityGroups(),
    staleTime: 300_000,
  });
export const goalsQuery = () =>
  queryOptions({
    queryKey: queryKeys.goals,
    queryFn: () => api.goals(),
    staleTime: 300_000,
  });
export const goalCategoriesQuery = () =>
  queryOptions({
    queryKey: queryKeys.goalCategories,
    queryFn: () => api.goalCategories(),
    staleTime: 300_000,
  });
/** One goal's completion history, newest period first. Fetched on demand when
 *  the history dialog opens; short stale window so a revisit reflects a recent
 *  toggle. */
export const goalLogsQuery = (goalId: string) =>
  queryOptions({
    queryKey: queryKeys.goalLogs(goalId),
    queryFn: () => api.goalLogs(goalId),
    staleTime: 60_000,
  });
export const versionInfoQuery = () =>
  queryOptions({
    queryKey: queryKeys.versionInfo,
    queryFn: () => api.versionInfo(),
    staleTime: 60_000,
    // Retry only genuine blips; a 403 (not an admin) is an answer, not a spinner.
    retry: retryTransient,
  });
export const versionCheckEnabledQuery = () =>
  queryOptions({
    queryKey: queryKeys.versionCheckEnabled,
    queryFn: () => api.versionCheckEnabled(),
    staleTime: 60_000,
    retry: retryTransient,
  });
export const licenseInfoQuery = () =>
  queryOptions({
    queryKey: queryKeys.licenseInfo,
    queryFn: () => api.licenseInfo(),
    staleTime: 60_000,
    // A 404 is the expected "no license registered" state and a 403/501 is a
    // capability answer — none should delay the registration form. A 5xx or a
    // dropped connection still gets the standard couple of retries.
    retry: retryTransient,
  });
export const integrationStatusQuery = () =>
  queryOptions({
    queryKey: queryKeys.integrationStatus("immich"),
    queryFn: () => api.integrationStatus(),
    retry: false,
  });
/**
 * The connected Immich library, one page at a time for the editor picker.
 * `retry: false` because a 400 (not connected) or 401 (stale key) is an answer
 * the picker renders a reconnect state from, not a transient failure to spin
 * on. `staleTime` sits well under the 24h thumbnail-URL TTL so reopening the
 * picker in a session reuses pages rather than refetching; `gcTime` keeps the
 * loaded pages and scroll position across a close/reopen.
 */
export const immichAssetsInfiniteQuery = (pageSize = 100) =>
  infiniteQueryOptions({
    queryKey: [...queryKeys.immichAssets, pageSize] as const,
    queryFn: ({ pageParam }) =>
      api.immichAssets({ page: pageParam, limit: pageSize }),
    initialPageParam: 1,
    getNextPageParam: (lastPage) =>
      lastPage.has_more ? lastPage.page + 1 : undefined,
    staleTime: 5 * 60_000,
    gcTime: 30 * 60_000,
    retry: false,
  });
/**
 * The connected Immich instance's detected people, page by page, for the
 * Library → People import dialog. Keyed by the trimmed `search` term so typing
 * starts a fresh query rather than mutating the current one. `retry: false` for
 * the same reason as the asset query — a 400/401 is a reconnect answer, not a
 * blip.
 */
export const immichPeopleInfiniteQuery = (search: string, pageSize = 100) =>
  infiniteQueryOptions({
    queryKey: [...queryKeys.immichPeople(search.trim()), pageSize] as const,
    queryFn: ({ pageParam }) =>
      api.immichPeople({
        page: pageParam,
        limit: pageSize,
        ...(search.trim() ? { search: search.trim() } : {}),
      }),
    initialPageParam: 1,
    getNextPageParam: (lastPage) =>
      lastPage.has_more ? lastPage.page + 1 : undefined,
    staleTime: 60_000,
    retry: false,
  });
export const exportJobQuery = (id: string) =>
  queryOptions({
    queryKey: queryKeys.exportJob(id),
    queryFn: () => api.exportStatus(id),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "pending" || status === "running" ? 1000 : false;
    },
  });
export const importJobQuery = (id: string) =>
  queryOptions({
    queryKey: queryKeys.importJob(id),
    queryFn: () => api.importStatus(id),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "pending" || status === "running" ? 1000 : false;
    },
  });
/** Recent export jobs for the Settings → Export history. Polls every few
 *  seconds only while a listed job is still `pending`/`running`, so an
 *  export started here (or in another tab) keeps advancing without the
 *  per-job query, and settles to idle once nothing is active. */
export const exportJobsQuery = () =>
  infiniteQueryOptions({
    queryKey: queryKeys.exportJobs,
    queryFn: ({ pageParam }) => api.listExports({ ...(pageParam ?? {}) }),
    initialPageParam: undefined as
      | { cursor_created_at?: string; cursor_id?: string }
      | undefined,
    getNextPageParam: (page) =>
      page.next_cursor_created_at && page.next_cursor_id
        ? {
            cursor_created_at: page.next_cursor_created_at,
            cursor_id: page.next_cursor_id,
          }
        : undefined,
    staleTime: 15_000,
    refetchInterval: (query) =>
      query.state.data?.pages.some((page) =>
        page.items.some(
          (job) => job.status === "pending" || job.status === "running",
        ),
      )
        ? 3000
        : false,
  });
/** Recent import jobs for the Settings → Import history. Same polling rule as
 *  {@link exportJobsQuery}. */
export const importJobsQuery = () =>
  infiniteQueryOptions({
    queryKey: queryKeys.importJobs,
    queryFn: ({ pageParam }) => api.listImports({ ...(pageParam ?? {}) }),
    initialPageParam: undefined as
      | { cursor_created_at?: string; cursor_id?: string }
      | undefined,
    getNextPageParam: (page) =>
      page.next_cursor_created_at && page.next_cursor_id
        ? {
            cursor_created_at: page.next_cursor_created_at,
            cursor_id: page.next_cursor_id,
          }
        : undefined,
    staleTime: 15_000,
    refetchInterval: (query) =>
      query.state.data?.pages.some((page) =>
        page.items.some(
          (job) => job.status === "pending" || job.status === "running",
        ),
      )
        ? 3000
        : false,
  });
/** A fresh signed download URL for a completed export. Enable only once the job
 *  reports `completed`; the signature is short-lived, so it is not cached. */
export const exportDownloadQuery = (id: string) =>
  queryOptions({
    queryKey: queryKeys.exportDownload(id),
    queryFn: () => api.signExportUrl(id),
    gcTime: 0,
    staleTime: 0,
    retry: false,
  });
export const tagSearchQuery = (q: string) =>
  queryOptions({
    queryKey: queryKeys.tagSearch(q),
    queryFn: () => api.searchTags(q),
    staleTime: 60_000,
  });
/**
 * Aggregate tag analytics (Journiv Plus, Supporter+). `retry: false` because a
 * 403/503 is a capability answer, not a transient failure — the caller renders
 * a locked state from it, never a spinner loop.
 */
export const tagAnalyticsQuery = () =>
  queryOptions({
    queryKey: queryKeys.tagAnalytics,
    queryFn: () => api.tagAnalytics(),
    staleTime: 300_000,
    retry: false,
  });
/** One tag's analytics over `days` (Journiv Plus, Supporter+). */
export const tagDetailAnalyticsQuery = (tagId: string, days: number) =>
  queryOptions({
    queryKey: queryKeys.tagDetailAnalytics(tagId, days),
    queryFn: () => api.tagDetailAnalytics(tagId, days),
    staleTime: 300_000,
    retry: false,
  });
/** The tag detail pane's moments preview. Signed thumbnail URLs expire, so it
 *  is cached briefly, matching `momentMediaQuery`. */
export const tagMomentsQuery = (tagId: string) =>
  queryOptions({
    queryKey: queryKeys.tagMoments(tagId),
    queryFn: () => api.tagMoments(tagId),
    staleTime: 60_000,
  });

/**
 * Insights analytics (Insights feature). All six are free (not Plus-gated).
 * A short `staleTime` keeps a revisit after writing an entry roughly current
 * even before the mutation-side `queryKeys.insights` invalidation lands;
 * `retry: 1` because a transient failure here is a pane-level StatusView, not a
 * spinner loop.
 */
export const writingStreakQuery = () =>
  queryOptions({
    queryKey: queryKeys.writingStreak,
    queryFn: () => api.writingStreak(),
    staleTime: 60_000,
    retry: 1,
  });
export const writingPatternsQuery = (days: number) =>
  queryOptions({
    queryKey: queryKeys.writingPatterns(days),
    queryFn: () => api.writingPatterns(days),
    staleTime: 60_000,
    retry: 1,
  });
export const productivityQuery = () =>
  queryOptions({
    queryKey: queryKeys.productivity,
    queryFn: () => api.productivityMetrics(),
    staleTime: 60_000,
    retry: 1,
  });
export const journalAnalyticsQuery = () =>
  queryOptions({
    queryKey: queryKeys.journalAnalytics,
    queryFn: () => api.journalAnalytics(),
    staleTime: 60_000,
    retry: 1,
  });
export const moodStatisticsQuery = (start: string, end: string) =>
  queryOptions({
    queryKey: queryKeys.moodStatistics(start, end),
    queryFn: () => api.moodStatistics(start, end),
    staleTime: 60_000,
    retry: 1,
  });
export const moodStreakQuery = () =>
  queryOptions({
    queryKey: queryKeys.moodStreak,
    queryFn: () => api.moodStreak(),
    staleTime: 60_000,
    retry: 1,
  });
/**
 * Accepted media formats. Server configuration, so it is cached hard — the
 * picker must reflect the backend's limits, never its own guess.
 */
export const mediaFormatsQuery = () =>
  queryOptions({
    queryKey: queryKeys.mediaFormats,
    queryFn: () => api.mediaFormats(),
    staleTime: 3_600_000,
  });
export const momentQuery = (id: string) =>
  queryOptions({
    queryKey: queryKeys.moment(id),
    queryFn: () => api.moment(id),
  });

/**
 * Journaling prompts (Prompts feature, docs/features/prompts.md). Free — not
 * Plus-gated. The library uses the API's offset-page continuation; every
 * browse filter is part of both the request and cache key. The daily prompt
 * is per-day and per-user, so a short stale window is enough and a save that
 * answers it invalidates `queryKeys.prompts`. `retry: 1` — a transient failure
 * here is a pane-level StatusView, never a spinner loop.
 */
export const PROMPT_LIBRARY_PAGE_SIZE = 24;
export const promptLibraryQuery = (filters: {
  category?: string;
  difficulty_level?: number;
  q?: string;
  min_minutes?: number;
  max_minutes?: number;
}) =>
  infiniteQueryOptions({
    queryKey: queryKeys.promptLibrary(filters),
    queryFn: ({ pageParam }) =>
      api.prompts({
        ...filters,
        limit: PROMPT_LIBRARY_PAGE_SIZE,
        offset: pageParam,
      }),
    initialPageParam: 0,
    getNextPageParam: (page) => page.next_offset ?? undefined,
    // Keep the filter controls mounted while the next server-filtered page is
    // loading; otherwise each keystroke would replace the search input with a
    // skeleton before the writer can finish their query.
    placeholderData: keepPreviousData,
    staleTime: 300_000,
    retry: 1,
  });
export const dailyPromptQuery = () =>
  queryOptions({
    queryKey: queryKeys.dailyPrompt,
    queryFn: () => api.dailyPrompt(),
    staleTime: 60_000,
    retry: 1,
  });
/** Per-writer prompt completion analytics. Mounted only by the prompt Insights
 * tab, so opening Discover never makes an analytics request. */
export const promptAnalyticsQuery = () =>
  queryOptions({
    queryKey: queryKeys.promptAnalytics,
    queryFn: () => api.promptAnalytics(),
    staleTime: 60_000,
    retry: 1,
  });
export const promptQuery = (id: string) =>
  queryOptions({
    queryKey: queryKeys.prompt(id),
    queryFn: () => api.prompt(id),
    staleTime: 300_000,
    retry: 1,
  });
/**
 * Full media for one Moment. The Moment response carries thumbnails only, so
 * this is a second, deliberately separate query: it must never block the entry
 * text from rendering.
 */
export const momentMediaQuery = (id: string) =>
  queryOptions({
    queryKey: queryKeys.momentMedia(id),
    queryFn: () => api.momentMedia(id),
    // Signed URLs expire. Keeping this short means an ordinary revisit
    // re-signs rather than rendering a dead URL.
    staleTime: 60_000,
  });
export const entryQuery = (id: string) =>
  queryOptions({ queryKey: queryKeys.entry(id), queryFn: () => api.entry(id) });
export const momentsQuery = (filters: MomentFilters) => {
  // `queryKeys.moments` normalises internally, so hand it the raw filters —
  // normalising twice would drop the entity-scope keys (`person_id` →
  // `person_ids`, which a second pass no longer recognises) and collapse every
  // scope onto the same cache key.
  const normalized = normalizeMomentFilters(filters);
  return infiniteQueryOptions({
    queryKey: queryKeys.moments(filters),
    queryFn: ({ pageParam }) =>
      api.moments({
        ...normalized,
        include_media: "thumbnails",
        include_drafts: false,
        include_empty: false,
        ...(pageParam ?? {}),
      }),
    initialPageParam: undefined as
      | { cursor_logged_at_utc?: string; cursor_id?: string }
      | undefined,
    getNextPageParam: (page) =>
      page.next_cursor_logged_at_utc && page.next_cursor_id
        ? {
            cursor_logged_at_utc: page.next_cursor_logged_at_utc,
            cursor_id: page.next_cursor_id,
          }
        : undefined,
  });
};
/**
 * Per-day summary for the calendar grid. Signed thumbnail URLs expire, so this
 * is cached briefly — an ordinary revisit re-signs rather than rendering a dead
 * URL, matching `momentMediaQuery`.
 */
export const momentCalendarQuery = (filters: CalendarFilters) =>
  queryOptions({
    queryKey: queryKeys.momentCalendar(filters),
    queryFn: () =>
      api.momentCalendar({
        start_date: filters.start,
        end_date: filters.end,
        ...(filters.journal_id ? { journal_id: filters.journal_id } : {}),
      }),
    staleTime: 60_000,
  });
/** Flat, paginated media across every moment — the Media grid. */
export const mediaLibraryQuery = (filters: MediaFilters) =>
  infiniteQueryOptions({
    queryKey: queryKeys.mediaLibrary(filters),
    queryFn: ({ pageParam }) =>
      api.mediaLibrary({
        ...(filters.journal_id ? { journal_id: filters.journal_id } : {}),
        ...(filters.media_type
          ? { media_type: filters.media_type as "image" | "video" | "audio" }
          : {}),
        ...(pageParam ?? {}),
      }),
    initialPageParam: undefined as
      | { cursor_logged_at_utc?: string; cursor_id?: string }
      | undefined,
    getNextPageParam: (page) =>
      page.next_cursor_logged_at_utc && page.next_cursor_id
        ? {
            cursor_logged_at_utc: page.next_cursor_logged_at_utc,
            cursor_id: page.next_cursor_id,
          }
        : undefined,
    staleTime: 60_000,
  });
