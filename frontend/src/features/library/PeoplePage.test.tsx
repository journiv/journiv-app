import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client/api";
import { sessionStore } from "../../api/auth/session";
import type {
  PersonGroupWithPeopleResponse,
  PersonResponse,
  UserResponse,
} from "../../api/generated/types.gen";
import { createAppQueryClient } from "../../app/queryClient";
import { createAppRouter } from "../../app/router";

vi.mock("../../api/client/api", () => ({
  api: {
    me: vi.fn(),
    journals: vi.fn(),
    people: vi.fn(),
    personGroups: vi.fn(),
    createPerson: vi.fn(),
    updatePerson: vi.fn(),
    archivePerson: vi.fn(),
    mergePeople: vi.fn(),
    uploadPersonImage: vi.fn(),
    removePersonImage: vi.fn(),
    createPersonGroup: vi.fn(),
    updatePersonGroup: vi.fn(),
    deletePersonGroup: vi.fn(),
  },
}));

const now = "2026-08-27T09:00:00Z";
const user: UserResponse = {
  id: "user-1",
  email: "writer@example.com",
  name: "Writer",
  role: "user",
  is_active: true,
  created_at: now,
  updated_at: now,
};
const familySummary = { id: "group-family", name: "Family" };
const jane: PersonResponse = {
  id: "person-jane",
  user_id: user.id,
  name: "Jane Doe",
  nickname: "Janie",
  memory_count: 42,
  groups: [familySummary],
  created_at: now,
  updated_at: now,
};
const sam: PersonResponse = {
  id: "person-sam",
  user_id: user.id,
  name: "Sam Doe",
  memory_count: 3,
  groups: [],
  created_at: now,
  updated_at: now,
};
const family: PersonGroupWithPeopleResponse = {
  id: familySummary.id,
  user_id: user.id,
  name: familySummary.name,
  position: 0,
  people: [
    {
      id: jane.id,
      name: jane.name,
      nickname: jane.nickname,
    },
  ],
  created_at: now,
  updated_at: now,
};

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  sessionStore.write({ version: 1, accessToken: "a", refreshToken: "r" });
  vi.mocked(api.me).mockResolvedValue(user);
  vi.mocked(api.journals).mockResolvedValue([]);
  vi.mocked(api.people).mockResolvedValue([jane, sam]);
  vi.mocked(api.personGroups).mockResolvedValue([family]);
  vi.mocked(api.createPerson).mockResolvedValue(jane);
  vi.mocked(api.updatePerson).mockResolvedValue(jane);
});

async function view() {
  const router = createAppRouter(
    createMemoryHistory({
      initialEntries: ["/settings/journaling/people"],
    }),
  );
  const queryClient = createAppQueryClient();
  queryClient.setDefaultOptions({ queries: { retry: false } });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  await router.load();
  await screen.findByRole("heading", { name: "People" });
  return router;
}

describe("Library · People", () => {
  it("renders as a first-class Library route with inline grouped people", async () => {
    await view();

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(
      screen.getByRole("link", { name: "People" }).getAttribute("aria-current"),
    ).toBe("page");
    expect(await screen.findByText("Jane Doe")).toBeTruthy();
    expect(screen.getByText("Janie · 42 moments")).toBeTruthy();
    expect(screen.getByText("Without a group")).toBeTruthy();
  });

  it("keeps the 'Without a group' bucket collapsed until it is opened", async () => {
    await view();
    await screen.findByText("Jane Doe");

    // Jane's group is open by default; the ungrouped fallback bucket is not.
    expect(screen.queryByText("Sam Doe")).toBeNull();
    await userEvent.click(
      screen.getByRole("button", { name: /without a group/i }),
    );
    expect(await screen.findByText("Sam Doe")).toBeTruthy();
  });

  it("shows a group's server member count even when search narrows the rows", async () => {
    const pat: PersonResponse = {
      ...sam,
      id: "person-pat",
      name: "Pat Roe",
      nickname: null,
      memory_count: 1,
      groups: [familySummary],
    };
    vi.mocked(api.people).mockResolvedValue([jane, pat]);
    vi.mocked(api.personGroups).mockResolvedValue([
      {
        ...family,
        people: [
          { id: jane.id, name: jane.name, nickname: jane.nickname },
          { id: pat.id, name: pat.name },
        ],
      },
    ]);
    await view();
    await userEvent.type(screen.getByLabelText("Search people"), "Jane");

    expect(await screen.findByText("2 people")).toBeTruthy();
    expect(screen.queryByText("Pat Roe")).toBeNull();
  });

  it("adds a person to the group chosen from the group's overflow menu", async () => {
    await view();
    await userEvent.click(
      screen.getByRole("button", { name: "Family group actions" }),
    );
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "Add person to group" }),
    );
    const dialog = await screen.findByRole("dialog", { name: "Add person" });
    expect(
      (
        within(dialog).getByRole("checkbox", {
          name: "Family",
        }) as HTMLInputElement
      ).checked,
    ).toBe(true);
    await userEvent.type(within(dialog).getByLabelText("Name"), "Alex Doe");
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Add person" }),
    );

    await waitFor(() =>
      expect(api.createPerson).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "Alex Doe",
          group_ids: [family.id],
        }),
      ),
    );
  });

  it("manages many-to-many membership without replacing other groups", async () => {
    vi.mocked(api.updatePerson).mockResolvedValue({
      ...sam,
      groups: [familySummary],
    });
    await view();
    await userEvent.click(
      screen.getByRole("button", { name: "Family group actions" }),
    );
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "Manage people" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Manage Family",
    });
    await userEvent.click(
      within(dialog).getByRole("checkbox", { name: "Sam Doe" }),
    );
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(api.updatePerson).toHaveBeenCalledWith(sam.id, {
        group_ids: [family.id],
      }),
    );
  });

  it("keeps the archive confirmation open and shows a mutation error", async () => {
    vi.mocked(api.archivePerson).mockRejectedValue(new Error("archive failed"));
    await view();

    await userEvent.click(
      screen.getByRole("button", { name: "Jane Doe actions" }),
    );
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "Archive" }),
    );
    const dialog = await screen.findByRole("alertdialog", {
      name: "Archive Jane Doe?",
    });
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Archive" }),
    );

    expect(
      await within(dialog).findByText(
        "The person could not be archived. Try again.",
      ),
    ).toBeTruthy();
    expect(dialog.isConnected).toBe(true);
  });
});
