import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client/api";
import type { MomentResponse } from "../../api/generated/types.gen";
import { queryKeys } from "../../api/query/keys";
import { QuickLogSheet } from "./QuickLogSheet";

const navigate = vi.fn();
vi.mock("@tanstack/react-router", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@tanstack/react-router")>()),
  useNavigate: () => navigate,
}));

vi.mock("../../api/client/api", () => ({
  api: {
    moods: vi.fn(async () => [
      {
        id: "mood-happy",
        name: "Happy",
        category: "positive",
        score: 5,
        color_value: 0xff405de6,
        created_at: "",
        updated_at: "",
      },
    ]),
    people: vi.fn(async () => []),
    searchTags: vi.fn(async () => []),
    mediaFormats: vi.fn(async () => ({
      images: [".jpg"],
      videos: [".mp4"],
      audio: [".mp3"],
    })),
    moment: vi.fn(),
    createMoment: vi.fn(),
    updateMoment: vi.fn(),
    deleteMoment: vi.fn(),
  },
}));

const createMoment = vi.mocked(api.createMoment);
const updateMoment = vi.mocked(api.updateMoment);
const deleteMoment = vi.mocked(api.deleteMoment);
const momentGet = vi.mocked(api.moment);

const moment = (over: Partial<MomentResponse> = {}): MomentResponse =>
  ({
    id: "m-new",
    user_id: "u1",
    logged_at_utc: "2026-09-05T09:00:00Z",
    logged_date_tz: "2026-09-05",
    logged_timezone: "UTC",
    tags: [],
    people: [],
    ...over,
  }) as MomentResponse;

const isDisabled = (name: string) =>
  screen.getByRole("button", { name }).hasAttribute("disabled");

function setup() {
  const onOpenChange = vi.fn();
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  render(<QuickLogSheet open onOpenChange={onOpenChange} />, { wrapper });
  return { client, onOpenChange };
}

beforeEach(() => {
  vi.clearAllMocks();
  createMoment.mockResolvedValue(moment() as never);
  updateMoment.mockResolvedValue(moment() as never);
  deleteMoment.mockResolvedValue(undefined as never);
  momentGet.mockResolvedValue(moment() as never);
});

describe("QuickLogSheet", () => {
  it("disables the primary actions until there is something to log", () => {
    setup();
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(isDisabled("Log moment")).toBe(true);
    expect(isDisabled("Continue as full entry")).toBe(true);
  });

  it("logs a note-only moment", async () => {
    const user = userEvent.setup();
    const { onOpenChange } = setup();

    await user.type(screen.getByLabelText("Note"), "Coffee with Sam");
    await waitFor(() => expect(isDisabled("Log moment")).toBe(false));
    await user.click(screen.getByRole("button", { name: "Log moment" }));

    await waitFor(() => expect(createMoment).toHaveBeenCalledTimes(1));
    expect(updateMoment).toHaveBeenCalledWith("m-new", {
      note: "Coffee with Sam",
    });
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it("hands off to the full editor with the seed flag when there is a note", async () => {
    const user = userEvent.setup();
    setup();

    await user.type(screen.getByLabelText("Note"), "longer thought");
    await waitFor(() =>
      expect(isDisabled("Continue as full entry")).toBe(false),
    );
    await user.click(
      screen.getByRole("button", { name: "Continue as full entry" }),
    );

    await waitFor(() =>
      expect(navigate).toHaveBeenCalledWith(
        expect.objectContaining({
          to: "/timeline/$momentId/edit",
          params: { momentId: "m-new" },
          search: { q: "", seedNote: true },
        }),
      ),
    );
    expect(updateMoment).toHaveBeenCalledWith("m-new", {
      note: "longer thought",
    });
  });

  it("confirms before discarding a started capture", async () => {
    const user = userEvent.setup();
    const { onOpenChange } = setup();

    await user.type(screen.getByLabelText("Note"), "half a thought");
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(
      await screen.findByRole("alertdialog", { name: "Discard quick log?" }),
    ).toBeTruthy();
    expect(onOpenChange).not.toHaveBeenCalledWith(false);

    await user.click(screen.getByRole("button", { name: "Discard" }));
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    // The note never reached the server, so nothing to delete.
    expect(deleteMoment).not.toHaveBeenCalled();
  });

  it("does not treat a saved detail as empty before its moment refetch resolves", async () => {
    const user = userEvent.setup();
    setup();
    momentGet.mockReturnValue(new Promise(() => {}) as never);

    await user.click(await screen.findByRole("button", { name: /Happy/ }));
    await waitFor(() =>
      expect(updateMoment).toHaveBeenCalledWith("m-new", {
        primary_mood_id: "mood-happy",
      }),
    );

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(
      await screen.findByRole("alertdialog", { name: "Discard quick log?" }),
    ).toBeTruthy();
  });

  it("invalidates the moment lists after discarding a saved detail", async () => {
    const user = userEvent.setup();
    const { client, onOpenChange } = setup();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    momentGet.mockReturnValue(new Promise(() => {}) as never);

    await user.click(await screen.findByRole("button", { name: /Happy/ }));
    await waitFor(() =>
      expect(updateMoment).toHaveBeenCalledWith("m-new", {
        primary_mood_id: "mood-happy",
      }),
    );
    invalidate.mockClear();

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await user.click(await screen.findByRole("button", { name: "Discard" }));

    await waitFor(() => expect(deleteMoment).toHaveBeenCalledWith("m-new"));
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: queryKeys.allMoments,
    });
  });

  it("closes without a prompt when nothing was entered", async () => {
    const user = userEvent.setup();
    const { onOpenChange } = setup();

    await user.click(screen.getByRole("button", { name: "Cancel" }));

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });
});
