import { useQuery } from "@tanstack/react-query";
import { moodsQuery } from "../api/query/options";
import type { MoodResponse } from "../api/generated/types.gen";

/**
 * Resolve a mood id to its record. Mirrors `useJournalLookup` — the mood list is
 * small and cached, so id -> mood is cheap. Mood colour is the only hue a mood
 * contributes; render it as a dot, never as a valence scale (DESIGN.md §21.6).
 */
export function useMoodLookup() {
  const moods = useQuery(moodsQuery());
  const byId = new Map<string, MoodResponse>(
    (moods.data ?? []).map((mood) => [mood.id, mood]),
  );
  return {
    moods: moods.data ?? [],
    isLoading: moods.isLoading,
    isError: moods.isError,
    get: (id?: string | null) => (id ? byId.get(id) : undefined),
  };
}
