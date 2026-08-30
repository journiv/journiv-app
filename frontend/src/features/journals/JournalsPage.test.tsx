import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { sessionStore } from "../../api/auth/session";
import { api } from "../../api/client/api";
import type {
  JournalResponse,
  UserResponse,
} from "../../api/generated/types.gen";
import { createAppQueryClient } from "../../app/queryClient";
import { createAppRouter } from "../../app/router";

vi.mock("../../api/client/api", () => ({
  api: {
    me: vi.fn(),
    journals: vi.fn(),
    moments: vi.fn(),
    createJournal: vi.fn(),
    updateJournal: vi.fn(),
    toggleJournalFavorite: vi.fn(),
    archiveJournal: vi.fn(),
    unarchiveJournal: vi.fn(),
    reorderJournals: vi.fn(),
    deleteJournal: vi.fn(),
  },
}));

const now = "2026-08-20T08:00:00Z";
const user: UserResponse = {
  id: "u1",
  email: "j@example.com",
  name: "J",
  role: "user",
  is_active: true,
  created_at: now,
  updated_at: now,
};

const journal = (
  over: Partial<JournalResponse> & { id: string },
): JournalResponse => ({
  user_id: "u1",
  title: over.id,
  is_favorite: false,
  is_archived: false,
  position: null,
  entry_count: 0,
  total_words: 0,
  created_at: now,
  updated_at: now,
  ...over,
});

const running = journal({
  id: "running",
  title: "Running",
  position: 0,
  entry_count: 12,
  total_words: 3400,
  last_entry_at: "2026-08-18T09:00:00Z",
});
const personal = journal({ id: "personal", title: "Personal", position: 1 });
const oldTrip = journal({ id: "trip", title: "Old trip", is_archived: true });

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  sessionStore.write({ version: 1, accessToken: "a", refreshToken: "r" });
  vi.mocked(api.me).mockResolvedValue(user);
  vi.mocked(api.journals).mockResolvedValue([running, personal, oldTrip]);
  vi.mocked(api.moments).mockResolvedValue({ items: [] });
  vi.mocked(api.createJournal).mockResolvedValue(
    journal({ id: "new", title: "Ideas" }),
  );
  vi.mocked(api.toggleJournalFavorite).mockResolvedValue({
    ...running,
    is_favorite: true,
  });
  vi.mocked(api.archiveJournal).mockResolvedValue({
    ...personal,
    is_archived: true,
  });
  vi.mocked(api.reorderJournals).mockResolvedValue(undefined as never);
  vi.mocked(api.deleteJournal).mockResolvedValue(undefined as never);
});

