import { useVirtualizer } from "@tanstack/react-virtual";
import { useEffect, useLayoutEffect, useRef, useState } from "react";

export type VirtualGridOptions = {
  /** Smallest a tile is allowed to get before a column is dropped. */
  minTileWidth: number;
  /** Gap between tiles, both axes. */
  gap: number;
  /** Never fewer than this many columns (phones still show a grid, not a list). */
  minColumns: number;
  /** Never more than this many (keeps tiles from becoming stamps on a wall). */
  maxColumns: number;
};

/**
 * How many columns fit `containerWidth`, clamped. Pure so the responsive
 * behaviour is unit-tested without a layout engine.
 */
export function columnCountFor(
  containerWidth: number,
  { minTileWidth, gap, minColumns, maxColumns }: VirtualGridOptions,
): number {
  if (!Number.isFinite(containerWidth) || containerWidth <= 0)
    return minColumns;
  const fit = Math.floor((containerWidth + gap) / (minTileWidth + gap));
  return Math.min(maxColumns, Math.max(minColumns, fit));
}

/** Splits a flat list into rows of `columns`. */
export function chunkRows<T>(items: T[], columns: number): T[][] {
  if (columns < 1) return items.length ? [items] : [];
  const rows: T[][] = [];
  for (let i = 0; i < items.length; i += columns) {
    rows.push(items.slice(i, i + columns));
  }
  return rows;
}

/**
 * Row-virtualizes a square-tile grid inside `scrollRef`.
 *
 * - Column count follows the container's real width (ResizeObserver), never a
 *   media query — DESIGN.md §9 calls this "a component reflowing at its own
 *   width", which is allowed and needs no page breakpoint.
 * - Reaching the last couple of rows pulls the next page. This replaces a
 *   separate IntersectionObserver sentinel: the virtualizer already knows which
 *   rows are near the viewport.
 */
export function useVirtualGrid<T>({
  items,
  scrollRef,
  options,
  hasNextPage,
  isFetchingNextPage,
  fetchNextPage,
}: {
  items: T[];
  scrollRef: React.RefObject<HTMLElement | null>;
  options: VirtualGridOptions;
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  fetchNextPage: () => void;
}) {
  const [width, setWidth] = useState(0);

  useLayoutEffect(() => {
    const element = scrollRef.current;
    if (!element) return;
    setWidth(element.clientWidth);
    const observer = new ResizeObserver((entries) => {
      const next = entries[0]?.contentRect.width;
      if (typeof next === "number") setWidth(next);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [scrollRef]);

  const columns = columnCountFor(width, options);
  const rows = chunkRows(items, columns);
  const tileWidth =
    columns > 0 && width > 0
      ? (width - options.gap * (columns - 1)) / columns
      : options.minTileWidth;
  const rowHeight = tileWidth + options.gap;

  const rowVirtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => rowHeight,
    overscan: 4,
  });

  // A resize changes the square tile size, so cached row measurements go stale.
  // biome-ignore lint/correctness/useExhaustiveDependencies: rowHeight is the trigger though it is read only inside the virtualizer's estimateSize closure.
  useEffect(() => {
    rowVirtualizer.measure();
  }, [rowHeight, rowVirtualizer]);

  const virtualRows = rowVirtualizer.getVirtualItems();
  const lastVisibleRow = virtualRows.at(-1)?.index ?? 0;
  const fetchGuard = useRef(false);
  useEffect(() => {
    if (!hasNextPage || isFetchingNextPage) {
      fetchGuard.current = false;
      return;
    }
    if (lastVisibleRow >= rows.length - 2 && !fetchGuard.current) {
      fetchGuard.current = true;
      fetchNextPage();
    }
  }, [
    lastVisibleRow,
    rows.length,
    hasNextPage,
    isFetchingNextPage,
    fetchNextPage,
  ]);

  return { columns, rows, rowVirtualizer, virtualRows, tileWidth };
}
