import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { sessionStore } from "../../api/auth/session";
import { api } from "../../api/client/api";
import type {
  JournalResponse,
  MediaLibraryItem,
  MediaLibraryPageResponse,
  MomentResponse,
  UserResponse,
} from "../../api/generated/types.gen";
import { createAppQueryClient } from "../../app/queryClient";
import { createAppRouter } from "../../app/router";

vi.mock("../../api/client/api", () => ({
  api: {
    me: vi.fn(),
    journals: vi.fn(),
    moods: vi.fn(),
    moments: vi.fn(),
    moment: vi.fn(),
    entry: vi.fn(),
    momentMedia: vi.fn(),
    mediaLibrary: vi.fn(),
  },
}));

const now = "2026-08-10T08:00:00Z";
const user: UserResponse = {
  id: "u1",
  email: "media@example.com",
  name: "Media",
  role: "user",
  is_active: true,
  created_at: now,
  updated_at: now,
};
const journal: JournalResponse = {
  id: "j1",
  user_id: "u1",
  title: "Daily notes",
  is_favorite: false,
  is_archived: false,
  entry_count: 1,
  total_words: 4,
  created_at: now,
  updated_at: now,
};
const photo = (
  over: Partial<MediaLibraryItem> & { id: string },
): MediaLibraryItem => ({
  moment_id: `m-${over.id}`,
  media_type: "image",
  mime_type: "image/jpeg",
  upload_status: "completed",
  signed_thumbnail_url: `https://sig/${over.id}.jpg`,
  created_at: now,
  logged_date_tz: "2026-08-10",
  logged_at_utc: now,
  logged_timezone: "UTC",
  ...over,
});
const moment: MomentResponse = {
  id: "m-a",
  user_id: "u1",
  logged_at_utc: now,
  logged_date_tz: "2026-08-10",
  logged_timezone: "UTC",
  entry: {
    id: "e-a",
    journal_id: journal.id,
    moment_id: "m-a",
    title: "A clear day",
    content_plain_text: "loop",
    created_at: now,
    updated_at: now,
  },
};

const firstPage: MediaLibraryPageResponse = {
  items: [
    photo({ id: "a" }),
    photo({ id: "b", media_type: "video" }),
    photo({
      id: "c",
      logged_date_tz: "2026-07-02",
      logged_at_utc: "2026-07-02T08:00:00Z",
    }),
  ],
  next_cursor_logged_at_utc: "2026-07-02T08:00:00Z",
  next_cursor_id: "c",
};

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  sessionStore.write({ version: 1, accessToken: "a", refreshToken: "r" });
  vi.mocked(api.me).mockResolvedValue(user);
  vi.mocked(api.journals).mockResolvedValue([journal]);
  vi.mocked(api.moods).mockResolvedValue([]);
  vi.mocked(api.mediaLibrary).mockResolvedValue(firstPage);
  vi.mocked(api.moment).mockResolvedValue(moment);
  vi.mocked(api.entry).mockResolvedValue({
    ...moment.entry,
    user_id: "u1",
    content_delta: { ops: [{ insert: "loop\n" }] },
    word_count: 1,
  } as never);
  vi.mocked(api.momentMedia).mockResolvedValue([]);
});

async function renderRoute(path: string) {
  const history = createMemoryHistory({ initialEntries: [path] });
  const router = createAppRouter(history);
  const queryClient = createAppQueryClient();
  queryClient.setDefaultOptions({ queries: { retry: false } });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  await router.load();
  return { ...view, router };
}

describe("MediaPane", () => {
  it("renders a month-grouped grid and opens a tile in the reader keeping the media view", async () => {
    const { router } = await renderRoute("/timeline?view=media");

    expect(await screen.findByRole("heading", { name: "Media" })).toBeTruthy();
    expect(await screen.findByText(/August 2026/)).toBeTruthy();
    expect(screen.getByText(/July 2026/)).toBeTruthy();

    const tiles = await screen.findAllByRole("link", { name: /Photo|Video/ });
    expect(tiles.length).toBeGreaterThanOrEqual(3);

    await userEvent.click(tiles[0]);
    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/timeline/m-a"),
    );
    expect(router.state.location.search.view).toBe("media");
    // The grid is still mounted beside the reader.
    expect(screen.getByRole("heading", { name: "Media" })).toBeTruthy();
  });

  it("paginates with Load more", async () => {
    vi.mocked(api.mediaLibrary).mockResolvedValueOnce(firstPage);
    vi.mocked(api.mediaLibrary).mockResolvedValueOnce({
      items: [
        photo({
          id: "d",
          logged_date_tz: "2026-05-01",
          logged_at_utc: "2026-05-01T08:00:00Z",
        }),
      ],
    });
    await renderRoute("/timeline?view=media");

    await userEvent.click(
      await screen.findByRole("button", { name: "Load more" }),
    );
    expect(await screen.findByText(/May 2026/)).toBeTruthy();
    expect(vi.mocked(api.mediaLibrary)).toHaveBeenCalledTimes(2);
    expect(vi.mocked(api.mediaLibrary).mock.calls[1]?.[0]).toEqual(
      expect.objectContaining({ cursor_id: "c" }),
    );
  });

  it("re-signs a thumbnail once on load error, then shows a broken tile", async () => {
    const { container } = await renderRoute("/timeline?view=media");
    await screen.findByText(/August 2026/);
    const img = container.querySelector("img") as HTMLImageElement;
    expect(img).toBeTruthy();

    vi.mocked(api.mediaLibrary).mockResolvedValue(firstPage);
    img.dispatchEvent(new Event("error"));
    await waitFor(() =>
      expect(vi.mocked(api.mediaLibrary).mock.calls.length).toBeGreaterThan(1),
    );

    const callsAfterFirstError = vi.mocked(api.mediaLibrary).mock.calls.length;
    const again = container.querySelector("img") as HTMLImageElement;
    again.dispatchEvent(new Event("error"));
    // The second failure does not trigger another refetch.
    await new Promise((r) => setTimeout(r, 20));
    expect(vi.mocked(api.mediaLibrary).mock.calls.length).toBe(
      callsAfterFirstError,
    );
  });

  it("shows an empty state when there is no media", async () => {
    vi.mocked(api.mediaLibrary).mockResolvedValue({ items: [] });
    await renderRoute("/timeline?view=media");
    expect(await screen.findByText("No photos yet")).toBeTruthy();
  });

  it("shows an error state with a retry", async () => {
    vi.mocked(api.mediaLibrary).mockRejectedValueOnce(new Error("offline"));
    await renderRoute("/timeline?view=media");
    expect(await screen.findByText("Media could not be loaded")).toBeTruthy();
    vi.mocked(api.mediaLibrary).mockResolvedValueOnce(firstPage);
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText(/August 2026/)).toBeTruthy();
  });
});
