import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { sessionStore } from "../../api/auth/session";
import { api } from "../../api/client/api";
import type {
  MoodGroupWithMoodsResponse,
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
    moodGroups: vi.fn(),
    createMood: vi.fn(),
    updateMood: vi.fn(),
    deleteMood: vi.fn(),
    createMoodGroup: vi.fn(),
    updateMoodGroup: vi.fn(),
    deleteMoodGroup: vi.fn(),
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
const awesome: MoodResponse = {
  id: "mood-awesome",
  user_id: user.id,
  name: "Awesome",
  key: "awesome",
  icon: "sentiment_very_satisfied",
  color_value: 4280391411,
  category: "positive",
  score: 5,
  position: 10,
  is_active: true,
  created_at: now,
  updated_at: now,
};
const good: MoodResponse = {
  ...awesome,
  id: "mood-good",
  name: "Good",
  key: "good",
  icon: "sentiment_satisfied",
  score: 4,
  position: 20,
};
const meh: MoodResponse = {
  ...awesome,
  id: "mood-meh",
  name: "Meh",
  key: "meh",
  icon: "sentiment_neutral",
  category: "neutral",
  score: 3,
  position: 30,
};
const bad: MoodResponse = {
  ...awesome,
  id: "mood-bad",
  name: "Bad",
  key: "bad",
  icon: "sentiment_dissatisfied",
  category: "negative",
  score: 2,
  position: 40,
};
const awful: MoodResponse = {
  ...awesome,
  id: "mood-awful",
  name: "Awful",
  key: "awful",
  icon: "sentiment_very_dissatisfied",
  category: "negative",
  score: 1,
  position: 50,
};
const starterMoods = [awesome, good, meh, bad, awful];
const dailyMoods: MoodGroupWithMoodsResponse = {
  id: "group-daily",
  user_id: user.id,
  name: "Daily Moods",
  icon: "mood",
  color_value: 4282400832,
  position: 10,
  moods: starterMoods,
  created_at: now,
  updated_at: now,
};

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  sessionStore.write({ version: 1, accessToken: "a", refreshToken: "r" });
  vi.mocked(api.me).mockResolvedValue(user);
  vi.mocked(api.journals).mockResolvedValue([]);
  vi.mocked(api.moods).mockResolvedValue(starterMoods);
  vi.mocked(api.moodGroups).mockResolvedValue([dailyMoods]);
  vi.mocked(api.createMood).mockResolvedValue(meh);
  vi.mocked(api.updateMood).mockResolvedValue(awesome);
  vi.mocked(api.deleteMood).mockResolvedValue(undefined);
  vi.mocked(api.createMoodGroup).mockResolvedValue(dailyMoods);
  vi.mocked(api.updateMoodGroup).mockResolvedValue(dailyMoods);
  vi.mocked(api.deleteMoodGroup).mockResolvedValue(undefined);
});

async function view(path = "/settings/journaling/moods?q=ignored") {
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
  await screen.findByRole("heading", { name: "Moods" });
  return router;
}