async function renderAt(path: string) {
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

/** The management pane, scoped away from the sidebar (both are named "Journals"). */
function pane() {
  return within(screen.getByRole("region", { name: "Journals" }));
}

describe("Journals management pane", () => {
  it("lists active journals and hides archived behind a disclosure", async () => {
    await renderAt("/journals");

    expect(
      await screen.findByRole("heading", { name: "Journals" }),
    ).toBeTruthy();
    expect(pane().getByRole("link", { name: /Running/ })).toBeTruthy();
    // Stats line is shown (entry_count included per the product decision).
    expect(pane().getByText(/12 entries · 3,400 words/)).toBeTruthy();

    // Archived journals live in a disclosure, collapsed by default — the route
    // the sidebar never offered.
    const details = pane()
      .getByText("Archived (1)")
      .closest("details") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    await userEvent.click(pane().getByText("Archived (1)"));
    expect(details.open).toBe(true);
    expect(pane().getByRole("link", { name: /Old trip/ })).toBeTruthy();
  });

  it("creates a journal with the chosen colour and icon", async () => {
    await renderAt("/journals");
    await userEvent.click(
      await screen.findByRole("button", { name: "New journal" }),
    );

    await userEvent.type(screen.getByLabelText("Title"), "Ideas");
    await userEvent.click(screen.getByRole("radio", { name: "Blue" }));
    await userEvent.click(screen.getByRole("radio", { name: "Lightbulb" }));
    await userEvent.click(
      screen.getByRole("button", { name: "Create journal" }),
    );

    await waitFor(() =>
      expect(api.createJournal).toHaveBeenCalledWith({
        title: "Ideas",
        description: null,
        color: "#3B82F6",
        icon: "lightbulb",
      }),
    );
  });

  it("blocks empty titles", async () => {
    await renderAt("/journals");
    await userEvent.click(
      await screen.findByRole("button", { name: "New journal" }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Create journal" }),
    );
    expect(await screen.findByText("Give the journal a title.")).toBeTruthy();
    expect(api.createJournal).not.toHaveBeenCalled();
  });

  it("toggles favourite from the row", async () => {
    await renderAt("/journals");
    await userEvent.click(
      await screen.findByRole("button", { name: "Add Running to favourites" }),
    );
    await waitFor(() =>
      expect(api.toggleJournalFavorite).toHaveBeenCalledWith("running"),
    );
  });

  it("archives a journal from its action menu", async () => {
    await renderAt("/journals");
    await userEvent.click(
      await screen.findByRole("button", { name: "Personal actions" }),
    );
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "Archive" }),
    );
    await waitFor(() =>
      expect(api.archiveJournal).toHaveBeenCalledWith("personal"),
    );
  });

  it("reorders within the peer group via Move down", async () => {
    await renderAt("/journals");
    await userEvent.click(
      await screen.findByRole("button", { name: "Running actions" }),
    );
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "Move down" }),
    );
    await waitFor(() =>
      expect(api.reorderJournals).toHaveBeenCalledWith({
        updates: [
          { id: "personal", position: 0 },
          { id: "running", position: 1 },
        ],
      }),
    );
  });

  it("requires typing the title before deleting", async () => {
    await renderAt("/journals");
    await userEvent.click(
      await screen.findByRole("button", { name: "Running actions" }),
    );
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "Delete…" }),
    );

    const del = (await screen.findByRole("button", {
      name: "Delete journal",
    })) as HTMLButtonElement;
    expect(del.disabled).toBe(true);
    await userEvent.type(
      screen.getByLabelText(/Type .* to confirm/),
      "Running",
    );
    expect(del.disabled).toBe(false);
    await userEvent.click(del);
    await waitFor(() =>
      expect(api.deleteJournal).toHaveBeenCalledWith("running"),
    );
  });
});

describe("Sidebar journal navigation", () => {
  it("lists active journals (favourites first) plus an All journals entry", async () => {
    vi.mocked(api.journals).mockResolvedValue([
      personal,
      { ...running, is_favorite: true },
      oldTrip,
    ]);
    await renderAt("/timeline");

    const nav = await screen.findByRole("navigation", { name: "Journals" });
    const links = within(nav)
      .getAllByRole("link")
      .map((el) => el.textContent);
    // Favourite sorts to the top; the non-favourite is still there; archived
    // never appears in the rail.
    expect(links).toEqual(["Running", "Personal", "All journals"]);
  });

  it("truncates a long list but always keeps All journals", async () => {
    vi.mocked(api.journals).mockResolvedValue(
      Array.from({ length: 12 }, (_, i) =>
        journal({ id: `j${i}`, title: `Journal ${i}`, position: i }),
      ),
    );
    await renderAt("/timeline");

    const nav = await screen.findByRole("navigation", { name: "Journals" });
    const links = within(nav).getAllByRole("link");
    // 8 journals + the All journals entry.
    expect(links).toHaveLength(9);
    expect(links.at(-1)?.textContent).toBe("All journals");
  });

  it("keeps every journal visible after one is favourited", async () => {
    vi.mocked(api.journals).mockResolvedValue([running, personal]);
    vi.mocked(api.toggleJournalFavorite).mockResolvedValue({
      ...running,
      is_favorite: true,
    });
    await renderAt("/journals");

    await userEvent.click(
      await screen.findByRole("button", { name: "Add Running to favourites" }),
    );

    const nav = await screen.findByRole("navigation", { name: "Journals" });
    await waitFor(() =>
      expect(
        within(nav)
          .getAllByRole("link")
          .map((el) => el.textContent),
      ).toEqual(["Running", "Personal", "All journals"]),
    );
  });
});
