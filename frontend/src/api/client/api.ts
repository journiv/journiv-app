import {
  archiveJournalApiV1JournalsJournalIdArchivePost,
  archivePersonApiV1PeoplePersonIdDelete,
  bulkAddTagsToMomentApiV1MomentsMomentIdTagsPost,
  connectApiV1IntegrationsConnectPost,
  createActivityApiV1ActivitiesPost,
  createActivityGroupApiV1ActivityGroupsPost,
  createDraftEntryApiV1EntriesDraftPost,
  createExportApiV1ExportPost,
  createGoalApiV1GoalsPost,
  createGoalCategoryApiV1GoalCategoriesPost,
  createJournalApiV1JournalsPost,
  createMomentApiV1MomentsPost,
  createMoodApiV1MoodsPost,
  createMoodGroupApiV1MoodsGroupsPost,
  createPersonApiV1PeoplePost,
  createPersonGroupApiV1PeopleGroupsPost,
  createTagApiV1TagsPost,
  createUserApiV1AdminUsersPost,
  deleteActivityApiV1ActivitiesActivityIdDelete,
  deleteActivityGroupApiV1ActivityGroupsGroupIdDelete,
  deleteEntryApiV1EntriesEntryIdDelete,
  deleteGoalCategoryApiV1GoalCategoriesCategoryIdDelete,
  deleteGoalPermanentlyApiV1GoalsGoalIdDelete,
  deleteJournalApiV1JournalsJournalIdDelete,
  deleteMediaApiV1MediaMediaIdDelete,
  deleteMomentApiV1MomentsMomentIdDelete,
  deleteMoodApiV1MoodsMoodIdDelete,
  deleteMoodGroupApiV1MoodsGroupsGroupIdDelete,
  deletePersonGroupApiV1PeopleGroupsGroupIdDelete,
  deleteTagApiV1TagsTagIdDelete,
  deleteUnusedTagsApiV1TagsUnusedDelete,
  deleteUserApiV1AdminUsersUserIdDelete,
  disconnectApiV1IntegrationsProviderDisconnectDelete,
  fetchWeatherApiV1WeatherFetchPost,
  getActivitiesApiV1ActivitiesGet,
  getActivityGroupsApiV1ActivityGroupsGet,
  getAllMoodsApiV1MoodsGet,
  getCurrentUserInfoApiV1UsersMeGet,
  getCurrentUserSettingsApiV1UsersMeSettingsGet,
  getEntryApiV1EntriesEntryIdGet,
  getExportStatusApiV1ExportJobIdGet,
  getGoalCategoriesApiV1GoalCategoriesGet,
  getGoalLogsApiV1GoalsGoalIdLogsGet,
  getGoalsApiV1GoalsGet,
  getImmichPeopleSuggestionsApiV1MomentsMomentIdPeopleSuggestionsImmichPost,
  getImportJobStatusApiV1MediaImportJobsJobIdGet,
  getImportStatusApiV1ImportJobIdGet,
  getInstanceConfigApiV1InstanceConfigGet,
  getLicenseInfoApiV1InstanceLicenseInfoGet,
  getMediaLibraryApiV1MediaGet,
  getMomentApiV1MomentsMomentIdGet,
  getMomentCalendarApiV1MomentsCalendarGet,
  getMomentMediaApiV1MomentsMomentIdMediaGet,
  getMomentsApiV1MomentsGet,
  getMomentsByTagApiV1TagsTagIdMomentsGet,
  getMoodGroupsApiV1MoodsGroupsGet,
  getPeopleApiV1PeopleGet,
  getPersonGroupsApiV1PeopleGroupsGet,
  getStatusApiV1IntegrationsProviderStatusGet,
  getSupportedFormatsApiV1MediaFormatsGet,
  getTagAnalyticsApiV1TagsAnalyticsGet,
  getTagDetailAnalyticsApiV1TagsTagIdAnalyticsGet,
  getUserJournalsApiV1JournalsGet,
  getUserTagsApiV1TagsGet,
  getVersionInfoApiV1InstanceVersionInfoGet,
  importFromImmichAsyncApiV1MediaImportFromImmichAsyncPost,
  importImmichPeopleApiV1IntegrationsImmichPeopleImportPost,
  listAssetsApiV1IntegrationsProviderAssetsGet,
  listImmichPeopleApiV1IntegrationsImmichPeopleGet,
  listUsersApiV1AdminUsersGet,
  loginApiV1AuthLoginPost,
  mergePeopleApiV1PeopleSourceIdMergeTargetIdPost,
  mergeTagsApiV1TagsSourceIdMergeTargetIdPost,
  oidcExchangeApiV1AuthOidcExchangePost,
  refreshTokenApiV1AuthRefreshPost,
  registerApiV1AuthRegisterPost,
  removePersonProfileImageApiV1PeoplePersonIdProfileImageDelete,
  removeTagFromMomentApiV1MomentsMomentIdTagsTagIdDelete,
  reorderJournalsApiV1JournalsReorderPut,
  replaceMomentPeopleApiV1MomentsMomentIdPeoplePut,
  reverseGeocodeApiV1LocationReversePost,
  searchLocationApiV1LocationSearchPost,
  searchTagsApiV1TagsSearchGet,
  signExportUrlApiV1ExportJobIdSignGet,
  toggleFavoriteApiV1JournalsJournalIdFavoritePost,
  triggerSyncApiV1IntegrationsProviderSyncPost,
  unarchiveJournalApiV1JournalsJournalIdUnarchivePost,
  updateActivityApiV1ActivitiesActivityIdPut,
  updateActivityGroupApiV1ActivityGroupsGroupIdPut,
  updateCurrentUserApiV1UsersMePut,
  updateCurrentUserSettingsApiV1UsersMeSettingsPut,
  updateGoalApiV1GoalsGoalIdPut,
  updateGoalCategoryApiV1GoalCategoriesCategoryIdPut,
  updateJournalApiV1JournalsJournalIdPut,
  updateMomentApiV1MomentsMomentIdPut,
  updateMoodApiV1MoodsMoodIdPut,
  updateMoodGroupApiV1MoodsGroupsGroupIdPut,
  updatePersonApiV1PeoplePersonIdPut,
  updatePersonGroupApiV1PeopleGroupsGroupIdPut,
  updateSettingsApiV1IntegrationsProviderSettingsPut,
  updateTagApiV1TagsTagIdPut,
  updateUserApiV1AdminUsersUserIdPatch,
  uploadImportApiV1ImportUploadPost,
  uploadPersonProfileImageApiV1PeoplePersonIdProfileImagePost,
} from "../generated/sdk.gen";
import type {
  ActivityCreate,
  ActivityGroupCreate,
  ActivityGroupUpdate,
  ActivityUpdate,
  AdminUserCreate,
  AdminUserListResponse,
  AdminUserUpdate,
  EntryDraftCreate,
  ExportJobCreateRequest,
  GetMediaLibraryApiV1MediaGetData,
  GetMomentCalendarApiV1MomentsCalendarGetData,
  GetMomentsApiV1MomentsGetData,
  GoalCategoryCreate,
  GoalCategoryUpdate,
  GoalCreate,
  GoalUpdate,
  ImmichImportRequest,
  ImmichPeopleImportRequest,
  ImportMode,
  IntegrationSettingsUpdateRequest,
  JournalCreate,
  JournalReorderRequest,
  JournalUpdate,
  ListAssetsApiV1IntegrationsProviderAssetsGetData,
  MomentCreate,
  MomentUpdate,
  MoodCreate,
  MoodGroupCreate,
  MoodGroupUpdate,
  MoodUpdate,
  PersonCreate,
  PersonGroupCreate,
  PersonGroupUpdate,
  PersonUpdate,
  TagCreate,
  TagUpdate,
  UserSettingsUpdate,
  UserCreate,
  UserUpdate,
  WeatherFetchRequest,
} from "../generated/types.gen";
import { configureApiClient } from "./config";