describe("Library · Moods", () => {
  it("opens the real route and renders the complete seeded mood group", async () => {
    const router = await view();

    expect(router.state.location.pathname).toBe("/settings/journaling/moods");
    expect(
      screen.getByRole("link", { name: "Moods" }).getAttribute("aria-current"),
    ).toBe("page");
    expect(await screen.findByText("Daily Moods")).toBeTruthy();
    expect(screen.getByText("5 moods")).toBeTruthy();
    for (const mood of starterMoods) {
      expect(screen.getByText(mood.name)).toBeTruthy();
    }
    expect(screen.getByText("Positive · 5 out of 5")).toBeTruthy();
  });

  it("shows moods not present in any group in the fallback bucket", async () => {
    const focused = { ...meh, id: "mood-focused", name: "Focused" };
    vi.mocked(api.moods).mockResolvedValue([...starterMoods, focused]);
    await view();
    await userEvent.click(
      screen.getByRole("button", { name: /without a group/i }),
    );
    expect(await screen.findByText("Focused")).toBeTruthy();
  });

  it("creates a mood with the supported definition fields", async () => {
    await view();
    await userEvent.click(screen.getByRole("button", { name: "Add mood" }));
    const dialog = await screen.findByRole("dialog", { name: "Add mood" });
    await userEvent.type(within(dialog).getByLabelText("Mood name"), "Calm");
    await userEvent.selectOptions(
      within(dialog).getByLabelText("Feeling score"),
      "4",
    );
    await userEvent.click(within(dialog).getByLabelText("Blue"));
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Add mood" }),
    );

    await waitFor(() =>
      expect(api.createMood).toHaveBeenCalledWith({
        name: "Calm",
        score: 4,
        color_value: 4282090230,
        icon: null,
      }),
    );
  });

  it("edits name, score and colour while disabling a no-op save", async () => {
    await view();
    await userEvent.click(
      screen.getByRole("button", { name: "Awesome actions" }),
    );
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "Edit mood" }),
    );
    const dialog = await screen.findByRole("dialog", { name: "Edit Awesome" });
    expect(
      (
        within(dialog).getByRole("button", {
          name: "Save",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    const name = within(dialog).getByLabelText("Mood name");
    await userEvent.clear(name);
    await userEvent.type(name, "Brilliant");
    await userEvent.selectOptions(
      within(dialog).getByLabelText("Feeling score"),
      "3",
    );
    await userEvent.click(within(dialog).getByLabelText("No colour"));
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(api.updateMood).toHaveBeenCalledWith(awesome.id, {
        name: "Brilliant",
        score: 3,
        color_value: null,
      }),
    );
  });

  it("keeps entered values and reports a failed save", async () => {
    vi.mocked(api.createMood).mockRejectedValueOnce(new Error("network"));
    await view();
    await userEvent.click(screen.getByRole("button", { name: "Add mood" }));
    const dialog = await screen.findByRole("dialog", { name: "Add mood" });
    const input = within(dialog).getByLabelText(
      "Mood name",
    ) as HTMLInputElement;
    await userEvent.type(input, "Hopeful");
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Add mood" }),
    );

    expect((await within(dialog).findByRole("alert")).textContent).toContain(
      "could not be saved",
    );
    expect(input.value).toBe("Hopeful");
  });

  it("creates a mood group through the shared group manager", async () => {
    await view();
    await userEvent.click(
      screen.getByRole("button", { name: "Manage groups" }),
    );
    let dialog = await screen.findByRole("dialog", { name: "Manage groups" });
    await userEvent.click(
      within(dialog).getByRole("button", { name: "New group" }),
    );
    dialog = await screen.findByRole("dialog", { name: "New group" });
    await userEvent.type(
      within(dialog).getByLabelText("Group name"),
      "Workday",
    );
    await userEvent.click(within(dialog).getByLabelText("Blue"));
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Create group" }),
    );

    await waitFor(() =>
      expect(api.createMoodGroup).toHaveBeenCalledWith({
        name: "Workday",
        color_value: 4282090230,
        icon: null,
        position: 1,
      }),
    );
  });

  it("confirms soft deletion and refreshes moods and groups", async () => {
    await view();
    await userEvent.click(
      screen.getByRole("button", { name: "Awesome actions" }),
    );
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "Delete mood…" }),
    );
    const dialog = await screen.findByRole("alertdialog", {
      name: "Delete Awesome?",
    });
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Delete mood" }),
    );

    await waitFor(() =>
      expect(api.deleteMood).toHaveBeenCalledWith(awesome.id),
    );
    await waitFor(() => {
      expect(vi.mocked(api.moods).mock.calls.length).toBeGreaterThan(1);
      expect(vi.mocked(api.moodGroups).mock.calls.length).toBeGreaterThan(1);
    });
  });
});
