import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { sessionStore } from "../../api/auth/session";
import { api } from "../../api/client/api";
import type {
  ActivityResponse,
  GoalCategoryResponse,
  GoalLogResponse,
  GoalResponse,
  GoalWithProgressResponse,
  UserResponse,
} from "../../api/generated/types.gen";
import { createAppQueryClient } from "../../app/queryClient";
import { createAppRouter } from "../../app/router";

vi.mock("../../api/client/api", () => ({
  api: {
    me: vi.fn(),
    journals: vi.fn(),
    activities: vi.fn(),
    moments: vi.fn(),
    goals: vi.fn(),
    goalLogs: vi.fn(),
    goalCategories: vi.fn(),
    createGoal: vi.fn(),
    updateGoal: vi.fn(),
    deleteGoal: vi.fn(),
    createGoalCategory: vi.fn(),
    updateGoalCategory: vi.fn(),
    deleteGoalCategory: vi.fn(),
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
const run: ActivityResponse = {
  id: "activity-run",
  user_id: user.id,
  name: "Running",
  icon: "footprints",
  color: "#3DBE5D",
  position: 10,
  group_id: null,
  created_at: now,
  updated_at: now,
};
const wellness: GoalCategoryResponse = {
  id: "category-wellness",
  user_id: user.id,
  name: "Wellness",
  icon: "heart-pulse",
  color_value: 4280391411,
  position: 10,
};
const weeklyRun: GoalWithProgressResponse = {
  id: "goal-run",
  user_id: user.id,
  title: "Run three times",
  activity_id: run.id,
  category_id: wellness.id,
  category: wellness,
  goal_type: "achieve",
  frequency_type: "weekly",
  target_count: 3,
  reminder_time: "07:30",
  is_paused: false,
  icon: "footprints",
  color_value: 4280391411,
  position: 10,
  archived_at: null,
  current_period_completed: 2,
  status: "fail",
  created_at: now,
  updated_at: now,
};
const reflect: GoalWithProgressResponse = {
  ...weeklyRun,
  id: "goal-reflect",
  title: "Reflect daily",
  activity_id: null,
  category_id: null,
  category: null,
  frequency_type: "daily",
  target_count: 1,
  current_period_completed: 1,
  status: "success",
  position: 20,
};

const runLogs: GoalLogResponse[] = [
  {
    id: "log-1",
    goal_id: weeklyRun.id,
    user_id: user.id,
    logged_date: "2019-08-19",
    period_start: "2019-08-19",
    period_end: "2019-08-25",
    status: "success",
    count: 3,
    source: "auto",
    last_updated_at: now,
    created_at: now,
    updated_at: now,
    moment_id: null,
  },
  {
    id: "log-2",
    goal_id: weeklyRun.id,
    user_id: user.id,
    logged_date: "2019-08-12",
    period_start: "2019-08-12",
    period_end: "2019-08-18",
    status: "fail",
    count: 1,
    source: "manual",
    last_updated_at: now,
    created_at: now,
    updated_at: now,
    moment_id: null,
  },
];

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  sessionStore.write({ version: 1, accessToken: "a", refreshToken: "r" });
  vi.mocked(api.me).mockResolvedValue(user);
  vi.mocked(api.journals).mockResolvedValue([]);
  vi.mocked(api.activities).mockResolvedValue([run]);
  vi.mocked(api.moments).mockResolvedValue({
    items: [],
    next_cursor_logged_at_utc: null,
    next_cursor_id: null,
  });
  vi.mocked(api.goals).mockResolvedValue([weeklyRun, reflect]);
  vi.mocked(api.goalLogs).mockResolvedValue(runLogs);
  vi.mocked(api.goalCategories).mockResolvedValue([wellness]);
  vi.mocked(api.createGoal).mockResolvedValue(weeklyRun as GoalResponse);
  vi.mocked(api.updateGoal).mockResolvedValue(weeklyRun as GoalResponse);
  vi.mocked(api.deleteGoal).mockResolvedValue(undefined);
  vi.mocked(api.createGoalCategory).mockResolvedValue(wellness);
  vi.mocked(api.updateGoalCategory).mockResolvedValue(wellness);
  vi.mocked(api.deleteGoalCategory).mockResolvedValue({ status: "ok" });
});

async function view(path = "/settings/journaling/goals?q=ignored") {
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
  await screen.findByRole("heading", { name: "Goals" });
  return router;
}

describe("Library · Goals", () => {
  it("opens the real route, marks navigation active, and renders API progress", async () => {
    const router = await view();

    expect(router.state.location.pathname).toBe("/settings/journaling/goals");
    expect(
      screen.getByRole("link", { name: "Goals" }).getAttribute("aria-current"),
    ).toBe("page");
    expect(await screen.findByText("Run three times")).toBeTruthy();
    expect(screen.getByText("Wellness")).toBeTruthy();
    expect(
      screen.getByText("Weekly · Achieve · 2/3 this period · Running"),
    ).toBeTruthy();
    expect(screen.getByText("Without a group")).toBeTruthy();
    expect(screen.queryByText("Reflect daily")).toBeNull();
  });

  it("opens the ungrouped fallback bucket on demand", async () => {
    await view();
    await userEvent.click(
      screen.getByRole("button", { name: /without a group/i }),
    );
    expect(await screen.findByText("Reflect daily")).toBeTruthy();
  });

  it("adds a goal to the group selected from its overflow menu", async () => {
    await view();
    await userEvent.click(
      screen.getByRole("button", { name: "Wellness group actions" }),
    );
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "Add goal to group" }),
    );
    const dialog = await screen.findByRole("dialog", { name: "Add goal" });
    expect(
      (within(dialog).getByLabelText("Group") as HTMLSelectElement).value,
    ).toBe(wellness.id);
    await userEvent.type(
      within(dialog).getByLabelText("Goal title"),
      "Stretch every day",
    );
    await userEvent.selectOptions(
      within(dialog).getByLabelText("Linked activity"),
      run.id,
    );
    await userEvent.selectOptions(
      within(dialog).getByLabelText("Frequency"),
      "weekly",
    );
    await userEvent.clear(within(dialog).getByLabelText("Target count"));
    await userEvent.type(within(dialog).getByLabelText("Target count"), "4");
    fireEvent.change(within(dialog).getByLabelText("Reminder time"), {
      target: { value: "08:15" },
    });
    await userEvent.click(within(dialog).getByLabelText("Blue"));
    await userEvent.click(within(dialog).getByLabelText("Target"));
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Add goal" }),
    );

    await waitFor(() =>
      expect(api.createGoal).toHaveBeenCalledWith({
        title: "Stretch every day",
        category_id: wellness.id,
        activity_id: run.id,
        goal_type: "achieve",
        frequency_type: "weekly",
        target_count: 4,
        reminder_time: "08:15",
        is_paused: false,
        color_value: 4282090230,
        icon: "target",
        position: 30,
      }),
    );
  });

  it("edits every supported goal field and validates the target", async () => {
    await view();
    await userEvent.click(
      screen.getByRole("button", { name: "Run three times actions" }),
    );
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "Edit goal" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Edit Run three times",
    });
    expect(
      (
        within(dialog).getByRole("button", {
          name: "Save",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    const title = within(dialog).getByLabelText("Goal title");
    await userEvent.clear(title);
    await userEvent.type(title, "Skip sugary drinks");
    await userEvent.selectOptions(within(dialog).getByLabelText("Group"), "");
    await userEvent.selectOptions(
      within(dialog).getByLabelText("Linked activity"),
      "",
    );
    await userEvent.selectOptions(
      within(dialog).getByLabelText("Direction"),
      "avoid",
    );
    await userEvent.selectOptions(
      within(dialog).getByLabelText("Frequency"),
      "monthly",
    );
    const target = within(dialog).getByLabelText("Target count");
    await userEvent.clear(target);
    await userEvent.type(target, "0");
    expect((await within(dialog).findByRole("alert")).textContent).toContain(
      "whole number",
    );
    expect(
      (
        within(dialog).getByRole("button", {
          name: "Save",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    await userEvent.clear(target);
    await userEvent.type(target, "2");
    fireEvent.change(within(dialog).getByLabelText("Reminder time"), {
      target: { value: "18:45" },
    });
    await userEvent.click(
      within(dialog).getByRole("checkbox", { name: /Pause this goal/ }),
    );
    await userEvent.click(within(dialog).getByLabelText("No colour"));
    await userEvent.click(within(dialog).getByLabelText("None"));
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(api.updateGoal).toHaveBeenCalledWith(weeklyRun.id, {
        title: "Skip sugary drinks",
        category_id: null,
        activity_id: null,
        goal_type: "avoid",
        frequency_type: "monthly",
        target_count: 2,
        reminder_time: "18:45",
        is_paused: true,
        color_value: null,
        icon: null,
      }),
    );
  });

  it("keeps entered values and reports a failed save", async () => {
    vi.mocked(api.createGoal).mockRejectedValueOnce(new Error("network"));
    await view();
    await userEvent.click(screen.getByRole("button", { name: "Add goal" }));
    const dialog = await screen.findByRole("dialog", { name: "Add goal" });
    const input = within(dialog).getByLabelText(
      "Goal title",
    ) as HTMLInputElement;
    await userEvent.type(input, "Meditate");
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Add goal" }),
    );

    expect((await within(dialog).findByRole("alert")).textContent).toContain(
      "could not be saved",
    );
    expect(input.value).toBe("Meditate");
  });

  it("creates a goal group through the reused group manager", async () => {
    await view();
    await userEvent.click(
      screen.getByRole("button", { name: "Manage groups" }),
    );
    let dialog = await screen.findByRole("dialog", { name: "Manage groups" });
    await userEvent.click(
      within(dialog).getByRole("button", { name: "New group" }),
    );
    dialog = await screen.findByRole("dialog", { name: "New group" });
    await userEvent.type(within(dialog).getByLabelText("Group name"), "Work");
    await userEvent.click(within(dialog).getByLabelText("Blue"));
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Create group" }),
    );

    await waitFor(() =>
      expect(api.createGoalCategory).toHaveBeenCalledWith({
        name: "Work",
        color_value: 4282090230,
        icon: null,
        position: 1,
      }),
    );
  });

  it("shows a goal's completion history from the overflow menu", async () => {
    await view();
    await userEvent.click(
      screen.getByRole("button", { name: "Run three times actions" }),
    );
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "View history" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Run three times history",
    });
    await waitFor(() =>
      expect(api.goalLogs).toHaveBeenCalledWith(weeklyRun.id),
    );
    expect(
      within(dialog).getByText("Completed · 3/3 · Logged automatically"),
    ).toBeTruthy();
    expect(
      within(dialog).getByText("Missed · 1/3 · Logged by you"),
    ).toBeTruthy();
    expect(within(dialog).getAllByText(/2019/).length).toBeGreaterThan(0);
  });

  it("recovers from a failed history load with Try again", async () => {
    vi.mocked(api.goalLogs).mockRejectedValueOnce(new Error("network"));
    await view();
    await userEvent.click(
      screen.getByRole("button", { name: "Run three times actions" }),
    );
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "View history" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Run three times history",
    });
    expect((await within(dialog).findByRole("alert")).textContent).toContain(
      "could not be loaded",
    );
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Try again" }),
    );
    expect(
      await within(dialog).findByText("Completed · 3/3 · Logged automatically"),
    ).toBeTruthy();
  });

  it("shows an empty history state when a goal has no logs", async () => {
    vi.mocked(api.goalLogs).mockResolvedValue([]);
    await view();
    await userEvent.click(
      screen.getByRole("button", { name: "Run three times actions" }),
    );
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "View history" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Run three times history",
    });
    expect(await within(dialog).findByText("No history yet")).toBeTruthy();
  });

  it("opens the goal's scoped Timeline from the overflow menu", async () => {
    const router = await view();
    await userEvent.click(
      screen.getByRole("button", { name: "Run three times actions" }),
    );
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "View moments" }),
    );
    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/timeline"),
    );
    expect(router.state.location.search).toMatchObject({ goal: weeklyRun.id });
    expect(
      await screen.findByRole("heading", { name: "Run three times" }),
    ).toBeTruthy();
    await waitFor(() =>
      expect(api.moments).toHaveBeenCalledWith(
        expect.objectContaining({ goal_id: weeklyRun.id }),
      ),
    );
  });

  it("confirms permanent deletion and refreshes goals", async () => {
    await view();
    await userEvent.click(
      screen.getByRole("button", { name: "Run three times actions" }),
    );
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "Delete goal…" }),
    );
    const dialog = await screen.findByRole("alertdialog", {
      name: "Delete Run three times?",
    });
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Delete goal" }),
    );
    await waitFor(() =>
      expect(api.deleteGoal).toHaveBeenCalledWith(weeklyRun.id),
    );
    await waitFor(() =>
      expect(vi.mocked(api.goals).mock.calls.length).toBeGreaterThan(1),
    );
  });
});
