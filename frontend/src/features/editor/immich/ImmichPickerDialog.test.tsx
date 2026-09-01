import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../../api/client/api";
import type { IntegrationAssetResponse } from "../../../api/generated/types.gen";
import { createAppQueryClient } from "../../../app/queryClient";
import { setTestViewportWidth } from "../../../test/viewport";
import { ImmichPickerDialog } from "./ImmichPickerDialog";

vi.mock("../../../api/client/api", () => ({
  api: { immichAssets: vi.fn() },
}));

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

const asset = (id: string): IntegrationAssetResponse => ({
  id,
  type: "IMAGE",
  title: `${id}.jpg`,
  taken_at: "2026-08-01T10:00:00Z",
  thumb_url: `/thumb/${id}`,
  original_url: `/orig/${id}`,
});

function setup(
  props: Partial<React.ComponentProps<typeof ImmichPickerDialog>> = {},
) {
  const onOpenChange = vi.fn();
  const onPickDevice = vi.fn();
  const onPickImmich = vi.fn();
  const client = createAppQueryClient();
  client.setDefaultOptions({ queries: { retry: false } });
  render(
    <QueryClientProvider client={client}>
      <ImmichPickerDialog
        open
        onOpenChange={onOpenChange}
        connection="connected"
        importMode="link_only"
        onPickDevice={onPickDevice}
        onPickImmich={onPickImmich}
        {...props}
      />
    </QueryClientProvider>,
  );
  return { onOpenChange, onPickDevice, onPickImmich };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.immichAssets).mockResolvedValue({
    assets: [asset("a"), asset("b")],
    page: 1,
    limit: 100,
    total: 2,
    has_more: false,
  });
});

describe("ImmichPickerDialog", () => {
  it("renders nothing while closed", () => {
    setup({ open: false });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("browses Immich and confirms a selection", async () => {
    const { onPickImmich, onOpenChange } = setup();
    const tile = await screen.findByRole("checkbox", { name: "a.jpg" });
    await userEvent.click(tile);
    await userEvent.click(screen.getByRole("button", { name: "Add 1 item" }));
    expect(onPickImmich).toHaveBeenCalledWith([
      expect.objectContaining({ id: "a" }),
    ]);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it.each([
    ["dialog", 1440, "dialog-content"],
    ["bottom sheet", 390, "drawer-popup"],
  ])("uses the adaptive %s presentation", async (_name, width, slot) => {
    setTestViewportWidth(width);
    setup();
    expect((await screen.findByRole("dialog")).dataset.slot).toBe(slot);
  });

  it("keeps the selected assets when the adaptive primitive swaps", async () => {
    setTestViewportWidth(1440);
    setup();
    await userEvent.click(
      await screen.findByRole("checkbox", { name: "a.jpg" }),
    );

    act(() => setTestViewportWidth(390));

    expect(
      await screen.findByRole("button", { name: "Add 1 item" }),
    ).toBeTruthy();
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
  });

  it("routes the device tab to the native picker", async () => {
    const { onPickDevice, onOpenChange } = setup();
    await userEvent.click(screen.getByRole("tab", { name: "This device" }));
    await userEvent.click(screen.getByRole("button", { name: "Choose files" }));
    expect(onPickDevice).toHaveBeenCalledTimes(1);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("explains link mode and copy mode", async () => {
    setup({ importMode: "copy" });
    expect(await screen.findByText(/copied into Journiv/i)).toBeTruthy();
  });

  it("defaults a disconnected picker to the device tab", async () => {
    setup({ connection: "disconnected" });
    expect(
      await screen.findByRole("button", { name: "Choose files" }),
    ).toBeTruthy();
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(api.immichAssets).not.toHaveBeenCalled();
  });

  it("shows a reconnect prompt on the Immich tab when the key is stale", async () => {
    setup({ connection: "error" });
    await userEvent.click(screen.getByRole("tab", { name: "Immich" }));
    expect(await screen.findByText("Immich needs reconnecting")).toBeTruthy();
    expect(api.immichAssets).not.toHaveBeenCalled();
  });
});
