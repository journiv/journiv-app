import { infiniteQueryOptions, queryOptions } from "@tanstack/react-query";
import { api } from "../client/api";
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
  });
export const licenseInfoQuery = () =>
  queryOptions({
    queryKey: queryKeys.licenseInfo,
    queryFn: () => api.licenseInfo(),
  });
export const integrationStatusQuery = () =>
  queryOptions({
    queryKey: queryKeys.integrationStatus("immich"),
    queryFn: () => api.integrationStatus(),
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
