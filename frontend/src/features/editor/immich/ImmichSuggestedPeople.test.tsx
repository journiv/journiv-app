import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../../api/client/api";
import { ApiError } from "../../../api/client/errors";
import type { MomentImmichPeopleSuggestionsResponse } from "../../../api/generated/types.gen";
import { ImmichSuggestedPeople } from "./ImmichSuggestedPeople";

vi.mock("../../../api/client/api", () => ({
  api: { immichPeopleSuggestions: vi.fn() },
}));

const suggestionsFor = (
  names: [string, string][],
): MomentImmichPeopleSuggestionsResponse => ({
  people: names.map(([id, name]) => ({ id, name })),
  source_asset_ids: Object.fromEntries(names.map(([id]) => [id, ["asset-1"]])),
});

function setup(
  props: Partial<Parameters<typeof ImmichSuggestedPeople>[0]> = {},
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const onAdd = props.onAdd ?? vi.fn();
  const onAddAll = props.onAddAll ?? vi.fn();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  render(
    <ImmichSuggestedPeople
      momentId="moment-1"
      enabled
      selectedIds={new Set()}
      busy={false}
      onAdd={onAdd}
      onAddAll={onAddAll}
      {...props}
    />,
    { wrapper },
  );
  return { onAdd, onAddAll };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.immichPeopleSuggestions).mockResolvedValue(
    suggestionsFor([["p-ada", "Ada"]]),
  );
});

describe("ImmichSuggestedPeople", () => {
  it("does not query or render when disabled", async () => {
    setup({ enabled: false });
    await Promise.resolve();
    expect(api.immichPeopleSuggestions).not.toHaveBeenCalled();
    expect(screen.queryByText("Suggested from Immich")).toBeNull();
  });

  it("does not query when there is no moment id yet", async () => {
    setup({ momentId: undefined });
    await Promise.resolve();
    expect(api.immichPeopleSuggestions).not.toHaveBeenCalled();
  });

  it("renders nothing when the face index returns no people", async () => {
    vi.mocked(api.immichPeopleSuggestions).mockResolvedValue(
      suggestionsFor([]),
    );
    setup();
    await waitFor(() =>
      expect(api.immichPeopleSuggestions).toHaveBeenCalledWith("moment-1"),
    );
    expect(screen.queryByText("Suggested from Immich")).toBeNull();
  });

  it("shows a chip per suggested person and adds one on click", async () => {
    const { onAdd } = setup();
    const chip = await screen.findByRole("button", { name: /Ada/ });
    await userEvent.click(chip);
    expect(onAdd).toHaveBeenCalledWith("p-ada");
  });

  it("hides people already on the moment", async () => {
    vi.mocked(api.immichPeopleSuggestions).mockResolvedValue(
      suggestionsFor([
        ["p-ada", "Ada"],
        ["p-bob", "Bob"],
      ]),
    );
    setup({ selectedIds: new Set(["p-bob"]) });
    expect(await screen.findByRole("button", { name: /Ada/ })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Bob/ })).toBeNull();
  });

  it("offers Add all for more than one suggestion", async () => {
    vi.mocked(api.immichPeopleSuggestions).mockResolvedValue(
      suggestionsFor([
        ["p-ada", "Ada"],
        ["p-bob", "Bob"],
      ]),
    );
    const { onAddAll } = setup();
    await userEvent.click(
      await screen.findByRole("button", { name: "Add all" }),
    );
    expect(onAddAll).toHaveBeenCalledWith(["p-ada", "p-bob"]);
  });

  it("disables the chips while a people write is in flight", async () => {
    setup({ busy: true });
    const chip = await screen.findByRole("button", { name: /Ada/ });
    expect((chip as HTMLButtonElement).disabled).toBe(true);
  });

  it("shows a quiet retry note — not an alert — when the lookup fails", async () => {
    vi.mocked(api.immichPeopleSuggestions).mockRejectedValue(
      new ApiError("nope", { status: 400 }),
    );
    setup();
    const note = await screen.findByText(/Couldn’t check Immich for people/);
    expect(note.closest('[role="alert"]')).toBeNull();
    expect(note.closest('[role="status"]')).toBeTruthy();

    vi.mocked(api.immichPeopleSuggestions).mockResolvedValue(
      suggestionsFor([["p-ada", "Ada"]]),
    );
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Suggested from Immich")).toBeTruthy();
  });
});
