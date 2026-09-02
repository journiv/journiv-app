import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { sessionStore } from "../../api/auth/session";
import { api } from "../../api/client/api";
import type {
  InstanceConfigResponse,
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
    createTag: vi.fn(),
    mergeTags: vi.fn(),
    deleteTag: vi.fn(),
    deleteUnusedTags: vi.fn(),
    tagAnalytics: vi.fn(),
    tagDetailAnalytics: vi.fn(),
    tagMoments: vi.fn(),
    updateTag: vi.fn(),
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

const tag = (
  name: string,
  usage_count: number,
  created_at = now,
): TagResponse => ({
  id: `tag-${name}`,
  user_id: user.id,
  name,
  usage_count,
  created_at,
  updated_at: created_at,
});

const travel = tag("travel", 8, "2026-01-02T00:00:00Z");
const food = tag("food", 3, "2026-03-02T00:00:00Z");
const orphan = tag("orphan", 0, "2026-05-02T00:00:00Z");
const allTags = [travel, food, orphan];

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

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  sessionStore.write({ version: 1, accessToken: "a", refreshToken: "r" });
  vi.mocked(api.me).mockResolvedValue(user);
  vi.mocked(api.journals).mockResolvedValue([]);
  vi.mocked(api.instanceConfig).mockResolvedValue(
    config({
      available: true,
      tier: "member",
      upgrade_url: "https://journiv.com/plus",
    }),
  );
  vi.mocked(api.tags).mockResolvedValue(allTags);
  vi.mocked(api.createTag).mockResolvedValue(tag("new-tag", 0));
  vi.mocked(api.mergeTags).mockResolvedValue(travel);
  vi.mocked(api.deleteTag).mockResolvedValue(undefined);
  vi.mocked(api.deleteUnusedTags).mockResolvedValue({ deleted: 1 });
  vi.mocked(api.tagAnalytics).mockResolvedValue({} as never);
});

async function view(path = "/library/tags") {
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
  await screen.findByRole("heading", { name: "Tags" });
  return router;
}

describe("Library · Tags", () => {
  it("renders a flat, most-used-first card grid with counts", async () => {
    await view();
    await screen.findByText("travel");
    // `LibraryRow` renders a stock `Item`, so the title is addressed by the
    // registry's own slot rather than by a Journiv class.
    const names = screen
      .getAllByText((_, el) =>
        Boolean(el?.getAttribute("data-slot") === "item-title"),
      )
      .map((n) => n.textContent);
    expect(names).toEqual(["travel", "food", "orphan"]);
    expect(screen.getByText(/8 moments · added/)).toBeTruthy();
    // Each card links to its detail route.
    const travelCard = screen
      .getByText("travel")
      .closest("a") as HTMLAnchorElement;
    expect(travelCard.getAttribute("href")).toContain(
      "/library/tags/tag-travel",
    );
    expect(
      screen.getByRole("link", { name: "Tags" }).getAttribute("aria-current"),
    ).toBe("page");
  });

  it("shows the free summary tiles computed from the tag list", async () => {
    await view();
    const insights = screen.getByLabelText("Tag insights");
    expect(within(insights).getByText("Total").nextSibling?.textContent).toBe(
      "3",
    );
    expect(within(insights).getByText("Unused").nextSibling?.textContent).toBe(
      "1",
    );
  });

  it("offers a Plus upsell for the analytics, not an error, when unlicensed", async () => {
    await view();
    const link = await screen.findByRole("link", { name: "Journiv Plus" });
    expect(link.getAttribute("href")).toBe("https://journiv.com/plus");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("cleans up unused tags after confirmation", async () => {
    await view();
    await userEvent.click(
      screen.getByRole("button", { name: /clean up 1 unused/i }),
    );
    const dialog = await screen.findByRole("alertdialog", {
      name: /clean up unused tags/i,
    });
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Delete 1" }),
    );
    await waitFor(() => expect(api.deleteUnusedTags).toHaveBeenCalledTimes(1));
  });

  it("merges a tag into another via the row menu", async () => {
    await view();
    await userEvent.click(screen.getByRole("button", { name: "food actions" }));
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "Merge into…" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: /merge #food into/i,
    });
    await userEvent.click(
      within(dialog).getByRole("radio", { name: /travel/ }),
    );
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Merge tags" }),
    );
    await waitFor(() =>
      expect(api.mergeTags).toHaveBeenCalledWith("tag-food", "tag-travel"),
    );
  });

  it("filters the list by search", async () => {
    await view();
    await userEvent.type(
      screen.getByRole("textbox", { name: "Search tags" }),
      "foo",
    );
    await waitFor(() => expect(screen.queryByText("travel")).toBeNull());
    expect(screen.getByText("food")).toBeTruthy();
  });
});
