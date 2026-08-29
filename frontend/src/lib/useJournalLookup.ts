import { useQuery } from "@tanstack/react-query";
import { journalsQuery } from "../api/query/options";
import type { JournalResponse } from "../api/generated/types.gen";

/**
 * Journals are the only sanctioned source of hue in the product chrome.
 * Resolving id -> journal is cheap because the journal list is already cached.
 */
export function useJournalLookup() {
  const journals = useQuery(journalsQuery());
  const byId = new Map<string, JournalResponse>(
    (journals.data ?? []).map((journal) => [journal.id, journal]),
  );
  return {
    journals: journals.data ?? [],
    isLoading: journals.isLoading,
    isError: journals.isError,
    refetch: journals.refetch,
    get: (id?: string | null) => (id ? byId.get(id) : undefined),
  };
}
