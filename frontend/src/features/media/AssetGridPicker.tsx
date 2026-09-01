import { Check, ImageOff, Play } from "lucide-react";
import { type RefObject, useRef, useState } from "react";
import { cx } from "../../lib/cx";
import { Button } from "../../components/ui/button";
import { Skeleton } from "../../components/ui/skeleton";
import { Spinner } from "../../components/ui/spinner";
import { StatusView } from "../../components/journiv/StatusView";
import type { AssetGridItem, AssetGridSource } from "./assetGrid.types";
import { useVirtualGrid, type VirtualGridOptions } from "./useVirtualGrid";
import "./assetGrid.css";

/** The default selection ceiling — the import endpoint caps `asset_ids` at 100. */
export const DEFAULT_MAX_SELECTION = 100;

const GRID_OPTIONS: VirtualGridOptions = {
  minTileWidth: 132,
  gap: 8,
  minColumns: 3,
  maxColumns: 8,
};

const SKELETON_TILES = 12;

export type AssetGridPickerProps = {
  source: AssetGridSource;
  /** Controlled: the ids currently chosen, in selection order. */
  selectedIds: string[];
  /** Toggle one tile. Not called for a *new* selection once the cap is hit. */
  onToggle: (id: string) => void;
  onClear: () => void;
  onConfirm: () => void;
  /** Already-formatted, e.g. "Add 3 photos". */
  confirmLabel: string;
  maxSelection?: number;
  /** `person` renders round tiles without a media badge (milestone 2). */
  variant?: "asset" | "person";
  /** Reuses an owning overlay body's scroll container for virtualization. */
  scrollRef?: RefObject<HTMLDivElement | null>;
  /** The owning overlay renders `AssetGridPickerFooter` in its fixed footer. */
  hideFooter?: boolean;
};

export function AssetGridPicker({
  source,
  selectedIds,
  onToggle,
  onClear,
  onConfirm,
  confirmLabel,
  maxSelection = DEFAULT_MAX_SELECTION,
  variant = "asset",
  scrollRef: externalScrollRef,
  hideFooter = false,
}: AssetGridPickerProps) {
  const {
    items,
    isLoading,
    isFetchingNextPage,
    hasNextPage,
    fetchNextPage,
    isError,
    refetch,
  } = source.useItems();

  const internalScrollRef = useRef<HTMLDivElement>(null);
  const scrollRef = externalScrollRef ?? internalScrollRef;
  const [capHit, setCapHit] = useState(false);
  const selected = new Set(selectedIds);
  const atCap = selectedIds.length >= maxSelection;

  const { rows, rowVirtualizer, virtualRows, columns } = useVirtualGrid({
    items,
    scrollRef,
    options: GRID_OPTIONS,
    hasNextPage,
    isFetchingNextPage,
    fetchNextPage,
  });

  const handleToggle = (item: AssetGridItem) => {
    if (!selected.has(item.id) && atCap) {
      setCapHit(true);
      return;
    }
    setCapHit(false);
    onToggle(item.id);
  };

  return (
    <div
      className="jv-asset-picker"
      data-variant={variant}
      data-scroll-owner={externalScrollRef ? "overlay" : "self"}
    >
      <section
        className="jv-asset-picker__scroll"
        ref={externalScrollRef ? undefined : internalScrollRef}
        tabIndex={-1}
        aria-label="Media library"
      >
        {isError ? (
          <StatusView
            tone="danger"
            title={source.error.title}
            description={source.error.description}
            action={
              <Button onClick={() => refetch()}>
                {source.error.retryLabel ?? "Try again"}
              </Button>
            }
          />
        ) : isLoading ? (
          <ul
            className="jv-asset-picker__row jv-asset-picker__row--static"
            style={{
              gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`,
            }}
          >
            {Array.from({ length: SKELETON_TILES }, (_, index) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: fixed count of identical placeholders that never reorder.
              <li key={index} aria-hidden="true">
                <Skeleton className="jv-asset-tile" />
              </li>
            ))}
          </ul>
        ) : items.length === 0 ? (
          <StatusView
            title={source.empty.title}
            description={source.empty.description}
          />
        ) : (
          <div
            className="jv-asset-picker__viewport"
            style={{ height: `${rowVirtualizer.getTotalSize()}px` }}
          >
            {virtualRows.map((virtualRow) => (
              <ul
                key={virtualRow.key}
                data-index={virtualRow.index}
                ref={rowVirtualizer.measureElement}
                className="jv-asset-picker__row"
                style={{
                  transform: `translateY(${virtualRow.start}px)`,
                  gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`,
                }}
              >
                {(rows[virtualRow.index] ?? []).map((item) => (
                  <li key={item.id}>
                    <AssetTile
                      item={item}
                      selected={selected.has(item.id)}
                      disabled={!selected.has(item.id) && atCap}
                      onToggle={() => handleToggle(item)}
                    />
                  </li>
                ))}
              </ul>
            ))}
          </div>
        )}
        {isFetchingNextPage && (
          <p className="jv-asset-picker__more" role="status">
            <Spinner /> Loading more…
          </p>
        )}
      </section>

      {!hideFooter && (
        <AssetGridPickerFooter
          selectedCount={selectedIds.length}
          maxSelection={maxSelection}
          confirmLabel={confirmLabel}
          onClear={onClear}
          onConfirm={onConfirm}
        />
      )}

      {capHit && (
        <p className="jv-asset-picker__cap" role="alert">
          You can add up to {maxSelection} at a time. Deselect one to choose
          another.
        </p>
      )}
    </div>
  );
}

