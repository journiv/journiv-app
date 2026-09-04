import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { sessionStore } from "../../api/auth/session";
import { api } from "../../api/client/api";
import type {
  InstanceConfigResponse,
  MoodStatistics,
  MoodStreak,
  ProductivityMetrics,
  UserResponse,
  WritingPatterns,
  WritingStreakAnalytics,
} from "../../api/generated/types.gen";
import { createAppQueryClient } from "../../app/queryClient";
import { createAppRouter } from "../../app/router";
import { shiftIsoDate } from "../../lib/datetime";

vi.mock("../../api/client/api", () => ({
  api: {
    me: vi.fn(),
    journals: vi.fn(),
    instanceConfig: vi.fn(),
    writingStreak: vi.fn(),
    writingPatterns: vi.fn(),
    productivityMetrics: vi.fn(),
    journalAnalytics: vi.fn(),
    moodStatistics: vi.fn(),
    moodStreak: vi.fn(),
  },
}));

const now = "2026-08-28T09:00:00Z";
const user: UserResponse = {
  id: "user-1",
  email: "writer@example.com",
  name: "Writer",
  role: "user",
  is_active: true,
  created_at: now,
  updated_at: now,
};
const instanceConfig: InstanceConfigResponse = {
  import_export_max_file_size_mb: 100,
  max_file_size_mb: 50,
  disable_signup: false,
  oidc_enabled: false,
  oidc_only: false,
  plus: { available: false, tier: "member", upgrade_url: "https://x" },
};

const writingStreak: WritingStreakAnalytics = {
  current_streak: 7,
  longest_streak: 21,
  total_entries: 123,
  total_words: 23456,
  average_words_per_entry: 190.7,
};
const writingPatterns: WritingPatterns = {
  period_days: 30,
  entries_by_day: [
    { date: "2026-08-20", entry_count: 1, total_words: 100 },
    { date: "2026-08-21", entry_count: 2, total_words: 240 },
  ],
  mood_patterns: [],
  top_tags: [],
};
const productivity: ProductivityMetrics = {
  current_month_entries: 12,
  current_month_words: 2400,
  entry_growth_percentage: 20,
  average_daily_entries: 1.2,
  average_words_per_day: 90,
};
const moodStats: MoodStatistics = {
  total_logs: 9,
  date_range: { start_date: "2026-07-29", end_date: "2026-08-28" },
  mood_distribution: { positive: 60, neutral: 30, negative: 10 },
  most_frequent_mood: { name: "content", category: "positive", count: 5 },
  mood_counts: [{ mood: "content", category: "positive", count: 5 }],
  daily_trends: [
    { date: "2026-08-20", category: "positive", count: 2 },
    { date: "2026-08-21", category: "negative", count: 1 },
  ],
};
const moodStreak: MoodStreak = {
  current_streak: 3,
  total_days_logged: 14,
  last_logged_date: "2026-08-28",
};

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  sessionStore.write({ version: 1, accessToken: "a", refreshToken: "r" });
  vi.mocked(api.me).mockResolvedValue(user);
  vi.mocked(api.journals).mockResolvedValue([]);
  vi.mocked(api.instanceConfig).mockResolvedValue(instanceConfig);
  vi.mocked(api.writingStreak).mockResolvedValue(writingStreak);
  vi.mocked(api.writingPatterns).mockResolvedValue(writingPatterns);
  vi.mocked(api.productivityMetrics).mockResolvedValue(productivity);
  vi.mocked(api.journalAnalytics).mockResolvedValue({
    journals: [
      {
        journal_id: "j-1",
        title: "Daily notes",
        entry_count: 100,
        total_words: 20000,
        last_entry: now,
      },
    ],
  });
  vi.mocked(api.moodStatistics).mockResolvedValue(moodStats);
  vi.mocked(api.moodStreak).mockResolvedValue(moodStreak);
});

