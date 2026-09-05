import { useInfiniteQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import type { PromptResponse } from "../../api/generated/types.gen";
import { promptLibraryQuery } from "../../api/query/options";
import { durationBounds } from "./promptDisplay";

export type PromptFilterState = {
  search: string;
  /** `null` = every category. */
  category: string | null;
  /** `null` = every level. */
  difficulty: number | null;
  /** `null` = every duration; otherwise a `DURATION_BUCKETS` value. */
  duration: string | null;
};

export const EMPTY_PROMPT_FILTERS: PromptFilterState = {
  search: "",
  category: null,
  difficulty: null,
  duration: null,
};

export type PromptBrowserState = {
  filters: PromptFilterState;
  setFilter: (patch: Partial<PromptFilterState>) => void;
  resetFilters: () => void;
  hasActiveFilters: boolean;
  /** Every currently loaded result from the server-filtered query. */
  prompts: PromptResponse[];
  /** Total matching prompts reported by the server. */
  totalCount: number;
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  fetchNextPage: () => void;
  /** Count per category over the search / level / duration set — the chip
   *  badges. Not narrowed by the active category, so the numbers stay stable
   *  as the writer clicks between categories. */
  categoryCounts: Map<string, number>;
  /** Result count with no category filter — the "All" chip badge. */
  allCount: number;
  isLoading: boolean;
  isError: boolean;
  refetch: () => void;
};

/**
 * Shared data + filter state for the prompt browser, used by both the
 * `/library/prompts` page and the in-editor picker so the two surfaces cannot
 * drift (docs/features/prompts.md).
 *
 * The system library is fetched in offset pages. All four filters travel with
 * the API request, so a result total and later pages describe the same set.
 */
export function usePromptBrowser(): PromptBrowserState {
  const [filters, setFilters] =
    useState<PromptFilterState>(EMPTY_PROMPT_FILTERS);
  const apiFilters = useMemo(() => {
    const bounds = durationBounds(filters.duration);
    const q = filters.search.trim();
    return {
      ...(filters.category ? { category: filters.category } : {}),
      ...(filters.difficulty != null
        ? { difficulty_level: filters.difficulty }
        : {}),
      ...(q ? { q } : {}),
      ...bounds,
    };
  }, [filters.category, filters.difficulty, filters.duration, filters.search]);
  const library = useInfiniteQuery(promptLibraryQuery(apiFilters));

  const setFilter = (patch: Partial<PromptFilterState>) => {
    setFilters((prev) => ({ ...prev, ...patch }));
  };
  const resetFilters = () => {
    setFilters(EMPTY_PROMPT_FILTERS);
  };

  const all = useMemo(
    () => (library.data?.pages ?? []).flatMap((page) => page.items),
    [library.data],
  );

  const firstPage = library.data?.pages[0];
  const categoryCounts = useMemo(
    () => new Map(Object.entries(firstPage?.category_counts ?? {})),
    [firstPage?.category_counts],
  );

  return {
    filters,
    setFilter,
    resetFilters,
    hasActiveFilters:
      filters.search.trim() !== "" ||
      filters.category != null ||
      filters.difficulty != null ||
      filters.duration != null,
    prompts: all,
    totalCount: firstPage?.total ?? 0,
    hasNextPage: library.hasNextPage,
    isFetchingNextPage: library.isFetchingNextPage,
    fetchNextPage: () => {
      void library.fetchNextPage();
    },
    categoryCounts,
    allCount: firstPage?.all_count ?? 0,
    isLoading: library.isLoading,
    isError: library.isError,
    refetch: () => {
      void library.refetch();
    },
  };
}