export function AssetGridPickerFooter({
  selectedCount,
  maxSelection = DEFAULT_MAX_SELECTION,
  confirmLabel,
  onClear,
  onConfirm,
}: {
  selectedCount: number;
  maxSelection?: number;
  confirmLabel: string;
  onClear: () => void;
  onConfirm: () => void;
}) {
  const atCap = selectedCount >= maxSelection;
  return (
    <div className="jv-asset-picker__footer">
      <div className="jv-asset-picker__count" aria-live="polite">
        {selectedCount > 0 ? (
          <>
            <span>
              {selectedCount} selected
              {atCap ? ` (max ${maxSelection})` : ""}
            </span>
            <Button variant="ghost" size="sm" onClick={onClear}>
              Clear
            </Button>
          </>
        ) : (
          <span className="jv-caption">Select photos and videos to add</span>
        )}
      </div>
      <Button
        variant="primary"
        disabled={selectedCount === 0}
        onClick={onConfirm}
      >
        {confirmLabel}
      </Button>
    </div>
  );
}

function AssetTile({
  item,
  selected,
  disabled,
  onToggle,
}: {
  item: AssetGridItem;
  selected: boolean;
  disabled: boolean;
  onToggle: () => void;
}) {
  const [broken, setBroken] = useState(false);
  return (
    // biome-ignore lint/a11y/useSemanticElements: a native checkbox cannot host the thumbnail and overlay; toggle-button + aria-checked is the accessible equivalent.
    <button
      type="button"
      role="checkbox"
      aria-checked={selected}
      aria-label={item.label}
      // A tile past the cap stays focusable so the cap alert is reachable —
      // hence aria-disabled, not the disabled attribute.
      aria-disabled={disabled || undefined}
      className={cx("jv-asset-tile", selected && "is-selected")}
      onClick={onToggle}
    >
      {broken ? (
        <span className="jv-asset-tile__glyph">
          <ImageOff aria-hidden="true" size={20} />
        </span>
      ) : (
        <img
          src={item.thumbUrl}
          alt=""
          loading="lazy"
          decoding="async"
          onError={() => setBroken(true)}
        />
      )}
      {item.badge === "video" && (
        <span className="jv-asset-tile__badge" aria-hidden="true">
          <Play size={13} />
          {typeof item.durationSec === "number" && item.durationSec > 0 && (
            <span>{formatDuration(item.durationSec)}</span>
          )}
        </span>
      )}
      <span className="jv-asset-tile__check" aria-hidden="true">
        <Check size={14} />
      </span>
    </button>
  );
}

function formatDuration(totalSeconds: number): string {
  const seconds = Math.round(totalSeconds);
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}
