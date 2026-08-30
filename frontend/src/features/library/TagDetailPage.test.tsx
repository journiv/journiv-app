import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { sessionStore } from "../../api/auth/session";
import { api } from "../../api/client/api";
import type {
  InstanceConfigResponse,
  TagDetailAnalyticsResponse,
  TaggedMomentSummary,
  TagResponse,
  UserResponse,
} from "../../api/generated/types.gen";
import { createAppQueryClient } from "../../app/queryClient";
import { createAppRouter } from "../../app/router";

vi.mock("../../api/client/api", () => ({
  api: {
    me: vi.fn(),
    journals: vi.fn(),
    instanceConfig: vi.fn(),
    tags: vi.fn(),
    updateTag: vi.fn(),
    deleteTag: vi.fn(),
    mergeTags: vi.fn(),
    deleteUnusedTags: vi.fn(),
    tagAnalytics: vi.fn(),
    tagDetailAnalytics: vi.fn(),
    tagMoments: vi.fn(),
    createTag: vi.fn(),
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
const travel: TagResponse = {
  id: "tag-travel",
  user_id: user.id,
  name: "travel",
  usage_count: 4,
  created_at: "2026-01-02T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
};
const work: TagResponse = {
  ...travel,
  id: "tag-work",
  name: "work",
  usage_count: 2,
};

const moment: TaggedMomentSummary = {
  id: "moment-1",
  logged_at_utc: "2026-02-10T18:00:00Z",
  logged_date_tz: "2026-02-10",
  entry: null,
  note: "a note about the trip",
  primary_mood_id: null,
  media_count: 0,
  media: [],
};

const analytics: TagDetailAnalyticsResponse = {
  tag_id: travel.id,
  tag_name: travel.name,
  usage_count: 4,
  usage_over_time: { "2026-01": 1, "2026-02": 3 },
  first_used: "2026-01-05T00:00:00Z",
  last_used: "2026-02-20T00:00:00Z",
  peak_month: { month: "2026-02", count: 3 },
  trend: "increasing",
  growth_rate: 42,
  days_analyzed: 365,
};

const config = (
  plus: InstanceConfigResponse["plus"],
): InstanceConfigResponse => ({
  import_export_max_file_size_mb: 100,
  max_file_size_mb: 50,
  disable_signup: false,
  oidc_enabled: false,
  oidc_only: false,
  plus,
});

const MEMBER = {
  available: true,
  tier: "member",
  upgrade_url: "https://journiv.com/plus",
};
const SUPPORTER = { ...MEMBER, tier: "supporter" };
const NO_BUILD = { ...MEMBER, available: false };

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  sessionStore.write({ version: 1, accessToken: "a", refreshToken: "r" });
  vi.mocked(api.me).mockResolvedValue(user);
  vi.mocked(api.journals).mockResolvedValue([]);
  vi.mocked(api.instanceConfig).mockResolvedValue(config(MEMBER));
  vi.mocked(api.tags).mockResolvedValue([travel, work]);
  vi.mocked(api.tagMoments).mockResolvedValue([moment]);
  vi.mocked(api.tagDetailAnalytics).mockResolvedValue(analytics);
  vi.mocked(api.updateTag).mockResolvedValue({ ...travel, name: "travels" });
  vi.mocked(api.deleteTag).mockResolvedValue(undefined);
  vi.mocked(api.mergeTags).mockResolvedValue(work);
});

async function view(path = "/library/tags/tag-travel") {
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
  await screen.findByText("#travel");
  return router;
}

describe("Library · Tag detail", () => {
  it("is a pushed page, not a third pane: breadcrumb back, no list", async () => {
    await view();
    // The workspace list (its "New tag" primary) is not mounted alongside.
    expect(screen.queryByRole("button", { name: /new tag/i })).toBeNull();
    const nav = screen.getByRole("navigation", { name: "breadcrumb" });
    const crumb = within(nav).getByRole("link", { name: "Tags" });
    expect(crumb.getAttribute("href")).toContain("/library/tags");
    expect(within(nav).getByText("#travel")).toBeTruthy();
  });

  it("shows the tag, its counts and a moments preview", async () => {
    await view();
    expect(screen.getByText(/4 moments · added/)).toBeTruthy();
    expect(await screen.findByText("a note about the trip")).toBeTruthy();
    expect(api.tagDetailAnalytics).not.toHaveBeenCalled();
  });

  it("locks analytics behind Plus with an upsell, never an error", async () => {
    await view();
    expect(
      await screen.findByText("Tag analytics is part of Journiv Plus"),
    ).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("says analytics is not in the build when Plus is unavailable", async () => {
    vi.mocked(api.instanceConfig).mockResolvedValue(config(NO_BUILD));
    await view();
    expect(
      await screen.findByText("Tag analytics is not included in this build"),
    ).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Learn about Plus" })).toBeNull();
  });

  it("renders the analytics for a Supporter licence", async () => {
    vi.mocked(api.instanceConfig).mockResolvedValue(config(SUPPORTER));
    await view();
    await waitFor(() => expect(api.tagDetailAnalytics).toHaveBeenCalled());
    expect(await screen.findByText("Trending up")).toBeTruthy();
    expect(screen.getByText("2026-02 (3)")).toBeTruthy();
  });

  it("renames the tag", async () => {
    await view();
    await userEvent.click(screen.getByRole("button", { name: "Rename" }));
    const dialog = await screen.findByRole("dialog", {
      name: /rename #travel/i,
    });
    const input = within(dialog).getByLabelText("Tag name");
    await userEvent.clear(input);
    await userEvent.type(input, "travels");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(api.updateTag).toHaveBeenCalledWith("tag-travel", {
        name: "travels",
      }),
    );
  });

  it("deletes the tag and returns to the list", async () => {
    const router = await view();
    await userEvent.click(
      screen.getByRole("button", { name: "travel actions" }),
    );
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "Delete tag…" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: /delete #travel/i,
    });
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Delete tag" }),
    );
    await waitFor(() =>
      expect(api.deleteTag).toHaveBeenCalledWith("tag-travel"),
    );
    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/library/tags"),
    );
    expect(screen.queryByText("Tag not found")).toBeNull();
  });
});
