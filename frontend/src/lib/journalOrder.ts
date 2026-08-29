import type {
  JournalReorderItem,
  JournalResponse,
} from "../api/generated/types.gen";

const POS = (j: JournalResponse) => j.position ?? Number.MAX_SAFE_INTEGER;

/**
 * The order the backend itself uses: favourites first, then by explicit
 * position (unset sinks to the end), then newest first as a stable fallback.
 * Every surface that lists journals sorts through this so they agree.
 */
export function compareJournals(
  a: JournalResponse,
  b: JournalResponse,
): number {
  if (a.is_favorite !== b.is_favorite) return a.is_favorite ? -1 : 1;
  if (POS(a) !== POS(b)) return POS(a) - POS(b);
  return b.created_at.localeCompare(a.created_at);
}

export function sortJournals(journals: JournalResponse[]): JournalResponse[] {
  return [...journals].sort(compareJournals);
}

export type JournalGroups = {
  /** Non-archived, sorted. Favourites lead. */
  active: JournalResponse[];
  /** Archived, sorted. */
  archived: JournalResponse[];
  /** Non-archived favourites, sorted — the sidebar's quick scopes. */
  favorites: JournalResponse[];
};

export function groupJournals(journals: JournalResponse[]): JournalGroups {
  const active = sortJournals(journals.filter((j) => !j.is_archived));
  return {
    active,
    archived: sortJournals(journals.filter((j) => j.is_archived)),
    favorites: active.filter((j) => j.is_favorite),
  };
}

/**
 * The journal a brand-new entry should be filed in when the route names none:
 * the first in canonical order. Favouriting or reordering a journal on the
 * Journals screen is therefore how you pick the default.
 */
export function defaultJournalId(
  journals: JournalResponse[],
): string | undefined {
  return groupJournals(journals).active[0]?.id;
}

/**
 * Positions to persist to move `id` one step within its own favourite/archived
 * peer group (the two groups the backend orders independently). Returns `null`
 * when the move is a no-op — already at the group edge.
 */
export function reorderWithinGroup(
  journals: JournalResponse[],
  id: string,
  direction: "up" | "down",
): JournalReorderItem[] | null {
  const target = journals.find((j) => j.id === id);
  if (!target) return null;
  const peers = sortJournals(
    journals.filter(
      (j) => j.is_favorite === target.is_favorite && !j.is_archived,
    ),
  );
  const from = peers.findIndex((j) => j.id === id);
  const to = direction === "up" ? from - 1 : from + 1;
  if (from < 0 || to < 0 || to >= peers.length) return null;
  const next = [...peers];
  [next[from], next[to]] = [next[to], next[from]];
  return next.map((j, index) => ({ id: j.id, position: index }));
}