const options = () => ({
  client: configureApiClient(),
  throwOnError: true as const,
});
const data = <T>(result: Promise<{ data: T }>) =>
  result.then((response) => response.data);
export const api = {
  register: (body: UserCreate) =>
    data(registerApiV1AuthRegisterPost({ ...options(), body })),
  login: (email: string, password: string) =>
    data(loginApiV1AuthLoginPost({ ...options(), body: { email, password } })),
  oidcExchange: (ticket: string) =>
    data(
      oidcExchangeApiV1AuthOidcExchangePost({
        ...options(),
        body: { ticket },
      }),
    ),
  refresh: (refresh_token: string) =>
    data(
      refreshTokenApiV1AuthRefreshPost({
        ...options(),
        body: { refresh_token },
      }),
    ),
  me: () => data(getCurrentUserInfoApiV1UsersMeGet(options())),
  /**
   * Updates the signed-in user. `name` and `profile_picture_url` are profile
   * edits; `current_password` + `new_password` together are a password change
   * (rejected server-side for OIDC accounts). Nothing else is settable here.
   */
  updateMe: (body: UserUpdate) =>
    data(updateCurrentUserApiV1UsersMePut({ ...options(), body })),
  /** Preferences (timezone, theme, …) — separate table from the user row. */
  userSettings: () =>
    data(getCurrentUserSettingsApiV1UsersMeSettingsGet(options())),
  updateUserSettings: (body: UserSettingsUpdate) =>
    data(
      updateCurrentUserSettingsApiV1UsersMeSettingsPut({ ...options(), body }),
    ),
  /** Instance capability flags — drives capability-aware Settings rendering. */
  instanceConfig: () =>
    data(getInstanceConfigApiV1InstanceConfigGet(options())),
  /**
   * The admin list endpoint is offset-paginated but exposes no total. Walk it
   * to completion so search and paging describe the complete account list.
   */
  adminUsers: async () => {
    const pageSize = 200;
    // Hard ceiling so a broken short-page contract can't spin forever.
    const maxPages = 50;
    const users: AdminUserListResponse[] = [];
    for (let page = 0; page < maxPages; page += 1) {
      const batch = await data(
        listUsersApiV1AdminUsersGet({
          ...options(),
          query: { limit: pageSize, offset: page * pageSize },
        }),
      );
      users.push(...batch);
      if (batch.length < pageSize) break;
    }
    return users;
  },
  createAdminUser: (body: AdminUserCreate) =>
    data(createUserApiV1AdminUsersPost({ ...options(), body })),
  updateAdminUser: (user_id: string, body: AdminUserUpdate) =>
    data(
      updateUserApiV1AdminUsersUserIdPatch({
        ...options(),
        path: { user_id },
        body,
      }),
    ),
  deleteAdminUser: (user_id: string) =>
    data(
      deleteUserApiV1AdminUsersUserIdDelete({
        ...options(),
        path: { user_id },
      }),
    ),
  /**
   * Every journal, archived included. The frontend keeps one cached list and
   * splits active vs archived client-side, so archiving is instant and the
   * Journals index never needs a second request.
   */
  journals: () =>
    data(
      getUserJournalsApiV1JournalsGet({
        ...options(),
        query: { include_archived: true },
      }),
    ),
  createJournal: (body: JournalCreate) =>
    data(createJournalApiV1JournalsPost({ ...options(), body })),
  updateJournal: (journal_id: string, body: JournalUpdate) =>
    data(
      updateJournalApiV1JournalsJournalIdPut({
        ...options(),
        path: { journal_id },
        body,
      }),
    ),
  /** Toggles favourite on/off; returns the updated journal. */
  toggleJournalFavorite: (journal_id: string) =>
    data(
      toggleFavoriteApiV1JournalsJournalIdFavoritePost({
        ...options(),
        path: { journal_id },
      }),
    ),
  archiveJournal: (journal_id: string) =>
    data(
      archiveJournalApiV1JournalsJournalIdArchivePost({
        ...options(),
        path: { journal_id },
      }),
    ),
  unarchiveJournal: (journal_id: string) =>
    data(
      unarchiveJournalApiV1JournalsJournalIdUnarchivePost({
        ...options(),
        path: { journal_id },
      }),
    ),
  /** Persists new positions for a set of journals. Responds 204. */
  reorderJournals: (body: JournalReorderRequest) =>
    data(reorderJournalsApiV1JournalsReorderPut({ ...options(), body })),
  /**
   * Hard-deletes a journal. The backend cascade-deletes every Entry written in
   * it; the parent Moments survive as quick logs. Irreversible — the UI guards
   * this behind a typed confirmation.
   */
  deleteJournal: (journal_id: string) =>
    data(
      deleteJournalApiV1JournalsJournalIdDelete({
        ...options(),
        path: { journal_id },
      }),
    ),
  moods: () => data(getAllMoodsApiV1MoodsGet(options())),
  createMood: (body: MoodCreate) =>
    data(createMoodApiV1MoodsPost({ ...options(), body })),
  updateMood: (mood_id: string, body: MoodUpdate) =>
    data(
      updateMoodApiV1MoodsMoodIdPut({
        ...options(),
        path: { mood_id },
        body,
      }),
    ),
  deleteMood: (mood_id: string) =>
    data(
      deleteMoodApiV1MoodsMoodIdDelete({
        ...options(),
        path: { mood_id },
      }),
    ),
  /** Mood groups with their embedded moods (`GET /moods/groups`). */
  moodGroups: () => data(getMoodGroupsApiV1MoodsGroupsGet(options())),
  createMoodGroup: (body: MoodGroupCreate) =>
    data(createMoodGroupApiV1MoodsGroupsPost({ ...options(), body })),
  updateMoodGroup: (group_id: string, body: MoodGroupUpdate) =>
    data(
      updateMoodGroupApiV1MoodsGroupsGroupIdPut({
        ...options(),
        path: { group_id },
        body,
      }),
    ),
  deleteMoodGroup: (group_id: string) =>
    data(
      deleteMoodGroupApiV1MoodsGroupsGroupIdDelete({
        ...options(),
        path: { group_id },
      }),
    ),
  /** Everyone the user has recorded, for the people picker. */
  people: () =>
    data(
      getPeopleApiV1PeopleGet({
        ...options(),
        query: { limit: 500, sort: "by_name" },
      }),
    ),
  createPerson: (body: PersonCreate) =>
    data(createPersonApiV1PeoplePost({ ...options(), body })),
  updatePerson: (person_id: string, body: PersonUpdate) =>
    data(
      updatePersonApiV1PeoplePersonIdPut({
        ...options(),
        path: { person_id },
        body,
      }),
    ),
  archivePerson: (person_id: string) =>
    data(
      archivePersonApiV1PeoplePersonIdDelete({
        ...options(),
        path: { person_id },
      }),
    ),
  mergePeople: (source_id: string, target_id: string) =>
    data(
      mergePeopleApiV1PeopleSourceIdMergeTargetIdPost({
        ...options(),
        path: { source_id, target_id },
      }),
    ),
  uploadPersonImage: (person_id: string, file: File) =>
    data(
      uploadPersonProfileImageApiV1PeoplePersonIdProfileImagePost({
        ...options(),
        path: { person_id },
        body: { file },
      }),
    ),
  removePersonImage: (person_id: string) =>
    data(
      removePersonProfileImageApiV1PeoplePersonIdProfileImageDelete({
        ...options(),
        path: { person_id },
      }),
    ),
  personGroups: () => data(getPersonGroupsApiV1PeopleGroupsGet(options())),
  createPersonGroup: (body: PersonGroupCreate) =>
    data(createPersonGroupApiV1PeopleGroupsPost({ ...options(), body })),
  updatePersonGroup: (group_id: string, body: PersonGroupUpdate) =>
    data(
      updatePersonGroupApiV1PeopleGroupsGroupIdPut({
        ...options(),
        path: { group_id },
        body,
      }),
    ),
  deletePersonGroup: (group_id: string) =>
    data(
      deletePersonGroupApiV1PeopleGroupsGroupIdDelete({
        ...options(),
        path: { group_id },
      }),
    ),
  tags: async () => {
    const tags = [];
    let offset = 0;
    while (true) {
      const page = await data(
        getUserTagsApiV1TagsGet({
          ...options(),
          query: { limit: 100, offset },
        }),
      );
      tags.push(...page);
      if (page.length < 100) return tags;
      offset += 100;
    }
  },
  createTag: (body: TagCreate) =>
    data(createTagApiV1TagsPost({ ...options(), body })),
  updateTag: (tag_id: string, body: TagUpdate) =>
    data(
      updateTagApiV1TagsTagIdPut({
        ...options(),
        path: { tag_id },
        body,
      }),
    ),
  deleteTag: (tag_id: string) =>
    data(deleteTagApiV1TagsTagIdDelete({ ...options(), path: { tag_id } })),
  /** Delete every tag attached to no moment. Returns `{ deleted }`. */
  deleteUnusedTags: () =>
    data(deleteUnusedTagsApiV1TagsUnusedDelete(options())),
  mergeTags: (source_id: string, target_id: string) =>
    data(
      mergeTagsApiV1TagsSourceIdMergeTargetIdPost({
        ...options(),
        path: { source_id, target_id },
      }),
    ),
  /** Moments carrying one tag — the tag detail preview. */
  tagMoments: (tag_id: string) =>
    data(
      getMomentsByTagApiV1TagsTagIdMomentsGet({
        ...options(),
        path: { tag_id },
        query: { limit: 5, include_media: "thumbnails" },
      }),
    ),
  /**
   * Aggregate tag analytics. Journiv Plus (Supporter+) only — a 403/503 here
   * means "not licensed / not built", handled by the caller as a locked state,
   * never a raw error.
   */
  tagAnalytics: () => data(getTagAnalyticsApiV1TagsAnalyticsGet(options())),
  /** One tag's analytics over `days`. Same Plus gating as `tagAnalytics`. */
  tagDetailAnalytics: (tag_id: string, days: number) =>
    data(
      getTagDetailAnalyticsApiV1TagsTagIdAnalyticsGet({
        ...options(),
        path: { tag_id },
        query: { days },
      }),
    ),
  /** Every active activity. The endpoint is paginated, so Library must walk
   *  all pages instead of silently dropping everything after the first page. */
  activities: async () => {
    const activities = [];
    let offset = 0;
    while (true) {
      const page = await data(
        getActivitiesApiV1ActivitiesGet({
          ...options(),
          query: { limit: 200, offset },
        }),
      );
      activities.push(...page);
      if (page.length < 200) return activities;
      offset += 200;
    }
  },
  createActivity: (body: ActivityCreate) =>
    data(createActivityApiV1ActivitiesPost({ ...options(), body })),
  updateActivity: (activity_id: string, body: ActivityUpdate) =>
    data(
      updateActivityApiV1ActivitiesActivityIdPut({
        ...options(),
        path: { activity_id },
        body,
      }),
    ),
  deleteActivity: (activity_id: string) =>
    data(
      deleteActivityApiV1ActivitiesActivityIdDelete({
        ...options(),
        path: { activity_id },
      }),
    ),
  /** Activity groups with their embedded activities (`GET /activity-groups/`). */
  activityGroups: () =>
    data(getActivityGroupsApiV1ActivityGroupsGet(options())),
  createActivityGroup: (body: ActivityGroupCreate) =>
    data(createActivityGroupApiV1ActivityGroupsPost({ ...options(), body })),
  updateActivityGroup: (group_id: string, body: ActivityGroupUpdate) =>
    data(
      updateActivityGroupApiV1ActivityGroupsGroupIdPut({
        ...options(),
        path: { group_id },
        body,
      }),
    ),
  deleteActivityGroup: (group_id: string) =>
    data(
      deleteActivityGroupApiV1ActivityGroupsGroupIdDelete({
        ...options(),
        path: { group_id },
      }),
    ),
  goals: () =>
    data(
      getGoalsApiV1GoalsGet({
        ...options(),
        query: { include_archived: false },
      }),
    ),
  createGoal: (body: GoalCreate) =>
    data(createGoalApiV1GoalsPost({ ...options(), body })),
  /** Historical period roll-up logs for one goal (`GET /goals/{id}/logs`),
   *  newest period first. One record per period the goal has been evaluated in —
   *  not a raw event feed. `limit` is 1–365; the backend default is 12. */
  goalLogs: (goal_id: string, limit = 12) =>
    data(
      getGoalLogsApiV1GoalsGoalIdLogsGet({
        ...options(),
        path: { goal_id },
        query: { limit },
      }),
    ),
  updateGoal: (goal_id: string, body: GoalUpdate) =>
    data(
      updateGoalApiV1GoalsGoalIdPut({
        ...options(),
        path: { goal_id },
        body,
      }),
    ),
  deleteGoal: (goal_id: string) =>
    data(
      deleteGoalPermanentlyApiV1GoalsGoalIdDelete({
        ...options(),
        path: { goal_id },
      }),
    ),
  /** Goal categories (`GET /goal-categories`). Responses do not embed members;
   *  counts are derived from the full Goals response. */
  goalCategories: () =>
    data(getGoalCategoriesApiV1GoalCategoriesGet(options())),
  createGoalCategory: (body: GoalCategoryCreate) =>
    data(createGoalCategoryApiV1GoalCategoriesPost({ ...options(), body })),
  updateGoalCategory: (category_id: string, body: GoalCategoryUpdate) =>
    data(
      updateGoalCategoryApiV1GoalCategoriesCategoryIdPut({
        ...options(),
        path: { category_id },
        body,
      }),
    ),
  deleteGoalCategory: (category_id: string) =>
    data(
      deleteGoalCategoryApiV1GoalCategoriesCategoryIdDelete({
        ...options(),
        path: { category_id },
      }),
    ),
  createExport: (body: ExportJobCreateRequest) =>
    data(createExportApiV1ExportPost({ ...options(), body })),
  exportStatus: (job_id: string) =>
    data(
      getExportStatusApiV1ExportJobIdGet({
        ...options(),
        path: { job_id },
      }),
    ),
  /** Short-lived signed download URL. The plain `download_url` on the status
   *  response points at an endpoint that needs the Authorization header, so a
   *  browser-native download can only use this. */
  signExportUrl: (job_id: string) =>
    data(
      signExportUrlApiV1ExportJobIdSignGet({
        ...options(),
        path: { job_id },
      }),
    ),
  uploadImport: (file: File, source_type: string) =>
    data(
      uploadImportApiV1ImportUploadPost({
        ...options(),
        body: { file, source_type },
      }),
    ),
  importStatus: (job_id: string) =>
    data(
      getImportStatusApiV1ImportJobIdGet({
        ...options(),
        path: { job_id },
      }),
    ),
  versionInfo: () => data(getVersionInfoApiV1InstanceVersionInfoGet(options())),
  licenseInfo: () => data(getLicenseInfoApiV1InstanceLicenseInfoGet(options())),
  integrationStatus: () =>
    data(
      getStatusApiV1IntegrationsProviderStatusGet({
        ...options(),
        path: { provider: "immich" },
      }),
    ),
  connectImmich: (
    credentials: Record<string, unknown>,
    import_mode?: ImportMode,
  ) =>
    data(
      connectApiV1IntegrationsConnectPost({
        ...options(),
        body: {
          provider: "immich",
          credentials,
          ...(import_mode ? { import_mode } : {}),
        },
      }),
    ),
  updateImmich: (body: IntegrationSettingsUpdateRequest) =>
    data(
      updateSettingsApiV1IntegrationsProviderSettingsPut({
        ...options(),
        path: { provider: "immich" },
        body,
      }),
    ),
  disconnectImmich: () =>
    data(
      disconnectApiV1IntegrationsProviderDisconnectDelete({
        ...options(),
        path: { provider: "immich" },
      }),
    ),
  /** Manually re-run the provider sync (metadata cache refresh). */
  syncImmich: () =>
    data(
      triggerSyncApiV1IntegrationsProviderSyncPost({
        ...options(),
        path: { provider: "immich" },
      }),
    ),
  /**
   * One page of the connected Immich library, newest first. Pagination is
   * `page`/`limit` only — the backend exposes no search / type / date / album
   * filter yet (tracked as gap G1 in frontend-immich-v2.md), so the picker
   * scrolls rather than queries.
   */
  immichAssets: (
    query: NonNullable<
      ListAssetsApiV1IntegrationsProviderAssetsGetData["query"]
    >,
  ) =>
    data(
      listAssetsApiV1IntegrationsProviderAssetsGet({
        ...options(),
        path: { provider: "immich" },
        query,
      }),
    ),
  /**
   * Starts a background job that attaches the chosen Immich assets to `moment_id`.
   * Link-only vs copy is decided server-side by the integration's import mode.
   * Returns placeholder media rows the editor swaps its upload placeholders for.
   */
  importFromImmich: (body: ImmichImportRequest) =>
    data(
      importFromImmichAsyncApiV1MediaImportFromImmichAsyncPost({
        ...options(),
        body,
      }),
    ),
  /** Status of an Immich import job — poll while `pending`/`running`. */
  immichImportJob: (job_id: string) =>
    data(
      getImportJobStatusApiV1MediaImportJobsJobIdGet({
        ...options(),
        path: { job_id },
      }),
    ),
  /**
   * One page of the connected Immich instance's detected people, newest first.
   * Unlike the asset list this endpoint takes a real `search` term. Each row
   * carries `mapped_person` when it is already linked to a Journiv person and
   * `sync_enabled` when its faces feed moment suggestions.
   */
  immichPeople: (query: { page: number; limit: number; search?: string }) =>
    data(
      listImmichPeopleApiV1IntegrationsImmichPeopleGet({
        ...options(),
        query,
      }),
    ),
  /**
   * Creates or links Journiv people from selected Immich people. Partial
   * success: the response's `results[]` carry a `person` or an `error` each —
   * the call does not fail as a whole when one item does.
   */
  importImmichPeople: (body: ImmichPeopleImportRequest) =>
    data(
      importImmichPeopleApiV1IntegrationsImmichPeopleImportPost({
        ...options(),
        body,
      }),
    ),
  /**
   * People the Immich face index matches to this moment's Immich media and who
   * are sync-enabled but not yet on the moment. POST with no body; read-shaped,
   * so it is consumed as a query. Never writes — the editor only suggests.
   */
  immichPeopleSuggestions: (moment_id: string) =>
    data(
      getImmichPeopleSuggestionsApiV1MomentsMomentIdPeopleSuggestionsImmichPost(
        {
          ...options(),
          path: { moment_id },
        },
      ),
    ),
  /** Tag name suggestions for the tag picker. */
  searchTags: (q: string) =>
    data(searchTagsApiV1TagsSearchGet({ ...options(), query: { q } })),
  /** Adds tags to a Moment by name; returns the Moment's full tag set. */
  addMomentTags: (moment_id: string, names: string[]) =>
    data(
      bulkAddTagsToMomentApiV1MomentsMomentIdTagsPost({
        ...options(),
        path: { moment_id },
        body: names,
      }),
    ),
  removeMomentTag: (moment_id: string, tag_id: string) =>
    data(
      removeTagFromMomentApiV1MomentsMomentIdTagsTagIdDelete({
        ...options(),
        path: { moment_id, tag_id },
      }),
    ),
  /** Replaces the Moment's people with `person_ids`; returns the new set. */
  setMomentPeople: (moment_id: string, person_ids: string[]) =>
    data(
      replaceMomentPeopleApiV1MomentsMomentIdPeoplePut({
        ...options(),
        path: { moment_id },
        body: { person_ids },
      }),
    ),
  /** Geocodes a free-text place query. */
  searchLocation: (query: string) =>
    data(
      searchLocationApiV1LocationSearchPost({ ...options(), body: { query } }),
    ),
  /** Turns device coordinates into a named place. */
  reverseGeocode: (latitude: number, longitude: number) =>
    data(
      reverseGeocodeApiV1LocationReversePost({
        ...options(),
        body: { latitude, longitude },
      }),
    ),
  /** Fetches weather for a coordinate and time. May report the service is off. */
  fetchWeather: (body: WeatherFetchRequest) =>
    data(fetchWeatherApiV1WeatherFetchPost({ ...options(), body })),
  moments: (query: NonNullable<GetMomentsApiV1MomentsGetData["query"]>) =>
    data(getMomentsApiV1MomentsGet({ ...options(), query })),
  /** Per-day moment counts, primary mood and a thumbnail — the calendar grid. */
  momentCalendar: (
    query: NonNullable<GetMomentCalendarApiV1MomentsCalendarGetData["query"]>,
  ) => data(getMomentCalendarApiV1MomentsCalendarGet({ ...options(), query })),
  /** Flat, paginated media across every moment — the Media grid. */
  mediaLibrary: (
    query: NonNullable<GetMediaLibraryApiV1MediaGetData["query"]>,
  ) => data(getMediaLibraryApiV1MediaGet({ ...options(), query })),
  moment: (moment_id: string) =>
    data(
      getMomentApiV1MomentsMomentIdGet({ ...options(), path: { moment_id } }),
    ),
  /** Authoritative accepted extensions, so the picker cannot invent its own. */
  mediaFormats: () => data(getSupportedFormatsApiV1MediaFormatsGet(options())),
  momentMedia: (moment_id: string) =>
    data(
      getMomentMediaApiV1MomentsMomentIdMediaGet({
        ...options(),
        path: { moment_id },
      }),
    ),
  entry: (entry_id: string) =>
    data(getEntryApiV1EntriesEntryIdGet({ ...options(), path: { entry_id } })),
  /**
   * Creates the server-side draft that owns uploaded media before an Entry is
   * finalised. Draft Entries are excluded from the Timeline by
   * `_apply_draft_filter`, so an abandoned one is invisible rather than junk.
   */
  createDraftEntry: (body: EntryDraftCreate) =>
    data(createDraftEntryApiV1EntriesDraftPost({ ...options(), body })),
  deleteMoment: (moment_id: string) =>
    data(
      deleteMomentApiV1MomentsMomentIdDelete({
        ...options(),
        path: { moment_id },
      }),
    ),
  deleteMedia: (media_id: string) =>
    data(
      deleteMediaApiV1MediaMediaIdDelete({ ...options(), path: { media_id } }),
    ),
  deleteEntry: (entry_id: string) =>
    data(
      deleteEntryApiV1EntriesEntryIdDelete({
        ...options(),
        path: { entry_id },
      }),
    ),
  createMoment: (body: MomentCreate) =>
    data(createMomentApiV1MomentsPost({ ...options(), body })),
  updateMoment: (moment_id: string, body: MomentUpdate) =>
    data(
      updateMomentApiV1MomentsMomentIdPut({
        ...options(),
        body,
        path: { moment_id },
      }),
    ),
};
