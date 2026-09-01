import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AssetGridPicker } from "./AssetGridPicker";
import type { AssetGridData, AssetGridItem } from "./assetGrid.types";

// jsdom has no layout, so the real virtualizer would render zero rows. This
// stand-in renders every row; the windowing maths is covered by
// useVirtualGrid.test.ts.
vi.mock("@tanstack/react-virtual", () => ({
  useVirtualizer: ({ count }: { count: number }) => ({
    getTotalSize: () => count * 140,
    getVirtualItems: () =>
      Array.from({ length: count }, (_, index) => ({
        key: index,
        index,
        start: index * 140,
        size: 140,
      })),
    measure: () => {},
    measureElement: () => {},
  }),
}));

const item = (
  id: string,
  over: Partial<AssetGridItem> = {},
): AssetGridItem => ({
  id,
  thumbUrl: `/thumb/${id}`,
  label: `Photo ${id}`,
  badge: null,
  ...over,
});

function makeSource(over: Partial<AssetGridData> = {}) {
  const data: AssetGridData = {
    items: [item("a"), item("b"), item("c")],
    isLoading: false,
    isFetchingNextPage: false,
    hasNextPage: false,
    fetchNextPage: vi.fn(),
    isError: false,
    refetch: vi.fn(),
    ...over,
  };
  return {
    data,
    source: {
      useItems: () => data,
      empty: { title: "No photos in Immich yet" },
      error: { title: "Immich needs reconnecting", description: "Bad key" },
    },
  };
}

function setup(
  over: {
    data?: Partial<AssetGridData>;
    selectedIds?: string[];
    maxSelection?: number;
  } = {},
) {
  const { data, source } = makeSource(over.data);
  const handlers = {
    onToggle: vi.fn(),
    onClear: vi.fn(),
    onConfirm: vi.fn(),
  };
  render(
    <AssetGridPicker
      source={source}
      selectedIds={over.selectedIds ?? []}
      confirmLabel={`Add ${(over.selectedIds ?? []).length}`}
      maxSelection={over.maxSelection}
      {...handlers}
    />,
  );
  return { data, ...handlers };
}

describe("AssetGridPicker", () => {
  it("shows a skeleton and no tiles while the first page loads", () => {
    setup({ data: { isLoading: true, items: [] } });
    expect(screen.queryAllByRole("checkbox")).toHaveLength(0);
    expect(screen.queryByText(/No photos/)).toBeNull();
  });

  it("renders the empty state when a load returns nothing", () => {
    setup({ data: { items: [] } });
    expect(screen.getByText("No photos in Immich yet")).toBeTruthy();
  });

  it("renders the error state and retries", async () => {
    const { data } = setup({ data: { isError: true, items: [] } });
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(data.refetch).toHaveBeenCalledTimes(1);
  });

  it("toggles a tile through the controlled handler", async () => {
    const { onToggle } = setup();
    await userEvent.click(screen.getByRole("checkbox", { name: "Photo a" }));
    expect(onToggle).toHaveBeenCalledWith("a");
  });

  it("reflects controlled selection and clears it", async () => {
    const { onClear } = setup({ selectedIds: ["b"] });
    expect(
      (
        screen.getByRole("checkbox", { name: "Photo b" }) as HTMLElement
      ).getAttribute("aria-checked"),
    ).toBe("true");
    await userEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(onClear).toHaveBeenCalledTimes(1);
  });

  it("blocks a new selection at the cap but still allows deselecting", async () => {
    const { onToggle } = setup({
      selectedIds: ["a", "b"],
      maxSelection: 2,
    });
    await userEvent.click(screen.getByRole("checkbox", { name: "Photo c" }));
    expect(onToggle).not.toHaveBeenCalled();
    expect(screen.getByRole("alert").textContent).toMatch(/up to 2 at a time/);

    await userEvent.click(screen.getByRole("checkbox", { name: "Photo a" }));
    expect(onToggle).toHaveBeenCalledWith("a");
  });

  it("gates confirm on having a selection", async () => {
    const { onConfirm } = setup({ selectedIds: [] });
    const confirm = screen.getByRole("button", { name: "Add 0" });
    expect((confirm as HTMLButtonElement).disabled).toBe(true);
    await userEvent.click(confirm);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("confirms an existing selection", async () => {
    const { onConfirm } = setup({ selectedIds: ["a"] });
    await userEvent.click(screen.getByRole("button", { name: "Add 1" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("pulls the next page when the last rows are in view", () => {
    const { data } = setup({ data: { hasNextPage: true } });
    expect(data.fetchNextPage).toHaveBeenCalledTimes(1);
  });

  it("does not pull again while a fetch is in flight", () => {
    const { data } = setup({
      data: { hasNextPage: true, isFetchingNextPage: true },
    });
    expect(data.fetchNextPage).not.toHaveBeenCalled();
    expect(screen.getByText(/Loading more/)).toBeTruthy();
  });

  it("marks a video tile with a formatted duration", () => {
    setup({
      data: {
        items: [item("v", { badge: "video", durationSec: 75, label: "Clip" })],
      },
    });
    const tile = screen.getByRole("checkbox", { name: "Clip" });
    expect(within(tile).getByText("1:15")).toBeTruthy();
  });
});
