import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client/api";
import { queryKeys } from "../../api/query/keys";
import type {
  JournalCreate,
  JournalReorderRequest,
  JournalResponse,
  JournalUpdate,
} from "../../api/generated/types.gen";

type List = JournalResponse[];

/**
 * All journal writes in one place, with optimistic cache updates against the
 * single cached list (`queryKeys.journals`) and rollback on failure. Callers
 * surface failure through a `role="alert"` with their own human message; the
 * raw error is never shown.
 */
export function useJournalMutations() {
  const qc = useQueryClient();

  const snapshot = () => qc.getQueryData<List>(queryKeys.journals);
  const write = (next: List) => qc.setQueryData(queryKeys.journals, next);
  const restore = (prev: List | undefined) => {
    if (prev) qc.setQueryData(queryKeys.journals, prev);
  };
  const patch = (id: string, changes: Partial<JournalResponse>) => {
    const prev = snapshot();
    if (prev) write(prev.map((j) => (j.id === id ? { ...j, ...changes } : j)));
    return prev;
  };
  const invalidate = () =>
    qc.invalidateQueries({ queryKey: queryKeys.journals });

  const create = useMutation({
    mutationFn: (body: JournalCreate) => api.createJournal(body),
    onSuccess: invalidate,
  });

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: JournalUpdate }) =>
      api.updateJournal(id, body),
    onMutate: ({ id, body }) => ({
      prev: patch(id, body as Partial<JournalResponse>),
    }),
    onError: (_e, _v, ctx) => restore(ctx?.prev),
    onSettled: invalidate,
  });

  const toggleFavorite = useMutation({
    mutationFn: (journal: JournalResponse) =>
      api.toggleJournalFavorite(journal.id),
    onMutate: (journal) => ({
      prev: patch(journal.id, { is_favorite: !journal.is_favorite }),
    }),
    onError: (_e, _v, ctx) => restore(ctx?.prev),
    onSettled: invalidate,
  });

  const setArchived = useMutation({
    mutationFn: ({ id, archived }: { id: string; archived: boolean }) =>
      archived ? api.archiveJournal(id) : api.unarchiveJournal(id),
    onMutate: ({ id, archived }) => ({
      prev: patch(id, { is_archived: archived }),
    }),
    onError: (_e, _v, ctx) => restore(ctx?.prev),
    onSettled: invalidate,
  });

  const reorder = useMutation({
    mutationFn: (body: JournalReorderRequest) => api.reorderJournals(body),
    onMutate: (body) => {
      const prev = snapshot();
      if (prev) {
        const pos = new Map(body.updates.map((u) => [u.id, u.position]));
        write(
          prev.map((j) =>
            pos.has(j.id) ? { ...j, position: pos.get(j.id) ?? null } : j,
          ),
        );
      }
      return { prev };
    },
    onError: (_e, _v, ctx) => restore(ctx?.prev),
    onSettled: invalidate,
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.deleteJournal(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.journals });
      // Entries in the journal are gone and some Moments were pruned.
      void qc.invalidateQueries({ queryKey: queryKeys.allMoments });
    },
  });

  return { create, update, toggleFavorite, setArchived, reorder, remove };
}
