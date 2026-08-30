import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { sessionStore } from "../../api/auth/session";
import { api } from "../../api/client/api";
import type {
  JournalResponse,
  MomentCalendarItem,
  MomentPageResponse,
  MomentResponse,
  MoodResponse,
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
    momentCalendar: vi.fn(),
    mediaLibrary: vi.fn(),
  },
}));

const now = "2026-08-10T08:00:00Z";
const user: UserResponse = {
  id: "u1",
  email: "cal@example.com",
  name: "Cal",
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
const mood: MoodResponse = {
  id: "mood-1",
  name: "Good",
  color_value: 0xff34d058,
  created_at: now,
  updated_at: now,
} as MoodResponse;
const moment: MomentResponse = {
  id: "moment-1",
  user_id: "u1",
  logged_at_utc: now,
  logged_date_tz: "2026-08-10",
  logged_timezone: "UTC",
  entry: {
    id: "entry-1",
    journal_id: journal.id,
    moment_id: "moment-1",
    title: "A clear day",
    content_plain_text: "Walked the long loop.",
    created_at: now,
    updated_at: now,
  },
};
const calendarItems: MomentCalendarItem[] = [
  {
    logged_date_tz: "2026-08-10",
    primary_mood_id: "mood-1",
    moment_count: 2,
    thumbnail_url: null,
  },
];
const dayPage: MomentPageResponse = { items: [moment] };

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  sessionStore.write({ version: 1, accessToken: "a", refreshToken: "r" });
  vi.mocked(api.me).mockResolvedValue(user);
  vi.mocked(api.journals).mockResolvedValue([journal]);
  vi.mocked(api.moods).mockResolvedValue([mood]);
  vi.mocked(api.momentCalendar).mockResolvedValue(calendarItems);
  vi.mocked(api.moments).mockResolvedValue(dayPage);
  vi.mocked(api.moment).mockResolvedValue(moment);
  vi.mocked(api.entry).mockResolvedValue({
    ...moment.entry,
    user_id: "u1",
    content_delta: { ops: [{ insert: "Walked the long loop.\n" }] },
    word_count: 4,
  } as never);
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

describe("CalendarPane", () => {
  it("renders the month grid with a mood-tinted, counted day", async () => {
    await renderRoute("/timeline?view=calendar&month=2026-08");

    expect(
      await screen.findByRole("heading", { name: "Calendar" }),
    ).toBeTruthy();
    expect(screen.getByText(/August 2026/)).toBeTruthy();

    const day = await screen.findByRole("link", { name: /2 moments/ });
    expect(day.getAttribute("aria-label")).toMatch(/August/i);
    expect(day.getAttribute("aria-label")).toMatch(/\b10\b/);
    expect(day.className).toContain("has-mood");
    expect(day.getAttribute("style")).toContain("--mood-accent");

    await waitFor(() =>
      expect(vi.mocked(api.momentCalendar)).toHaveBeenCalledWith(
        expect.objectContaining({
          start_date: "2026-07-26",
          end_date: "2026-09-05",
        }),
      ),
    );
  });

  it("opens the selected day's moments and keeps the calendar mounted when one is read", async () => {
    const { router } = await renderRoute(
      "/timeline?view=calendar&month=2026-08",
    );

    const day = await screen.findByRole("link", { name: /2 moments/ });
    await userEvent.click(day);

    await waitFor(() =>
      expect(router.state.location.search.date).toBe("2026-08-10"),
    );
    expect(await screen.findByText("A clear day")).toBeTruthy();
    await waitFor(() =>
      expect(vi.mocked(api.moments)).toHaveBeenCalledWith(
        expect.objectContaining({
          start_date: "2026-08-10",
          end_date: "2026-08-10",
        }),
      ),
    );

    // Open the moment in the reader — view, month and selected day must survive.
    await userEvent.click(screen.getByText("A clear day"));
    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/timeline/moment-1"),
    );
    expect(router.state.location.search.view).toBe("calendar");
    expect(router.state.location.search.month).toBe("2026-08");
    expect(router.state.location.search.date).toBe("2026-08-10");
    // Both panes are present: the calendar grid and the reader.
    expect(screen.getByText(/August 2026/)).toBeTruthy();
  });

  it("moves between months from the navigation control", async () => {
    const { router } = await renderRoute(
      "/timeline?view=calendar&month=2026-08",
    );
    await userEvent.click(
      await screen.findByRole("button", { name: "Previous month" }),
    );
    await waitFor(() =>
      expect(router.state.location.search.month).toBe("2026-07"),
    );
    expect(screen.getByText(/July 2026/)).toBeTruthy();
  });

  it("jumps to any month and year from the picker dropdowns", async () => {
    const { router } = await renderRoute(
      "/timeline?view=calendar&month=2026-08",
    );

    await userEvent.selectOptions(await screen.findByLabelText("Year"), "2023");
    await waitFor(() =>
      expect(router.state.location.search.month).toBe("2023-08"),
    );

    await userEvent.selectOptions(screen.getByLabelText("Month"), "March");
    await waitFor(() =>
      expect(router.state.location.search.month).toBe("2023-03"),
    );
    expect(screen.getByText(/March 2023/)).toBeTruthy();
  });

  it("shows an error state with a retry when the calendar fails", async () => {
    vi.mocked(api.momentCalendar).mockRejectedValueOnce(new Error("offline"));
    await renderRoute("/timeline?view=calendar&month=2026-08");

    expect(
      await screen.findByText("The calendar could not be loaded"),
    ).toBeTruthy();
    vi.mocked(api.momentCalendar).mockResolvedValueOnce(calendarItems);
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText(/August 2026/)).toBeTruthy();
  });
});
