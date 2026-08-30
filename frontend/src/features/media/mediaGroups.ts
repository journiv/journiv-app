import type { MediaLibraryItem } from "../../api/generated/types.gen";

export type MediaMonthGroup = {
  key: string;
  label: string;
  items: MediaLibraryItem[];
};

/**
 * Group a flat, newest-first media list into month sections. Items of the same
 * calendar month arrive contiguous (the API orders by the owning moment's
 * time), so this is a single pass and preserves order.
 */
export function groupMediaByMonth(
  items: readonly MediaLibraryItem[],
): MediaMonthGroup[] {
  const groups: MediaMonthGroup[] = [];
  for (const item of items) {
    const key = item.logged_date_tz.slice(0, 7);
    const last = groups[groups.length - 1];
    if (last && last.key === key) {
      last.items.push(item);
      continue;
    }
    groups.push({ key, label: monthLabel(key), items: [item] });
  }
  return groups;
}

function monthLabel(key: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${key}-01T12:00:00Z`));
}