async function view(path = "/insights?tab=overview&period=30") {
  const router = createAppRouter(
    createMemoryHistory({ initialEntries: [path] }),
  );
  const queryClient = createAppQueryClient();
  queryClient.setDefaultOptions({ queries: { retry: false } });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  await router.load();
  await screen.findByRole("heading", { name: "Insights", level: 1 });
  return router;
}

describe("Insights", () => {
  it("shows the summary strip and the Overview tab, and does not fetch other tabs", async () => {
    await view();

    expect(await screen.findByText("123")).toBeTruthy();
    expect(screen.getByText("Writing streak")).toBeTruthy();
    expect(screen.getByText("23,456")).toBeTruthy();
    expect(screen.getByText("191")).toBeTruthy();

    // Overview is the default tab; its queries run.
    await waitFor(() => expect(api.writingPatterns).toHaveBeenCalledWith(30));
    expect(api.productivityMetrics).toHaveBeenCalled();

    // Mood / Journals panels are not mounted, so their queries never fired.
    expect(api.moodStatistics).not.toHaveBeenCalled();
    expect(api.moodStreak).not.toHaveBeenCalled();
    expect(api.journalAnalytics).not.toHaveBeenCalled();
  });

  it("switches to the Mood tab, keeping the period in the URL", async () => {
    const router = await view("/insights?tab=overview&period=90");

    await userEvent.click(screen.getByRole("tab", { name: "Mood" }));

    await waitFor(() => {
      expect(router.state.location.search.tab).toBe("mood");
      expect(router.state.location.search.period).toBe(90);
    });
    await waitFor(() => expect(api.moodStatistics).toHaveBeenCalled());
    expect(await screen.findByText("Most frequent")).toBeTruthy();
    expect(screen.getByText("Content")).toBeTruthy();
  });

  it("requests exactly the selected number of inclusive mood dates", async () => {
    await view("/insights?tab=mood&period=7");

    await waitFor(() => expect(api.moodStatistics).toHaveBeenCalled());
    const [start, end] = vi.mocked(api.moodStatistics).mock.calls[0];
    expect(start).toBe(shiftIsoDate(end, -6));
  });

  it("shows unavailable placeholders when the mood streak cannot load", async () => {
    vi.mocked(api.moodStreak).mockRejectedValue(new Error("offline"));
    await view("/insights?tab=mood&period=30");

    expect(await screen.findAllByText("—")).toHaveLength(2);
  });

  it("changes the Trend period and refetches the writing trend", async () => {
    const router = await view("/insights?tab=overview&period=30");
    await waitFor(() => expect(api.writingPatterns).toHaveBeenCalledWith(30));

    await userEvent.selectOptions(screen.getByLabelText("Trend period"), "90");

    await waitFor(() => expect(router.state.location.search.period).toBe(90));
    await waitFor(() => expect(api.writingPatterns).toHaveBeenCalledWith(90));
  });

  it("shows a retry error state when the summary fails", async () => {
    vi.mocked(api.writingStreak).mockRejectedValue(new Error("offline"));
    await view();

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Summary could not be loaded")).toBeTruthy();
    expect(
      within(alert).getByRole("button", { name: "Try again" }),
    ).toBeTruthy();
  });

  it("shows an empty message on the Mood tab when nothing is logged", async () => {
    vi.mocked(api.moodStatistics).mockResolvedValue({
      ...moodStats,
      total_logs: 0,
      most_frequent_mood: undefined,
      mood_counts: [],
      daily_trends: [],
      mood_distribution: {},
    });
    await view("/insights?tab=mood&period=30");

    expect(
      await screen.findAllByText("No moods logged in this period yet."),
    ).not.toHaveLength(0);
  });

  it("lists per-journal analytics on the Journals tab with an All time note", async () => {
    await view("/insights?tab=journals&period=30");

    expect(await screen.findByText("All time")).toBeTruthy();
    const link = await screen.findByRole("link", { name: "Daily notes" });
    expect(link.getAttribute("href")).toContain("/journals/j-1");
    expect(screen.getByText("100")).toBeTruthy();
    expect(api.moodStatistics).not.toHaveBeenCalled();
  });
});
