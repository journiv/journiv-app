/**
 * The provider-agnostic contract behind {@link AssetGridPicker}.
 *
 * The Immich asset picker in the entry editor is the first consumer. A later
 * milestone (people / face import — see `frontend-immich-v2.md` §6) reuses the
 * same shell with a person-thumbnail source and the `person` tile variant, so
 * nothing here may reference Immich, entries, or people directly.
 */

export type AssetGridItem = {
  /** Stable id used for selection and as the React key. */
  id: string;
  /** A ready-to-use image URL (already signed / same-origin). */
  thumbUrl: string;
  /** Accessible label for the tile — a filename or a person's name. */
  label: string;
  /** Drives the corner badge. `null` for a plain image or an avatar. */
  badge: "video" | null;
  /** Seconds, shown on a video badge when the source can provide it. */
  durationSec?: number | null;
};

export type AssetGridData = {
  items: AssetGridItem[];
  /** True only for the very first page load. */
  isLoading: boolean;
  isFetchingNextPage: boolean;
  hasNextPage: boolean;
  fetchNextPage: () => void;
  isError: boolean;
  refetch: () => void;
};

export type AssetGridSource = {
  /** A hook returning the current page set and its paging controls. */
  useItems: () => AssetGridData;
  /** Shown by the shell when a successful load returns nothing. */
  empty: { title: string; description?: string };
  /** Shown when the source errors (stale key, provider unreachable, …). */
  error: { title: string; description?: string; retryLabel?: string };
};
